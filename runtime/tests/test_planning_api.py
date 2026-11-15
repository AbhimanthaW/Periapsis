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


@pytest.mark.parametrize("closures", [[], ["mid"], ["north"], ["mid", "north"], ["north", "mid"]])
@pytest.mark.parametrize("remaining", [0, 54, 55, 60, 70, 74, 75, 89, 90, 100, 109, 110, 200, 86_400])
def test_marswalk_engine_matches_mission_contract(closures, remaining):
    pack = load_pack(FIXTURE, simulation=True)
    mission, marswalk = PlanningService(pack, None), PlanningService(pack, None, engine="marswalk")
    request = PlanRequest.model_validate({**mission.identity, "schema_version": 1, "request_id": "parity",
                                          "closure_ids": closures, "remaining_s": remaining})
    expected, result = mission.plan(request), marswalk.plan(request)
    for key in V1_FIELDS + ("schema_version", "request_id", "route_index_order"):
        assert result[key] == expected[key], key
    scenario = pack.scenario
    checkpoint = scenario["checkpoint"]["cell"]
    shelter = scenario["shelter"]["cell"]
    closed = {tuple(cell) for closure in scenario["closures"] if closure["id"] in closures
              for cell in closure["cells"]}
    for key, start, end in (("direct_return", checkpoint, shelter), ("reverse_control", shelter, checkpoint)):
        assert _route_seconds(result[key]) == _route_seconds(expected[key]), key
        if result[key] is None:
            continue
        # Equal-time ties may pick different cells. Both routes must avoid closures and screened terrain.
        cells = [tuple(cell) for cell in result[key]["cells"]]
        assert cells[0] == tuple(start) and cells[-1] == tuple(end)
        rows, cols = pack.terrain["valid_mask"].shape
        assert all(0 <= row < rows and 0 <= col < cols for row, col in cells)
        assert all(pack.terrain["valid_mask"][cell] and not pack.terrain["screen_excluded_mask"][cell]
                   and cell not in closed for cell in cells)
        assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(cells, cells[1:]))
    assert result["engine"] == "marswalk"
    assert result["marswalk"]["schema"] == "marswalk-plan-v1"
    assert result["marswalk"]["status"] == result["status"]
    json.dumps(result, allow_nan=False)


def test_unknown_engine_is_refused():
    with pytest.raises(ValueError):
        PlanningService(load_pack(FIXTURE, simulation=True), None, engine="astar")


def _service_request(service, **extra):
    from runtime.planning_api import PlanRequest
    return PlanRequest.model_validate({**service.identity, "schema_version": 1, "request_id": "profile",
                                       "closure_ids": [], "remaining_s": 100, **extra})


def test_profile_is_fed_as_data_to_the_marswalk_engine():
    from contracts.pack import PackError
    pack = load_pack(FIXTURE, simulation=True)
    marswalk = PlanningService(pack, None, engine="marswalk")
    control = {"platform": "human", "pace_model": "control_linear", "neighbours": 4}
    assert marswalk.plan(_service_request(marswalk, profile=control))["direct_return"] == \
        marswalk.plan(_service_request(marswalk))["direct_return"]
    tobler = marswalk.plan(_service_request(marswalk, profile={"platform": "human", "v_flat_mps": 0.6}))
    assert tobler["marswalk"]["profile"]["v_flat_mps"] == 0.6
    assert tobler["marswalk"]["site"]["dimensions"]["cell_dx_m"] == 10
    with pytest.raises(PackError) as error:
        marswalk.plan(_service_request(marswalk, profile={"platform": "human", "v_flat_mps": 2.0}))
    assert error.value.code == "INVALID_PROFILE"
    mission = PlanningService(pack, None)
    with pytest.raises(PackError) as error:
        mission.plan(_service_request(mission, profile=control))
    assert error.value.code == "PROFILE_UNSUPPORTED"


def _feed(*messages, required=False, now_utc="2021-02-18T20:43:49Z"):
    feed = {"provenance": "simulated", "required": required, "max_age_s": 600,
            "stations": [{"id": "base-1", "cell": [1, 0]}], "messages": list(messages)}
    return feed if now_utc is None else {**feed, "now_utc": now_utc}


def _wind(value, *, kind="observed", t="2021-02-18T20:40:00Z"):
    return {"station_id": "base-1", "variable": "wind_speed", "value": value, "unit": "m/s", "kind": kind,
            "time_utc": t, "provenance": "simulated"}


def test_weather_is_fed_to_the_marswalk_engine():
    from contracts.pack import PackError
    pack = load_pack(FIXTURE, simulation=True)
    marswalk = PlanningService(pack, None, engine="marswalk")
    calm = marswalk.plan(_service_request(marswalk, weather=_feed(_wind(5))))
    assert calm["recommendation"] == "science-a" and calm["status"] == "OK"
    assert calm["marswalk"]["weather"]["return_now"] is False
    forecast = marswalk.plan(_service_request(marswalk, weather=_feed(_wind(5), _wind(30, kind="forecast"))))
    assert forecast["recommendation"] == "science-a"
    assert any(m.startswith("[ADVISORY]") for m in forecast["marswalk"]["weather"]["crew_messages"])
    windy = marswalk.plan(_service_request(marswalk, weather=_feed(_wind(22))))
    assert windy["status"] == "OK" and windy["recommendation"] == "direct_return"
    assert windy["direct_return"] == calm["direct_return"]
    assert not any(row["feasible"] for row in windy["science"])
    assert windy["marswalk"]["weather"]["return_now"] is True
    lost = marswalk.plan(_service_request(marswalk, weather=_feed(_wind(5, t="2021-02-18T19:00:00Z"),
                                                                   required=True)))
    assert lost["recommendation"] == "direct_return" and lost["marswalk"]["weather"]["link_lost"] is True
    for bad in (_feed(_wind(5), now_utc=None), {**_feed(_wind(5)), "stations": [{"id": "base-1", "cell": [9, 9]}]}):
        with pytest.raises(PackError) as error:
            marswalk.plan(_service_request(marswalk, weather=bad))
        assert error.value.code == "INVALID_WEATHER"
    mission = PlanningService(pack, None)
    with pytest.raises(PackError) as error:
        mission.plan(_service_request(mission, weather=_feed(_wind(5))))
    assert error.value.code == "WEATHER_UNSUPPORTED"


