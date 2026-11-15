"""Loopback HTTP adapter for the fixture and an explicitly configured evidence query."""

import argparse
from contextlib import nullcontext
from dataclasses import replace
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from socket import SHUT_WR
import sqlite3
from typing import Annotated, Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts.pack import PackError, decode
from marsdoc import CapabilityQuery, DocumentationEngine, Package
from runtime.final_routing import FinalRoutingSession, RoutingRequest
from runtime.marswalk import HumanProfile, MarswalkError, baseline_from_pack, plan_marswalk, snapshot_from_pack
from runtime.marswalk.environment import parse_utc
from runtime.marswalk.forecast import ForecastModel
from runtime.marswalk.profiles import load_profile
from runtime.marswalk.weather import feed_from_dict
from runtime.mission import load_pack, simulate
from runtime.report_exports import pdf_summary, segments_csv, trace_csv
from runtime.report_segments import plan_segments
from runtime.reporting import ReportStore, stage
from ranking.service import RankRequest, RankingService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contracts/fixtures/synthetic-v1"
MAX_REQUEST_BYTES = 16_384
MAX_ROUTING_REQUEST_BYTES = 262_144
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


class PlanningService:
    def __init__(self, pack, evidence_result, ranking=None, *, engine="mission", hazard_replay=None,
                 final_routing=None, reports=None):
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
        self.pack = pack
        self.evidence_result = evidence_result
        self.ranking = ranking
        self.engine = engine
        self.hazard_replay = hazard_replay
        self.final_routing = final_routing
        self.reports = reports
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
        if reports is not None:
            self.fixture_provenance = {
                "classification": "synthetic", "pack_id": self.identity["pack_id"],
                "pack_version": self.identity["pack_version"], "engine": engine,
                "pack": reports.artifact({name: json.loads((FIXTURE / f"{name}.json").read_bytes())
                                          for name in ("site", "scenario", "stations", "source-manifest")}),
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
        run = (nullcontext(None) if self.reports is None else
               self.reports.run("fixture_plan", request.model_dump(), self.fixture_provenance))
        with run as report:
            result = self._plan(request, report)
            if report is not None:
                report.finish(result)
            return result

    def _plan(self, request, report):
        for key, expected in self.identity.items():
            if getattr(request, key) != expected:
                raise PackError("SCENARIO_MISMATCH", f"{key} differs from the configured fixture")
        if self.engine == "marswalk":
            result = self._marswalk(request, report)
        elif request.profile is not None:
            raise PackError("PROFILE_UNSUPPORTED", "operating profiles need the marswalk engine")
        elif request.weather is not None:
            raise PackError("WEATHER_UNSUPPORTED", "weather feeds need the marswalk engine")
        else:
            with stage(report, "fixture.simulate", "Four-neighbour directed Dijkstra and time-budget checks",
                       {"remaining_s": request.remaining_s, "reserve_s": request.reserve_s,
                        "closure_ids": request.closure_ids}) as record:
                result = simulate(self.pack, closures=request.closure_ids, remaining_s=request.remaining_s)
                record.update(status=result["status"], recommendation=result["recommendation"])
        return {"schema_version": 1, "request_id": request.request_id, "route_index_order": "row_col", **result}

    def _marswalk(self, request, report=None):
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
            if request.weather is not None:
                feed = feed_from_dict(request.weather)
                now_utc = request.weather.get("now_utc")
                try:
                    parse_utc(now_utc)
                except MarswalkError as error:
                    raise MarswalkError("INVALID_WEATHER", "weather needs a valid now_utc timestamp in UTC") from error
                snapshot = replace(snapshot, weather=feed, time_utc=now_utc)
            result = plan_marswalk(self.baseline, snapshot, report=report,
                                   report_scope=f"{snapshot.profile.platform}.")
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
        if report is not None:
            with stage(report, "result.publish", "Record edge costs and route recommendation", {}) as record:
                record["platforms"] = {snapshot.profile.platform: {"segments": plan_segments(result)}}
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
        self.send_bytes(status, json.dumps(body, allow_nan=False).encode(), "application/json")

    def send_bytes(self, status, raw, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if filename is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(raw)

    def reject(self, status, code, message, request_id=None):
        self.send_json(status, {
            "schema_version": 1, "request_id": request_id, "error": code, "message": message,
        })

    def reject_large_body(self, length):
        self.reject(413, "INVALID_LENGTH", "Invalid JSON body length")
        # On Windows a close with unread request bytes can reset the response.
        # Send EOF first and drain a bounded amount from clients already writing.
        try:
            self.connection.shutdown(SHUT_WR)
            self.connection.settimeout(0.1)
            self.rfile.read(min(length, 65_536))
        except OSError:
            pass

    def do_GET(self):
        if self.path.startswith(("/api/v1/reports", "/api/v1/report-artifacts/")):
            try:
                self.report_resource()
            except sqlite3.Error:
                self.reject(503, "REPORT_STORE_UNAVAILABLE", "The report store is unavailable")
        elif self.path == "/healthz":
            self.send_json(200, {"status": "ready"})
        elif self.path == "/api/v1/site":
            self.send_json(200, self.service.site())
        elif self.path in ("/api/v1/routing/site", "/api/v1/routing/plan"):
            routing = self.service.final_routing
            if routing is None:
                self.reject(503, "ROUTING_NOT_CONFIGURED", "Configure the synthetic station model for the routing drill")
            else:
                self.send_json(200, routing.site() if self.path.endswith("/site") else routing.latest())
        elif self.path.startswith("/api/v1/hazard-replay/"):
            self.hazard_frame(self.path.removeprefix("/api/v1/hazard-replay/"))
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

    def report_resource(self):
        url = urlsplit(self.path)
        store = self.service.reports
        if url.path == "/api/v1/reports":
            try:
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=2)
                if params.keys() - {"limit", "offset"} or any(len(values) != 1 for values in params.values()):
                    raise ValueError
                limit = int(params.get("limit", ["25"])[0])
                offset = int(params.get("offset", ["0"])[0])
                if not 1 <= limit <= 100 or not 0 <= offset < 2**63:
                    raise ValueError
            except ValueError:
                self.reject(400, "INVALID_REPORT_QUERY", "Expected limit from 1 through 100 and a nonnegative offset")
            else:
                self.send_json(200, store.list(limit, offset))
            return
        artifact = re.fullmatch(r"/api/v1/report-artifacts/([a-f0-9]{64})", url.path)
        if artifact:
            raw = store.read_artifact(artifact[1])
            if raw is not None:
                self.send_bytes(200, raw, "application/json")
                return
        match = re.fullmatch(r"/api/v1/reports/([a-f0-9]{32})(?:/(trace\.csv|segments\.csv|report\.pdf|report\.json))?",
                             url.path)
        report = None if match is None else store.read(match[1])
        if report is None:
            self.reject(404, "REPORT_NOT_FOUND", "Unknown report or artifact")
            return
        if match[2] is None:
            self.send_json(200, report)
            return
        export = match[2]
        if export == "report.pdf":
            try:
                raw = pdf_summary(report)
            except ImportError:
                self.reject(503, "PDF_EXPORT_UNAVAILABLE", "Install ReportLab to enable PDF export")
                return
            content_type = "application/pdf"
        elif export == "report.json":
            content_type = "application/json"
            raw = json.dumps(report, allow_nan=False, indent=2).encode()
        else:
            content_type = "text/csv; charset=utf-8"
            raw = (trace_csv if export == "trace.csv" else segments_csv)(report)
        self.send_bytes(200, raw, content_type, f"{match[1]}-{export}")

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
        requests = {"/api/v1/plan": PlanRequest, "/api/v1/rank": RankRequest, "/api/v1/routing/plan": RoutingRequest}
        request_type = requests.get(self.path)
        if request_type is None:
            self.reject(404, "NOT_FOUND", "Unknown endpoint")
            return
        if self.headers.get_content_type() != "application/json":
            self.reject(415, "INVALID_CONTENT_TYPE", "Expected application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        max_bytes = MAX_ROUTING_REQUEST_BYTES if request_type is RoutingRequest else MAX_REQUEST_BYTES
        if length > max_bytes:
            self.reject_large_body(length)
            return
        if length <= 0:
            self.reject(400, "INVALID_LENGTH", "Invalid JSON body length")
            return
        payload = None
        try:
            payload = decode(self.rfile.read(length))
            request = request_type.model_validate(payload)
        except (PackError, ValidationError, TimeoutError):
            request_id = payload.get("request_id") if isinstance(payload, dict) else None
            self.reject(400, "INVALID_REQUEST", "Expected a valid v1 request",
                        request_id if isinstance(request_id, str) and 0 < len(request_id) <= 128 else None)
            return
        try:
            if request_type is RoutingRequest:
                if self.service.final_routing is None:
                    self.reject(503, "ROUTING_NOT_CONFIGURED", "Configure the synthetic station model for the routing drill",
                                request.request_id)
                else:
                    self.send_json(200, self.service.final_routing.update(request))
            elif request_type is RankRequest:
                if self.service.ranking is None:
                    self.reject(503, "RANKING_NOT_CONFIGURED", "Configure a cell ranking pack", request.request_id)
                else:
                    ranking = self.service.ranking
                    pack = ranking.engine.pack
                    with self.service.reports.run("cell_ranking", request.model_dump(),
                                                  {"ranking_pack_sha256": pack.sha256,
                                                   "ranking_pack_version": pack.manifest["version"]}) as report:
                        result = ranking.rank(request, report=report)
                        report.finish(result)
                    self.send_json(200, result)
            else:
                self.send_json(200, self.service.plan(request))
        except (PackError, MarswalkError) as error:
            conflicts = {"SCENARIO_MISMATCH", "MIXED_PACK", "STALE_REVISION", "STALE_HAZARD", "WEATHER_CONFLICT"}
            self.reject(409 if error.code in conflicts else 400,
                        error.code, str(error), request.request_id)
        except sqlite3.Error:
            self.reject(503, "REPORT_STORE_UNAVAILABLE", "The report store is unavailable", request.request_id)


class PlanningServer(ThreadingHTTPServer):
    def __init__(self, port, service):
        self.reports = service.reports
        super().__init__(("127.0.0.1", port), partial(PlanningHandler, service=service))

    # Finish request handlers before closing the store they use.
    daemon_threads = False

    def server_close(self):
        super().server_close()
        if self.reports is not None:
            self.reports.close()
            self.reports = None


def create_server(port=8000, *, evidence_package=None, evidence_query=None,
                  ranking_pack=None, engine="mission", hazard_model=None, final_routing_model=None,
                  final_rover_profile=None, final_human_policy=None, report_db=None):
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
    if final_routing_model is None and (final_rover_profile is not None or final_human_policy is not None):
        raise ValueError("an integrated profile requires --final-routing-model")
    reports = ReportStore(report_db)
    try:
        final_routing = None if final_routing_model is None else FinalRoutingSession(
            ForecastModel.load(final_routing_model), rover_profile=final_rover_profile, human_policy=final_human_policy,
            reports=reports,
        )
        service = PlanningService(load_pack(FIXTURE, simulation=True), result,
                                  RankingService(ranking_pack) if ranking_pack else None,
                                  engine=engine, hazard_replay=replay, final_routing=final_routing, reports=reports)
        return PlanningServer(port, service)
    except Exception:
        reports.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--evidence-package", type=Path)
    parser.add_argument("--evidence-query", type=Path)
    parser.add_argument("--engine", choices=ENGINES, default="mission",
                        help="planner behind POST /api/v1/plan (default: mission)")
    parser.add_argument("--ranking-pack", type=Path)
    parser.add_argument("--hazard-model", type=Path, help="enable the local hazard replay with this synthetic station artifact")
    parser.add_argument("--final-routing-model", type=Path, help="enable integrated routing with this synthetic station artifact")
    parser.add_argument("--final-rover-profile", type=Path, help="rover profile for integrated routing")
    parser.add_argument("--final-human-policy", type=Path, help="human cost policy for integrated routing")
    parser.add_argument("--report-db", type=Path, help="SQLite run history file (in-memory by default)")
    args = parser.parse_args()
    try:
        server = create_server(args.port, evidence_package=args.evidence_package,
                               evidence_query=args.evidence_query, ranking_pack=args.ranking_pack,
                               engine=args.engine, hazard_model=args.hazard_model, final_routing_model=args.final_routing_model,
                               final_rover_profile=args.final_rover_profile, final_human_policy=args.final_human_policy,
                               report_db=args.report_db)
    except (OSError, ValueError, KeyError, PackError, MarswalkError, sqlite3.Error) as error:
        parser.exit(2, f"Unable to initialize planning service: {error}\n")
    with server:
        print(f"Planning service ready at http://127.0.0.1:{server.server_port} (engine: {args.engine})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
