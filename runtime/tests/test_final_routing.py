from datetime import timedelta
import http.client
import json
from pathlib import Path
from threading import Thread

import pytest

from runtime.marswalk.environment import SOL_S, parse_utc
from runtime.marswalk.forecast import ForecastModel, MARS_HOUR_S, local_time
from runtime.planning_api import create_server
from runtime.tests.tradeoff_world import policy_data, telemetry_data

ROOT = Path(__file__).resolve().parents[2]
PLANS = "/api/v1/routing/plan"


@pytest.fixture(scope="module")
def forecast_artifact(tmp_path_factory):
    with pytest.MonkeyPatch.context() as paths:
        paths.syspath_prepend(str(ROOT / "pipeline/src"))
        from return_window_pipeline.forecast.model import build_artifact
        from return_window_pipeline.forecast.station import to_grid
        from return_window_pipeline.forecast.synthetic import synthetic_rows

    station = json.loads((ROOT / "pipeline/examples/weather/synthetic-station.json").read_text())
    artifact = build_artifact(to_grid(synthetic_rows(1050), 24, station))
    target = tmp_path_factory.mktemp("forecast") / "model.json"
    target.write_text(json.dumps(artifact, allow_nan=False))
    return target


@pytest.fixture
def routing_http(forecast_artifact):
    with create_server(0, final_routing_model=forecast_artifact) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def call(path, body=None):
            with_connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            try:
                if body is None:
                    with_connection.request("GET", path)
                else:
                    with_connection.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
                response = with_connection.getresponse()
                return response.status, json.load(response)
            finally:
                with_connection.close()

        try:
            yield call
        finally:
            server.shutdown()
            worker.join()


