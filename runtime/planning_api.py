"""Loopback HTTP adapter for the fixture and an explicitly configured evidence query."""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts.pack import PackError, decode
from marsdoc import CapabilityQuery, DocumentationEngine, Package
from runtime.marswalk import HumanProfile, MarswalkError, baseline_from_pack, plan_marswalk, snapshot_from_pack
from runtime.marswalk.profiles import load_profile
from runtime.mission import load_pack, simulate
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


class PlanningService:
    def __init__(self, pack, evidence_result, ranking=None, *, engine="mission"):
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
        self.pack = pack
        self.evidence_result = evidence_result
        self.ranking = ranking
        self.engine = engine
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
        else:
            result = simulate(self.pack, closures=request.closure_ids, remaining_s=request.remaining_s)
        return {"schema_version": 1, "request_id": request.request_id, "route_index_order": "row_col", **result}

    def _marswalk(self, request):
        """Plan with runtime.marswalk and serialize the v1 fields the mission view reads.
        The complete Marswalk plan is attached under `marswalk` for later UI work."""
        scenario = self.pack.scenario
        named = {closure["id"] for closure in scenario["closures"]}
        closures = request.closure_ids
        if len(set(closures)) != len(closures) or set(closures) - named:
            raise PackError("INVALID_SCENARIO", "unknown or duplicate closure")
        try:
            profile = FIXTURE_CONTROL if request.profile is None else load_profile(request.profile)
            snapshot = snapshot_from_pack(self.pack, closure_ids=tuple(closures), remaining_s=request.remaining_s,
                                          profile=profile, mission_id=request.request_id)
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
    def __init__(self, *args, service, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def send_json(self, status, body):
        raw = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def reject(self, status, code, message, request_id=None):
        self.send_json(status, {
            "schema_version": 1, "request_id": request_id, "error": code, "message": message,
        })

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ready"})
        elif self.path == "/api/v1/site":
            self.send_json(200, self.service.site())
        elif self.path == "/api/v1/evidence":
            try:
                self.send_json(200, self.service.evidence())
            except PackError as error:
                self.reject(503, error.code, str(error))
        elif self.path.startswith("/api/v1/cell/"):
            if self.service.ranking is None:
                self.reject(503, "RANKING_NOT_CONFIGURED", "Configure a cell ranking pack")
                return
            result = self.service.ranking.detail(self.path.removeprefix("/api/v1/cell/"))
            if result is None:
                self.reject(404, "CELL_NOT_FOUND", "Cell ID was not found")
            else:
                self.send_json(200, result)
        else:
            self.reject(404, "NOT_FOUND", "Unknown endpoint")

    def do_POST(self):
        if self.path not in ("/api/v1/plan", "/api/v1/rank"):
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
            request = (RankRequest if self.path == "/api/v1/rank" else PlanRequest).model_validate(payload)
        except (PackError, ValidationError, TimeoutError):
            request_id = payload.get("request_id") if isinstance(payload, dict) else None
            self.reject(400, "INVALID_REQUEST", "Expected a valid v1 request",
                        request_id if isinstance(request_id, str) and 0 < len(request_id) <= 128 else None)
            return
        try:
            if self.path == "/api/v1/rank":
                if self.service.ranking is None:
                    self.reject(503, "RANKING_NOT_CONFIGURED", "Configure a cell ranking pack", request.request_id)
                else:
                    self.send_json(200, self.service.ranking.rank(request))
            else:
                self.send_json(200, self.service.plan(request))
        except PackError as error:
            self.reject(409 if error.code == "SCENARIO_MISMATCH" else 400,
                        error.code, str(error), request.request_id)


def create_server(port=8000, *, evidence_package=None, evidence_query=None,
                  ranking_pack=None, engine="mission"):
    if (evidence_package is None) != (evidence_query is None):
        raise ValueError("Supply the evidence package and query together")
    result = None
    if evidence_package is not None:
        package = Package.model_validate_json(evidence_package.read_bytes())
        query = CapabilityQuery.model_validate_json(evidence_query.read_bytes())
        result = DocumentationEngine(package).resolve(query).model_dump(mode="json")
    service = PlanningService(load_pack(FIXTURE, simulation=True), result,
                              RankingService(ranking_pack) if ranking_pack else None,
                              engine=engine)
    return ThreadingHTTPServer(("127.0.0.1", port), partial(PlanningHandler, service=service))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--evidence-package", type=Path)
    parser.add_argument("--evidence-query", type=Path)
    parser.add_argument("--engine", choices=ENGINES, default="mission",
                        help="planner behind POST /api/v1/plan (default: mission)")
    parser.add_argument("--ranking-pack", type=Path)
    args = parser.parse_args()
    try:
        server = create_server(args.port, evidence_package=args.evidence_package,
                               evidence_query=args.evidence_query, ranking_pack=args.ranking_pack,
                               engine=args.engine)
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