@pytest.mark.parametrize("call", [{"engine": "marswalk"}], indirect=True, ids=["marswalk"])
def test_weather_over_http(call):
    _, site = call("/api/v1/site")
    status, body = call("/api/v1/plan", plan_request(site, remaining_s=100, weather=_feed(_wind(22))))
    assert status == 200 and body["recommendation"] == "direct_return"
    status, body = call("/api/v1/plan", plan_request(site, remaining_s=100, weather=_feed(_wind(5), now_utc=None)))
    assert status == 400 and body["error"] == "INVALID_WEATHER"


@pytest.mark.parametrize("call", [{"engine": "marswalk"}], indirect=True)
def test_invalid_profile_shape_returns_http_error(call):
    _, site = call("/api/v1/site")
    status, result = call("/api/v1/plan", plan_request(site, profile={"platform": []}))
    assert status == 400 and result["error"] == "INVALID_PROFILE"


@pytest.mark.parametrize("call", [{"engine": "marswalk"}], indirect=True)
def test_malformed_weather_returns_a_structured_http_error(call):
    _, site = call("/api/v1/site")
    valid = _feed(_wind(5))
    invalid = [
        [],
        {**valid, "now_utc": "invalid"},
        {**valid, "now_utc": "2021-02-18T20:43:49"},
        {**valid, "stations": [{"id": "base-1", "cell": [1]}]},
        {**valid, "stations": [{"id": "base-1", "cell": [1.5, 0]}]},
        {**valid, "stations": [{"id": [], "cell": [1, 0]}]},
        {**valid, "messages": [{**_wind(5), "variable": []}]},
        {**valid, "max_age_s": True},
    ]
    for weather in invalid:
        status, body = call("/api/v1/plan", plan_request(site, weather=weather))
        assert status == 400 and body["error"] == "INVALID_WEATHER", weather


def test_hazard_endpoint_is_opt_in(call):
    status, body = call("/api/v1/hazard-replay/0")
    assert (status, body["error"]) == (503, "HAZARD_REPLAY_NOT_CONFIGURED")


@pytest.fixture
def hazard_options(tmp_path):
    return {"hazard_model": tmp_path / "missing-model.json"}


@pytest.mark.parametrize("call", ["hazard_options"], indirect=True)
def test_hazard_routes_with_model_artifact_missing(call):
    status, frame = call("/api/v1/hazard-replay/3")
    assert status == 200
    assert frame["weather"]["status"] == "warning"
    assert frame["routes"]["rover"][0]["status"] == "blocked"
    assert frame["forecast"]["status"] == "unavailable"
    assert call("/api/v1/hazard-replay/6")[0] == 404
    assert call("/api/v1/hazard-replay/missing")[0] == 404


def test_regional_evidence_uses_the_atlas_identity_and_capability_gates(call):
    from runtime.planning_api import ROOT

    atlas = json.loads((ROOT / "web/src/atlas/regions.json").read_bytes())
    registry = json.loads((ROOT / "evidence/sites.v1.json").read_bytes())
    for region in atlas["regions"]:
        region_id = region["id"]
        status, response = call(f"/api/v1/regions/{region_id}")
        assert status == 200
        assert response["schema_version"] == 1
        assert response["region_id"] == region_id
        assert 0 <= int(response["anchor_cell_id"].removeprefix("HPX128:")) < 196_608
        assert response["cell_context"] is None
        assert response["tactical_routing"] == "withheld_no_qualified_pack"
        assert response["live_hazards"] == "unavailable_no_qualified_feed"
        if region_id in registry["sites"]:
            site = registry["sites"][region_id]
            evidence = response["local_evidence"]
            assert evidence["query_sha256"] == site["query_sha256"]
            assert evidence["package_sha256"] == site["package_sha256"]
            assert evidence["result"]["package_id"] == site["package_id"]
            assert evidence["result"]["requested"]["eligible"] is False
            assert evidence["result"]["supported_fallback_ids"]
        else:
            assert response["local_evidence"] is None

    status, response = call("/api/v1/regions/unknown")
    assert (status, response["error"]) == (404, "REGION_NOT_FOUND")


@pytest.mark.parametrize("region_id", ["03", "43"])
@pytest.mark.parametrize("field", ["query", "package"])
def test_regional_evidence_rejects_same_version_changed_bytes(tmp_path, region_id, field):
    from shutil import copyfile

    from runtime.planning_api import ROOT
    from runtime.region_evidence import RegionEvidence

    registry_path = "evidence/sites.v1.json"
    registry = json.loads((ROOT / registry_path).read_bytes())
    paths = [registry_path, "web/src/atlas/regions.json"]
    paths.extend(site[key] for site in registry["sites"].values() for key in ("package", "query"))
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / name, target)

    target = tmp_path / registry["sites"][region_id][field]
    data = json.loads(target.read_bytes())
    if field == "query":
        data["requested"]["requirements"][0]["max_native_spacing_m"] = 1234
    else:
        data["products"][0]["native_spacing_m"] = 1234
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Pinned regional evidence changed"):
        RegionEvidence(tmp_path)