def utc(base, seconds):
    return (parse_utc(base) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def reading(var, value, unit, now):
    return {"variable": var, "value": value, "unit": unit, "time_utc": now}


def payload(site, revision, seconds=0, **updates):
    return {key: site[key] for key in ("schema_version", "pack_id", "pack_version")} | {
        "request_id": f"update-{revision}", "expected_revision": revision,
        "time_utc": utc(site["start_time_utc"], seconds), "current_cell": site["current_cell"],
        "objective": "stratigraphy", "confirmed_task_ids": ["transect"],
    } | updates


def station_history(model, start):
    history = [reading("wind_speed", 8, "m/s", start), reading("dust_optical_depth", 0.72, "1", start)]
    for offset in range(3):
        time = utc(start, -offset * MARS_HOUR_S)
        solar = local_time(time, model.station["lon_east_deg"])
        value, _ = model.climatology("pressure_pa", int(solar["ltst_h"]), solar["ls_deg"])
        history.append(reading("pressure_pa", value + 3, "Pa", time))
    return history


def test_http_route_changes_for_both_platforms(routing_http, forecast_artifact):
    status, site = routing_http("/api/v1/routing/site")
    assert status == 200 and site["classification"] == "synthetic"
    assert site["grid"]["shape"] == [160, 160]
    assert site["terrain"]["elevation_m"][130][20] is None
    assert routing_http(PLANS) == (200, {"revision": 0, "plan": None})
    start = site["start_time_utc"]
    model = ForecastModel.load(forecast_artifact)
    initial = payload(site, 0, weather_readings=station_history(model, start))
    status, open_plan = routing_http(PLANS, initial)
    assert status == 200 and open_plan["revision"] == 1
    assert routing_http(PLANS, initial) == (200, open_plan)
    assert open_plan["forecast"]["advisory_only"]
    assert any(row["status"] == "model" for row in open_plan["forecast"]["forecasts"])
    assert open_plan["objective"]["confirmed_task_ids"] == ["transect"]
    assert open_plan["tradeoff"]["return_now"]["class"] == "GREEN"
    assert open_plan["human"]["profile"]["profile_id"] == "human-pair-personalised"
    assert open_plan["human"]["recommendation"] == "science:transect"
    assert open_plan["rover"]["candidates"][0]["energy_ledger"]["unit"] == "J"
    assert open_plan["rover"]["walkback"]["per_plan"]["direct_return"]["slack_s"] > 0

    footprint = site["demo_footprints"]["north-ramp"]
    time = utc(start, 270)
    closure = {"hazard_id": "north-ramp", "revision": 1, "action": "close", "observed_utc": time, "cells": footprint}
    status, closed = routing_http(PLANS, payload(site, 1, 270, hazard_events=[closure], weather_readings=[
        reading("dust_optical_depth", 2.4, "1", time),
    ]))
    assert status == 200 and closed["revision"] == 2
    assert closed["observed_weather"]["no_solar_credit"]
    assert closed["rover"]["environment"]["power"]["atmospheric_transmittance"] == 0
    blocked = set(map(tuple, footprint))
    for platform in ("human", "rover"):
        before, after = open_plan[platform], closed[platform]
        assert blocked.intersection(map(tuple, before["direct_return"]["cells"]))
        assert not blocked.intersection(map(tuple, after["direct_return"]["cells"]))
        assert after["direct_return"]["length_m"] > before["direct_return"]["length_m"]
        assert after["shortest_distance_return"]["length_m"] <= after["direct_return"]["length_m"] + 1e-7
        direct = after["candidates"][0]
        assert direct["eligible_for_recommendation"]
        assert direct["elapsed_sols"] == pytest.approx(direct["elapsed_s"] / SOL_S)

    time = utc(start, 900)
    status, stale = routing_http(PLANS, payload(site, 2, 900, current_cell=[36, 108],
                                                 weather_readings=[reading("wind_speed", 7, "m/s", time)]))
    assert status == 200
    assert stale["observed_weather"]["link_lost"] and stale["observed_weather"]["no_solar_credit"]
    assert stale["hazards"] == closed["hazards"]
    for platform in ("human", "rover"):
        assert stale[platform]["direct_return"]["cells"][0] == [36, 108]
        assert stale[platform]["recommendation"] == "direct_return"

    time = utc(start, 930)
    release = {"hazard_id": "north-ramp", "revision": 2, "action": "clear", "observed_utc": time}
    status, recovered = routing_http(PLANS, payload(site, 3, 930, hazard_events=[release], weather_readings=[
        reading("dust_optical_depth", 0.68, "1", time),
    ]))
    assert status == 200 and recovered["hazards"] == []
    assert not recovered["observed_weather"]["link_lost"]
    assert recovered["rover"]["environment"]["power"]["atmospheric_transmittance"] == 0.6
    assert recovered["human"]["direct_return"]["length_m"] == open_plan["human"]["direct_return"]["length_m"]
    assert routing_http(PLANS, payload(site, 3, 930))[0] == 409
    assert routing_http(PLANS, payload(site, 4, 931, hazard_events=[closure]))[0] == 409
    assert routing_http(PLANS) == (200, {"revision": 4, "plan": recovered})


def test_conflicting_updates_and_current_stores(routing_http):
    _, site = routing_http("/api/v1/routing/site")
    time = site["start_time_utc"]
    stale_earlier = utc(time, -10)
    observations = [
        reading("wind_speed", 8, "m/s", time),
        reading("dust_optical_depth", 0.68, "1", time),
        reading("dust_optical_depth", 2.4, "1", stale_earlier),
    ]
    assert routing_http(PLANS, payload(site, 0, objective="no stratigraphy"))[0] == 400
    request = payload(site, 0, weather_readings=observations)
    status, clear = routing_http(PLANS, request)
    assert status == 200
    assert not clear["observed_weather"]["no_solar_credit"]
    assert not clear["observed_weather"]["link_lost"]
    conflicting = payload(site, 1, weather_readings=[reading("dust_optical_depth", 2.5, "1", time)])
    status, error = routing_http(PLANS, conflicting)
    assert (status, error["error"]) == (409, "WEATHER_CONFLICT")

    stores = {
        "EV1": {"oxygen": 750, "cooling_water": 2.2, "drinking_water": 1.5, "battery": 650},
        "EV2": {"oxygen": 250, "cooling_water": 2.2, "drinking_water": 1.5, "battery": 650},
    }
    status, limited = routing_http(PLANS, payload(site, 1, crew_stores=stores))
    assert status == 200 and limited["revision"] == 2
    assert limited["human"]["status"] == "RETURN_RESOURCE_LIMIT"
    assert limited["human"]["recommendation"] is None
    assert limited["human"]["direct_return"]["status"] == "ok"
    assert limited["tradeoff"]["return_now"]["class"] == "RED"
    assert limited["rover"]["status"] == "RETURN_WALKBACK_EXCEEDED"
    assert limited["rover"]["recommendation"] is None
    checks = {item["rule"]: item["outcome"] for item in limited["rover"]["candidates"][0]["constraints"]}
    assert checks["energy_budget"] == checks["walkback"] == "pass"
    assert checks["walkback_resources"] == "fail"

    closure = {"hazard_id": "shelter-dust", "revision": 1, "action": "close", "observed_utc": time,
               "cells": [site["shelter_cell"]]}
    status, blocked = routing_http(PLANS, payload(site, 2, hazard_events=[closure]))
    assert status == 200
    for platform in ("human", "rover"):
        assert blocked[platform]["status"] == "NO_RETURN_ROUTE"
        assert blocked[platform]["recommendation"] is None
        assert blocked[platform]["direct_return"]["cells"] == []


def test_amber_science_requires_separate_acceptance(routing_http):
    _, site = routing_http("/api/v1/routing/site")
    time = site["start_time_utc"]
    status, nominal = routing_http(PLANS, payload(site, 0, weather_readings=[
        reading("wind_speed", 8, "m/s", time), reading("dust_optical_depth", 0.72, "1", time),
    ]))
    assert status == 200
    science = nominal["tradeoff"]["assessments"][1]
    ev1 = next(item for item in science["per_astronaut"] if item["id"] == "EV1")
    margin = next(row["margin_l1"] for row in ev1["resources"] if row["resource"] == "battery")
    telemetry = telemetry_data(ROOT / "runtime/examples/crew-human-factors.json", policy_data(), observed_utc=time)
    stores = {
        "EV1": {"oxygen": 750, "cooling_water": 2.2, "drinking_water": 1.5, "battery": 650 - margin - 5},
        "EV2": {"oxygen": 700, "cooling_water": 2.2, "drinking_water": 1.5, "battery": 650},
    }
    status, amber = routing_http(PLANS, payload(
        site, 1, crew_stores=stores, telemetry=telemetry, decision_window_s=1800, one_way_light_time_s=600,
    ))
    assert status == 200
    assert amber["tradeoff"]["assessments"][1]["class"] == "AMBER"
    assert amber["tradeoff"]["assessments"][1]["requires_acceptance"]
    assert not amber["human"]["candidates"][1]["eligible_for_recommendation"]
    assert amber["human"]["recommendation"] == "direct_return"


def test_three_predictive_models_and_three_deterministic_models_share_a_plan(routing_http, forecast_artifact):
    _, site = routing_http("/api/v1/routing/site")
    time = site["start_time_utc"]
    model = ForecastModel.load(forecast_artifact)
    objective = "measure bedding thickness along the traverse"
    history = station_history(model, time)
    telemetry = telemetry_data(ROOT / "runtime/examples/crew-human-factors.json", policy_data(), observed_utc=time,
                               scale=1.29)
    # Unknown to the lexicon. Without confirmation the suggestion changes no tasks.
    status, offered = routing_http(PLANS, payload(
        site, 0, objective=objective, confirmed_task_ids=[], weather_readings=history,
    ))
    assert status == 200
    assert not offered["objective"]["interpretation"]["concepts"]
    assert not offered["objective"]["interpretation"]["unsupported"]
    assert offered["objective"]["requires_confirmation"] == ["transect"]
    assert offered["human"]["recommendation"] == "direct_return"
    baseline_margin = offered["tradeoff"]["assessments"][0]["per_astronaut"][0]["resources"][0]["margin_l1"]

    status, learned = routing_http(PLANS, payload(site, 1, objective=objective, telemetry=telemetry))
    assert status == 200
    assert learned["objective"]["prediction"]["suggested_task_id"] == "transect"
    assert learned["human"]["recommendation"] == "science:transect"
    assert any(row["status"] == "model" for row in learned["forecast"]["forecasts"])
    update = learned["tradeoff"]["model"]["oxygen_update"]
    assert update["status"] == "updated" and update["applied_factors"]["EV1"] > 1.3
    margin = learned["tradeoff"]["assessments"][0]["per_astronaut"][0]["resources"][0]["margin_l1"]
    assert margin < baseline_margin

    # The storm starts outside the north ramp. Its swept footprint intersects
    # the original return path while the crew is travelling through the window.
    storm = {"storm_id": "moving", "kind": "observed", "observed_utc": time, "centre_m": [475, 750],
             "velocity_mps": [0.0, -0.35], "radius_m": 25, "wind_mps": 24, "dust_tau": 2.4}
    spatial = {"feed_id": "integrated-storm", "storms": [storm]}
    status, guarded = routing_http(PLANS, payload(
        site, 2, objective=objective, telemetry=telemetry, live_hazards=spatial,
    ))
    assert status == 200
    assert guarded["tradeoff"]["model"]["oxygen_update"]["applied_factors"] == update["applied_factors"]
    possible = set(map(tuple, guarded["spatial_hazards"]["blocked_for_plan"]))
    immediate = set(map(tuple, guarded["spatial_hazards"]["blocked_now"]))
    assert possible > immediate
    for platform in ("human", "rover"):
        old = set(map(tuple, learned[platform]["direct_return"]["cells"]))
        assert old.isdisjoint(immediate)
        assert not old.isdisjoint(possible)
        assert guarded[platform]["direct_return"]["status"] == "ok"
        assert possible.isdisjoint(map(tuple, guarded[platform]["direct_return"]["cells"]))
        assert guarded[platform]["direct_return"]["cells"] != learned[platform]["direct_return"]["cells"]
    assert guarded["rover"]["environment"]["power"]["atmospheric_transmittance"] == 0
    checks = {item["rule"]: item["outcome"] for item in guarded["rover"]["candidates"][0]["constraints"]}
    assert checks["energy_budget"] == checks["walkback_resources"] == "pass"

    # A forecast of the same storm is a different channel. It cannot clear
    # the observed swept mask, even when it claims a newer, clear position.
    later = utc(time, 1)
    forecast = storm | {"kind": "forecast", "observed_utc": later, "wind_mps": 1, "dust_tau": 0.1}
    status, held = routing_http(PLANS, payload(site, 3, 1, objective=objective,
                                               live_hazards=spatial | {"storms": [forecast]}))
    assert status == 200 and held["spatial_hazards"]["blocked_for_plan"]
    assert held["tradeoff"]["model"]["oxygen_update"]["applied_factors"] == update["applied_factors"]


def test_forecast_failure_leaves_hard_hazard_and_return_checks_active(routing_http, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ValueError("broken forecast artifact")

    monkeypatch.setattr("runtime.final_routing.issue_forecast", unavailable)
    _, site = routing_http("/api/v1/routing/site")
    time = site["start_time_utc"]
    status, plan = routing_http(PLANS, payload(
        site, 0, weather_readings=[reading("wind_speed", 8, "m/s", time),
                                   reading("dust_optical_depth", 0.72, "1", time)],
        live_hazards={"feed_id": "sep-alert", "alerts": [{
            "alert_id": "sep", "start_utc": utc(time, 900), "end_utc": None, "observed_utc": time,
        }]},
    ))
    assert status == 200
    assert plan["forecast"]["status"] == "unavailable"
    assert plan["spatial_hazards"]["radiation_in_window"]
    assert plan["human"]["recommendation"] == plan["rover"]["recommendation"] == "direct_return"
    assert plan["tradeoff"]["assessments"][1]["class"] == "RED"
