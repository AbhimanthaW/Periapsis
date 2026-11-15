"""Loopback HTTP adapter for the fixture and an explicitly configured evidence query."""

import argparse
from dataclasses import replace
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from mimetypes import guess_type
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from marsdoc.grid import Grid

from contracts.pack import PackError, decode
from marsdoc import CapabilityQuery, DocumentationEngine, Package
from runtime.marswalk import HumanProfile, MarswalkError, baseline_from_pack, plan_marswalk, snapshot_from_pack
from runtime.marswalk.environment import parse_utc
from runtime.marswalk.profiles import load_profile
from runtime.marswalk.weather import feed_from_dict
from runtime.mission import load_pack, simulate
from runtime.region_evidence import RegionEvidence
from ranking.service import RankRequest, RankingService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/fixtures/synthetic-v1"
MAX_REQUEST_BYTES = 16_384
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Seconds = Annotated[int, Field(ge=0, le=86_400)]
ENGINES = ("mission", "marswalk")
# The fixture contract is 4-neighbour moves at 1 s/m plus 2 s per metre climbed.
# The Marswalk control profile reproduces it, so the v1 response stays identical.
FIXTURE_CONTROL = HumanProfile(pace_model="control_linear", neighbours=4)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Annotated[int, Field(ge=1, le=1)]
    request_id: Identifier
    pack_id: Identifier
    pack_version: Identifier
    scenario_id: Identifier
    checkpoint_id: Identifier
    shelter_id: Identifier
    closure_ids: Annotated[list[Identifier], Field(max_length=64)]
    completed_task_ids: Annotated[list[Identifier], Field(max_length=64)]
    remaining_s: Seconds
    reserve_s: Seconds
    # Optional operating profile fed as data (runtime/examples/profile-*.json). Marswalk engine only;
    # absent means the fixture control profile, so the v1 response is unchanged.
    profile: dict[str, Any] | None = None
    # Optional base-station weather feed (runtime/examples/weather-*.json shape) with a required
    # "now_utc" that sets the plan time. Marswalk engine only. Forecasts are advisory; an observed
    # return-now warning blocks science; a lost link on a required feed leaves science unknown.
    weather: Any = None  # Validated at the service boundary for the weather-specific error code.


GridCell = tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]]
MarsPoint = tuple[Annotated[float, Field(ge=-180, le=180)], Annotated[float, Field(ge=-90, le=90)]]


class SortieRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[2]
    request_id: Identifier
    sortie_id: Identifier
    revision: Annotated[int, Field(ge=1)]
    context_cell_id: Identifier
    mars_base_point: MarsPoint
    pack_id: Identifier
    pack_version: Identifier
    scenario_id: Identifier
    mode: Literal["simulation", "tactical"]
    base_cell: GridCell | None = None
    current_cell: GridCell | None = None
    closure_ids: list[Identifier] = Field(max_length=64)
    completed_task_ids: list[Identifier] = Field(max_length=64)
    remaining_s: Seconds


