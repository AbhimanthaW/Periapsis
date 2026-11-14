import http.client
import json
from pathlib import Path
from threading import Thread

import pytest

from runtime.mission import load_pack
from runtime.planning_api import ENGINES, FIXTURE, PlanningService, PlanRequest, create_server


@pytest.fixture
def call(request):
    options = getattr(request, "param", {})
    if isinstance(options, str):
        options = request.getfixturevalue(options)
    with create_server(0, **options) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def request(path, body=None, *, raw=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                if body is None and raw is None:
                    connection.request("GET", path)
                else:
                    connection.request("POST", path, raw if raw is not None else json.dumps(body),
                                       {"Content-Type": "application/json"})
                response = connection.getresponse()
                return response.status, json.load(response)
            finally:
                connection.close()

        try:
            yield request
        finally:
            server.shutdown()
            worker.join()


def plan_request(site, **overrides):
    fields = ("schema_version", "pack_id", "pack_version", "scenario_id", "checkpoint_id",
              "shelter_id", "completed_task_ids", "remaining_s", "reserve_s")
    return {**{key: site[key] for key in fields}, "request_id": "test-1", "closure_ids": [], **overrides}


@pytest.mark.parametrize("call", [{"engine": engine} for engine in ENGINES], indirect=True,
                         ids=list(ENGINES))
def test_http_replay(call):
    assert call("/healthz") == (200, {"status": "ready"})
    status, site = call("/api/v1/site")
    assert status == 200
    assert site["classification"] == "synthetic"
    assert site["grid"]["index_order"] == "row_col"
    cases = [
        ([], 100, "OK", 40, 45, "science-a"),
        (["mid"], 100, "OK", 60, 25, "direct_return"),
        (["mid"], 70, "RETURN_OVER_RESERVE", 60, -5, None),
        (["mid", "north"], 100, "NO_RETURN_ROUTE", None, None, None),
        ([], 100, "OK", 40, 45, "science-a"),
    ]
    for index, (closures, remaining, expected, seconds, margin, recommendation) in enumerate(cases):
        request_id = f"replay-{index}"
        status, result = call("/api/v1/plan", plan_request(
            site, request_id=request_id, closure_ids=closures, remaining_s=remaining,
        ))
        assert status == 200
        assert result["request_id"] == request_id
        assert result["pack_id"] == site["pack_id"]
        assert result["status"] == expected
        assert result["route_index_order"] == "row_col"
        assert (result["direct_return"] or {}).get("seconds") == seconds
        assert result["return_margin_s"] == margin
        assert result["recommendation"] == recommendation
        assert result["completed_task_ids"] == ["survey-done"]


@pytest.mark.parametrize("call", [{"engine": engine} for engine in ENGINES], indirect=True,
                         ids=list(ENGINES))
def test_invalid_requests_and_evidence_boundary(call):
    _, site = call("/api/v1/site")
    for changes, http_status, code in [
        ({"remaining_s": True}, 400, "INVALID_REQUEST"),
        ({"closure_ids": ["mid", "mid"]}, 400, "INVALID_SCENARIO"),
        ({"closure_ids": ["unknown"]}, 400, "INVALID_SCENARIO"),
        ({"completed_task_ids": []}, 409, "SCENARIO_MISMATCH"),
        ({"pack_id": "rw-jezero-preview"}, 409, "SCENARIO_MISMATCH"),
    ]:
        status, result = call("/api/v1/plan", plan_request(site, **changes))
        assert (status, result["error"], result["request_id"]) == (http_status, code, "test-1")
    assert call("/api/v1/plan", raw='{"request_id":"a","request_id":"b"}')[0] == 400
    assert call("/api/v1/plan", raw=" " * 16_385)[0] == 413

    status, evidence = call("/api/v1/evidence")
    assert (status, evidence["error"]) == (503, "EVIDENCE_NOT_CONFIGURED")
    assert "result" not in evidence


JEZERO_CONTROL = Path(__file__).resolve().parents[2] / "evidence/jezero"


@pytest.mark.parametrize("call", [{
    "evidence_package": JEZERO_CONTROL / "jezero-evidence.json",
    "evidence_query": JEZERO_CONTROL / "jezero-route.json",
}], indirect=True)
def test_explicit_evidence_configuration(call):
    status, evidence = call("/api/v1/evidence")
    assert status == 200
    assert evidence["context"] == "operator_configured_evidence"
    assert evidence["classification"] == "provenance_unverified"
    assert evidence["result"]["requested"]["eligible"] is False
    assert evidence["result"]["fallbacks"][0]["eligible"] is True
    assert "direct_return" not in evidence


@pytest.fixture
def synthetic_evidence_options(tmp_path):
    query = {
        "schema_version": 1,
        "geometry": {"type": "Point", "coordinates": [0.002, 0.0032]},
        "requested": {
            "id": "elevation",
            "requirements": [{"variable": "elevation", "product_classes": ["stereo_dtm"]}],
        },
    }
    query_path = tmp_path / "query.json"
    query_path.write_text(json.dumps(query), encoding="utf-8")
    return {"evidence_package": FIXTURE / "evidence.json", "evidence_query": query_path}


@pytest.mark.parametrize("call", ["synthetic_evidence_options"], indirect=True)
def test_eligible_synthetic_evidence_has_unverified_provenance(call):
    status, evidence = call("/api/v1/evidence")
    assert status == 200
    assert evidence["classification"] == "provenance_unverified"
    assert evidence["result"]["requested"]["eligible"] is True


V1_FIELDS = ("pack_id", "pack_version", "scenario_id", "classification", "closure_ids", "remaining_s", "reserve_s",
             "return_margin_s", "completed_task_ids", "science", "recommendation", "status")


def _route_seconds(route):
    return None if route is None else route["seconds"]


@pytest.mark.parametrize("closures", [[], ["mid"], ["north"], ["mid", "north"]])
@pytest.mark.parametrize("remaining", [0, 60, 70, 100, 200])
def test_marswalk_engine_matches_mission_contract(closures, remaining):
    pack = load_pack(FIXTURE, simulation=True)
    mission, marswalk = PlanningService(pack, None), PlanningService(pack, None, engine="marswalk")
    request = PlanRequest.model_validate({**mission.identity, "schema_version": 1, "request_id": "parity",
                                          "closure_ids": closures, "remaining_s": remaining})
    expected, result = mission.plan(request), marswalk.plan(request)
    for key in V1_FIELDS + ("schema_version", "request_id", "route_index_order"):
        assert result[key] == expected[key], key
    for key in ("direct_return", "reverse_control"):
        assert _route_seconds(result[key]) == _route_seconds(expected[key]), key
        if result[key] is not None:    # equal-time ties may pick different cells; the route must still be valid
            cells = result[key]["cells"]
            assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(cells, cells[1:]))
    direct = result["direct_return"]
    if direct is not None:
        assert direct["cells"][0] == list(pack.scenario["checkpoint"]["cell"])
        assert direct["cells"][-1] == list(pack.scenario["shelter"]["cell"])
    assert result["engine"] == "marswalk"
    assert result["marswalk"]["schema"] == "marswalk-plan-v1"
    assert result["marswalk"]["status"] == result["status"]
    json.dumps(result, allow_nan=False)


def test_unknown_engine_is_refused():
    with pytest.raises(ValueError):
        PlanningService(load_pack(FIXTURE, simulation=True), None, engine="astar")
