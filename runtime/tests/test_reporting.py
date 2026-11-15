import csv
from hashlib import sha256
from http.client import HTTPConnection
from io import StringIO
import json
from threading import Thread

import pytest

from runtime.marswalk.forecast import ForecastModel
from runtime.planning_api import create_server
from runtime.reporting import ReportStore
from runtime.tests.test_final_routing import PLANS, forecast_artifact, payload, station_history


def _call(server, path, data=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=20)
    try:
        if data is None:
            connection.request("GET", path)
        else:
            connection.request("POST", path, json.dumps(data), {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read()
        body = json.loads(raw) if response.getheader("Content-Type") == "application/json" else raw
        return response.status, body, raw
    finally:
        connection.close()


def test_report_matches_routing_and_survives_restart(forecast_artifact, tmp_path):
    database = tmp_path / "runs.sqlite"
    with create_server(0, report_db=database, final_routing_model=forecast_artifact) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            _, site, _ = _call(server, "/api/v1/routing/site")
            model = ForecastModel.load(forecast_artifact)
            request = payload(site, 0, weather_readings=station_history(model, site["start_time_utc"]))
            status, plan, _ = _call(server, PLANS, request)
            assert status == 200
            assert _call(server, PLANS, request)[:2] == (200, plan)
            assert _call(server, PLANS, request | {"request_id": "conflict"})[0] == 409
            _, history, _ = _call(server, "/api/v1/reports?limit=1")
            assert history["next_offset"] == 1
            _, failed, _ = _call(server, f"/api/v1/reports/{history['reports'][0]['report_id']}")
            assert failed["status"] == "failed" and failed["error"]["code"] == "STALE_REVISION"
            _, history, _ = _call(server, "/api/v1/reports?offset=1")
            [row] = history["reports"]
            report_id = row["report_id"]
            base = f"/api/v1/reports/{report_id}"
            _, report, _ = _call(server, base)
            assert report["status"] == "completed" and report["revision"] == 1
            assert report["result"] == plan
            assert report["request"]["weather_readings"] == request["weather_readings"]
            trace = {step["name"]: step for step in report["calculation_trace"]}
            assert trace["weather.station_forecast"]["outputs"]["feature_vectors"]
            assert trace["weather.station_forecast"]["outputs"]["forecast"]["forecasts"] == plan["forecast"]["forecasts"]
            assert trace["human.tradeoff"]["outputs"]["oxygen_update"] == plan["tradeoff"]["model"]["oxygen_update"]
            assert trace["human.oxygen_update"]["outputs"]["applied_factors"] == (
                plan["tradeoff"]["model"]["oxygen_update"]["applied_factors"])
            assert trace["human.cost"]["outputs"]["options"]
            assert trace["rover.static.terrain_graph"]["outputs"]["edges"] > 0
            assert _call(server, base + "/report.json")[1] == report
            terrain = report["provenance"]["terrain"]
            status, artifact, raw = _call(server, terrain["href"])
            assert status == 200 and sha256(raw).hexdigest() == terrain["sha256"]
            assert artifact["site"]["terrain"] == site["terrain"]
            _, raw_csv, _ = _call(server, base + "/trace.csv")
            assert len(list(csv.DictReader(StringIO(raw_csv.decode())))) == len(trace)
            _, raw_csv, _ = _call(server, base + "/segments.csv")
            segments = list(csv.DictReader(StringIO(raw_csv.decode())))
            rover_return = [row for row in segments if row["platform"] == "rover" and row["option_id"] == "direct_return"]
            direct = plan["rover"]["candidates"][0]
            assert sum(float(row["duration_s"]) for row in rover_return) == pytest.approx(direct["travel_s"])
            assert sum(float(row["gross_energy_j"]) for row in rover_return) == pytest.approx(direct["energy_ledger"]["total_use"])
            assert rover_return[-1]["remaining_j_after_supply"] == str(direct["energy_ledger"]["final_remaining"])
        finally:
            server.shutdown()
            worker.join()
    reopened = ReportStore(database)
    try:
        assert reopened.read(report_id) == report
    finally:
        reopened.close()


def test_trace_can_be_read_before_run_finishes():
    store = ReportStore()
    try:
        with store.run("test", {"request_id": "test"}, {}) as run:
            with run.stage("sample", "deterministic", "method", {"value": 3}) as outputs:
                report = store.read(run.id)
                assert report["status"] == "running"
                assert report["calculation_trace"][0]["status"] == "running"
                outputs["value"] = 6
            assert store.read(run.id)["calculation_trace"][0]["outputs"] == {"value": 6}
            run.finish({"revision": 1})
        assert store.read(run.id)["status"] == "completed"
    finally:
        store.close()