class PlanningService:
    def __init__(self, pack, evidence_result, ranking=None, *, engine="mission", hazard_replay=None, regions=None):
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
        self.pack = pack
        self.evidence_result = evidence_result
        self.ranking = ranking
        self.regions = regions
        self.grid = Grid()
        self.sorties = {}
        self.sortie_lock = Lock()
        self.engine = engine
        self.hazard_replay = hazard_replay
        self.baseline = baseline_from_pack(pack) if engine == "marswalk" else None
        scenario = pack.scenario
        self.identity = {
            "pack_id": pack.site["pack_id"],
            "pack_version": pack.site["pack_version"],
            "scenario_id": scenario["scenario_id"],
            "checkpoint_id": scenario["checkpoint"]["id"],
            "shelter_id": scenario["shelter"]["id"],
            "completed_task_ids": list(scenario["completed_task_ids"]),
            "reserve_s": scenario["reserve_s"],
        }

    def site(self):
        scenario = self.pack.scenario
        grid = self.pack.site["grid"]
        return {
            "schema_version": 1,
            **self.identity,
            "classification": "synthetic",
            "capabilities": list(self.pack.site["capabilities"]),
            "remaining_s": scenario["remaining_s"],
            "closures": [{"id": item["id"], "cells": item["cells"]} for item in scenario["closures"]],
            "checkpoint_cell": scenario["checkpoint"]["cell"],
            "shelter_cell": scenario["shelter"]["cell"],
            "grid": {"shape": grid["shape"], "affine": grid["affine"], "index_order": "row_col"},
        }

    def plan(self, request):
        for key, expected in self.identity.items():
            if getattr(request, key) != expected:
                raise PackError("SCENARIO_MISMATCH", f"{key} differs from the configured fixture")
        if self.engine == "marswalk":
            result = self._marswalk(request)
        elif request.profile is not None:
            raise PackError("PROFILE_UNSUPPORTED", "operating profiles need the marswalk engine")
        elif request.weather is not None:
            raise PackError("WEATHER_UNSUPPORTED", "weather feeds need the marswalk engine")
        else:
            result = simulate(self.pack, closures=request.closure_ids, remaining_s=request.remaining_s)
        return {"schema_version": 1, "request_id": request.request_id, "route_index_order": "row_col", **result}

    def sortie(self, request):
        cell_id = self.grid.cell_at(request.mars_base_point).id
        if cell_id != request.context_cell_id:
            raise PackError("CELL_MISMATCH", "The base point does not belong to the selected Mars cell")
        if request.mode == "tactical":
            raise PackError("TERRAIN_UNQUALIFIED", "A qualified tactical terrain pack is required for the base and route")
        if self.baseline is None:
            raise PackError("SIMULATION_UNAVAILABLE", "Start the service with the Marswalk engine")
        for field in ("pack_id", "pack_version", "scenario_id"):
            if getattr(request, field) != self.identity[field]:
                raise PackError("SCENARIO_MISMATCH", f"{field} differs from the configured fixture")
        named = {item["id"]: item["cells"] for item in self.pack.scenario["closures"]}
        if len(set(request.closure_ids)) != len(request.closure_ids) or set(request.closure_ids) - named.keys():
            raise PackError("INVALID_SCENARIO", "Unknown or duplicate closure")
        closed = {tuple(cell) for name in request.closure_ids for cell in named[name]}
        rows, cols = self.pack.site["grid"]["shape"]
        for location in (request.base_cell, request.current_cell):
            if location is None or not (0 <= location[0] < rows and 0 <= location[1] < cols):
                raise PackError("INVALID_POSITION", "Choose a position on the synthetic grid")
        terrain = self.pack.terrain
        for label, location in (("base", request.base_cell), ("crew", request.current_cell)):
            if not terrain["valid_mask"][location] or terrain["screen_excluded_mask"][location] or location in closed:
                raise PackError("BLOCKED_POSITION", f"The {label} position is closed or unsupported")
        known_tasks = set(self.identity["completed_task_ids"])
        known_tasks.update(task["id"] for task in self.pack.stations)
        completed = set(request.completed_task_ids)
        if len(completed) != len(request.completed_task_ids) or not completed <= known_tasks or not set(self.identity["completed_task_ids"]) <= completed:
            raise PackError("INVALID_TASKS", "Completed tasks must be unique fixture task IDs")
        identity = (request.context_cell_id, request.mars_base_point, request.base_cell)
        with self.sortie_lock:
            prior = self.sorties.get(request.sortie_id)
            if prior is None:
                if request.current_cell != request.base_cell:
                    raise PackError("SCENARIO_MISMATCH", "A new sortie must start at its base")
            else:
                prior_request, prior_result = prior
                if request == prior_request:
                    return prior_result
                same_base = identity == (prior_request.context_cell_id, prior_request.mars_base_point, prior_request.base_cell)
                if not same_base or not set(prior_request.completed_task_ids) <= completed:
                    raise PackError("SCENARIO_MISMATCH", "Keep the sortie base and completed work")
                if request.revision <= prior_request.revision:
                    raise PackError("STALE_REVISION", "The sortie already has a newer revision")
            result = self._marswalk(request, sortie=request)
            response = {
                "schema_version": 2, "request_id": request.request_id, "sortie_id": request.sortie_id,
                "revision": request.revision, "context_cell_id": cell_id,
                "mars_base_point": request.mars_base_point, "base_cell": request.base_cell,
                "current_cell": request.current_cell, "route_index_order": "row_col", **result,
            }
            self.sorties[request.sortie_id] = (request, response)
            return response

    def _marswalk(self, request, *, sortie=None):
        """Plan with runtime.marswalk and serialize the v1 fields the mission view reads.
        The complete Marswalk plan is attached under `marswalk` for later UI work."""
        scenario = self.pack.scenario
        named = {closure["id"] for closure in scenario["closures"]}
        closures = request.closure_ids
        if len(set(closures)) != len(closures) or set(closures) - named:
            raise PackError("INVALID_SCENARIO", "unknown or duplicate closure")
        try:
            profile = FIXTURE_CONTROL if sortie or request.profile is None else load_profile(request.profile)
            snapshot = snapshot_from_pack(self.pack, closure_ids=tuple(closures), remaining_s=request.remaining_s,
                                          profile=profile, mission_id=request.request_id)
            if sortie:
                snapshot = replace(snapshot, mission_id=sortie.sortie_id, revision=sortie.revision,
                                   current_cell=sortie.current_cell, return_cell=sortie.base_cell,
                                   completed_task_ids=tuple(sortie.completed_task_ids))
            if not sortie and request.weather is not None:
                feed = feed_from_dict(request.weather)
                now_utc = request.weather.get("now_utc")
                try:
                    parse_utc(now_utc)
                except MarswalkError as error:
                    raise MarswalkError("INVALID_WEATHER", "weather needs a valid now_utc timestamp in UTC") from error
                snapshot = replace(snapshot, weather=feed, time_utc=now_utc)
            result = plan_marswalk(self.baseline, snapshot)
        except MarswalkError as error:
            raise PackError(error.code, str(error)) from error

        def route(leg):
            return {"seconds": leg.seconds, "cells": [list(cell) for cell in leg.cells]} if leg.ok else None

        direct = result.direct_leg
        reverse = result.router.leg_outbound(snapshot.return_cell, snapshot.current_cell)
        science = []
        if result.status == "OK":
            for task in snapshot.tasks:
                if task.id in snapshot.completed_task_ids:
                    continue
                plan = result.plan(f"science:{task.id}")
                science.append({"id": task.id, "seconds": plan.ledger.total_use, "margin_s": plan.ledger.margin,
                                "feasible": plan.passed})
        recommendation = result.recommendation
        if recommendation is not None and recommendation.startswith("science:"):
            recommendation = recommendation.removeprefix("science:")
        return dict(pack_id=snapshot.pack_id, pack_version=snapshot.pack_version, scenario_id=snapshot.scenario_id,
                    classification="synthetic", closure_ids=list(closures), remaining_s=snapshot.remaining_s,
                    reserve_s=snapshot.reserve_s, direct_return=route(direct), reverse_control=route(reverse),
                    return_margin_s=result.direct_gate.margin_s if direct.ok else None,
                    completed_task_ids=list(snapshot.completed_task_ids), science=science,
                    recommendation=recommendation, status=result.status, engine="marswalk",
                    marswalk=result.to_dict())

    def evidence(self):
        if self.evidence_result is None:
            raise PackError("EVIDENCE_NOT_CONFIGURED", "Configure a qualified demo site evidence package and query")
        return {
            "schema_version": 1,
            "classification": "provenance_unverified",
            "context": "operator_configured_evidence",
            "result": self.evidence_result,
        }


class PlanningHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, service, static_root, **kwargs):
        self.service = service
        self.static_root = static_root
        super().__init__(*args, **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def send_payload(self, status, raw, content_type, *, cache_control=None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # Browser navigation and superseded planner requests cancel in-flight responses.
            self.close_connection = True

    def send_json(self, status, body):
        self.send_payload(status, json.dumps(body, allow_nan=False).encode(), "application/json",
                          cache_control="no-store")

    def reject(self, status, code, message, request_id=None):
        self.send_json(status, {
            "schema_version": 1, "request_id": request_id, "error": code, "message": message,
        })

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ready"})
        elif self.path == "/api/v1/site":
            self.send_json(200, self.service.site())
        elif self.path.startswith("/api/v1/hazard-replay/"):
            self.hazard_frame(self.path.removeprefix("/api/v1/hazard-replay/"))
        elif self.path == "/api/v1/evidence":
            try:
                self.send_json(200, self.service.evidence())
            except PackError as error:
                self.reject(503, error.code, str(error))
        elif self.path.startswith("/api/v1/regions/"):
            region = self.service.regions.get(self.path.removeprefix("/api/v1/regions/"), self.service.ranking)
            if region is None:
                self.reject(404, "REGION_NOT_FOUND", "Atlas region ID was not found")
            else:
                self.send_json(200, region)
        elif urlsplit(self.path).path == "/api/v1/cell-at":
            try:
                query = parse_qs(urlsplit(self.path).query)
                lon, lat = float(query["lon"][0]), float(query["lat"][0])
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError
                cell = self.service.grid.cell_at((lon, lat))
            except (KeyError, ValueError):
                self.reject(400, "INVALID_COORDINATES", "Supply Mars longitude and latitude in degrees")
            else:
                self.send_json(200, cell.model_dump(mode="json"))
        elif self.path.startswith("/api/v1/cell-context/"):
            try:
                cell_id = unquote(self.path.removeprefix("/api/v1/cell-context/"))
                result = self.service.regions.cell_context(cell_id, self.service.ranking)
            except ValueError:
                self.reject(404, "CELL_NOT_FOUND", "Cell ID was not found")
            else:
                self.send_json(200, result)
        elif self.path.startswith("/api/v1/cell/"):
            if self.service.ranking is None:
                self.reject(503, "RANKING_NOT_CONFIGURED", "Configure a cell ranking pack")
                return
            result = self.service.ranking.detail(self.path.removeprefix("/api/v1/cell/"))
            if result is None:
                self.reject(404, "CELL_NOT_FOUND", "Cell ID was not found")
            else:
                self.send_json(200, result)
        elif not self.serve_release_file():
            self.reject(404, "NOT_FOUND", "Unknown endpoint")

    def serve_release_file(self):
        if self.static_root is None:
            return False
        request_path = unquote(urlsplit(self.path).path)
        if request_path.startswith("/api/") or request_path == "/healthz":
            return False
        if request_path in {"/", "/atlas", "/atlas/", "/mission", "/mission/", "/architecture", "/architecture/", "/explore", "/explore/"}:
            directory, name = "app", "index.html"
        elif request_path == "/demo":
            self.send_response(308)
            self.send_header("Location", "/demo/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        elif request_path == "/demo/":
            directory, name = "demo", "index.html"
        elif request_path.startswith("/demo/"):
            directory, name = "demo", request_path.removeprefix("/demo/")
        else:
            directory, name = "app", request_path.lstrip("/")
        base = self.static_root / directory
        artifact = (base / name).resolve()
        if not artifact.is_relative_to(base) or not artifact.is_file():
            return False
        self.send_payload(200, artifact.read_bytes(), guess_type(artifact)[0] or "application/octet-stream")
        return True

    def hazard_frame(self, step):
        replay = self.service.hazard_replay
        if replay is None:
            self.reject(503, "HAZARD_REPLAY_NOT_CONFIGURED", "The offline replay bundle is available in Mission Preview")
            return
        try:
            if not step.isascii() or not step.isdecimal() or len(step) > 2:
                raise IndexError
            frame = replay.frame(int(step))
        except IndexError:
            self.reject(404, "HAZARD_FRAME_NOT_FOUND", "Unknown replay step")
        else:
            self.send_json(200, frame)

    def do_POST(self):
        if self.path not in ("/api/v1/plan", "/api/v1/rank", "/api/v2/plan"):
            self.reject(404, "NOT_FOUND", "Unknown endpoint")
            return
        if self.headers.get_content_type() != "application/json":
            self.reject(415, "INVALID_CONTENT_TYPE", "Expected application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_REQUEST_BYTES:
            self.reject(413 if length > MAX_REQUEST_BYTES else 400, "INVALID_LENGTH", "Invalid JSON body length")
            return
        payload = None
        try:
            payload = decode(self.rfile.read(length))
            schema = {"/api/v1/rank": RankRequest, "/api/v1/plan": PlanRequest, "/api/v2/plan": SortieRequest}[self.path]
            request = schema.model_validate_json(json.dumps(payload))
        except (PackError, ValidationError, TimeoutError):
            request_id = payload.get("request_id") if isinstance(payload, dict) else None
            self.reject(400, "INVALID_REQUEST", "Expected a valid versioned request",
                        request_id if isinstance(request_id, str) and 0 < len(request_id) <= 128 else None)
            return
        try:
            if self.path == "/api/v1/rank":
                if self.service.ranking is None:
                    self.reject(503, "RANKING_NOT_CONFIGURED", "Configure a cell ranking pack", request.request_id)
                else:
                    self.send_json(200, self.service.ranking.rank(request))
            elif self.path == "/api/v2/plan":
                self.send_json(200, self.service.sortie(request))
            else:
                self.send_json(200, self.service.plan(request))
        except PackError as error:
            self.reject(409 if error.code in {"SCENARIO_MISMATCH", "STALE_REVISION"} else 400,
                        error.code, str(error), request.request_id)


def create_server(port=8000, *, evidence_package=None, evidence_query=None,
                  ranking_pack=None, engine="mission", hazard_model=None, static_root=None):
    if (evidence_package is None) != (evidence_query is None):
        raise ValueError("Supply the evidence package and query together")
    result = None
    if evidence_package is not None:
        package = Package.model_validate_json(evidence_package.read_bytes())
        query = CapabilityQuery.model_validate_json(evidence_query.read_bytes())
        result = DocumentationEngine(package).resolve(query).model_dump(mode="json")
    replay = None
    if hazard_model is not None:
        from runtime.hazards.replay import HazardReplay
        replay = HazardReplay(hazard_model)
    service = PlanningService(load_pack(FIXTURE, simulation=True), result,
                              RankingService(ranking_pack) if ranking_pack else None,
                              engine=engine, hazard_replay=replay, regions=RegionEvidence(ROOT))
    return ThreadingHTTPServer(("127.0.0.1", port), partial(PlanningHandler, service=service, static_root=static_root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--evidence-package", type=Path)
    parser.add_argument("--evidence-query", type=Path)
    parser.add_argument("--engine", choices=ENGINES, default="mission",
                        help="planner behind POST /api/v1/plan (default: mission)")
    parser.add_argument("--ranking-pack", type=Path)
    parser.add_argument("--hazard-model", type=Path, help="enable the local hazard replay with this synthetic station artifact")
    args = parser.parse_args()
    try:
        server = create_server(args.port, evidence_package=args.evidence_package,
                               evidence_query=args.evidence_query, ranking_pack=args.ranking_pack,
                               engine=args.engine, hazard_model=args.hazard_model)
    except (OSError, ValueError, PackError) as error:
        parser.exit(2, f"Unable to initialize planning service: {error}\n")
    with server:
        print(f"Planning service ready at http://127.0.0.1:{server.server_port} (engine: {args.engine})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
