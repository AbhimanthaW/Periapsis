"""Phase 0 site gates, JSON-fed profiles, rover walkback, weather feed and search horizon."""
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import pytest

from runtime.marswalk import (HumanProfile, MarswalkError, MissionSnapshot, PowerScenario, ScreenPolicy,
                              TerrainSupport, build_baseline, plan_marswalk)
from runtime.marswalk import site as site_module
from runtime.marswalk.__main__ import main
from runtime.marswalk.config import Task
from runtime.marswalk.demo import DEMO_TIME_UTC, demo_inputs
from runtime.marswalk.errors import (FAIL, GRID_TOO_LARGE, LEG_SEARCH_LIMIT, NO_TERRAIN_EVIDENCE, OK, PASS, RETURN_WALKBACK_EXCEEDED,
                                     TERRAIN_NOT_AVAILABLE, TERRAIN_TOO_COARSE, UNKNOWN)
from runtime.marswalk.profiles import load_profile, profile_to_dict
from runtime.marswalk.rover import hypothetical_crew_rover
from runtime.marswalk.site import (SiteDimensions, arcadia_context, arcadia_gate, check_site, evidence_verdict,
                                   gate_for_support, healpix_dimensions, healpix_gate, jezero_gate)
from runtime.marswalk.walkback import WalkbackPolicy, breakdown_snapshot
from runtime.marswalk.weather import (ADVISORY, CAUTION, LINK_LOST, NOMINAL, REJECTED, STALE, WARNING, WeatherFeed,
                                      WeatherMessage, WeatherStation, assess_weather, feed_from_dict, without_solar)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def rule(plan, name):
    return next((outcome, reason) for r, outcome, reason in plan.constraints if r == name)


# ------------------------------------------------------------------ Phase 0
def test_dimensions_come_from_the_affine():
    baseline, _ = demo_inputs()
    gate = gate_for_support(baseline.support, clearance_m=0.35)
    d = gate.dimensions
    assert (d.rows, d.cols, d.cells, d.cell_dx_m, d.cell_dy_m) == (160, 160, 25_600, 5.0, 5.0)
    assert (d.width_m, d.height_m) == (800.0, 800.0)
    assert gate.routable and gate.code is None
    assert gate.obstacle_visibility["status"] == "not_observable"     # 15 m features vs 0.35 m clearance


def test_coarse_grid_is_refused_before_routing():
    z = np.zeros((6, 6))
    support = TerrainSupport.from_affine(z.shape, (25, 0, 0, 0, -25, 150), native_spacing_m=25,
                                         pack_id="coarse", pack_version="1")
    baseline = build_baseline(support, z, np.ones(z.shape, bool))
    snapshot = MissionSnapshot("m", 1, "coarse", "1", "s", (2, 2), (3, 3), (), (), 3600, 900)
    with pytest.raises(MarswalkError) as error:
        plan_marswalk(baseline, snapshot)
    assert error.value.code == TERRAIN_TOO_COARSE


def test_size_and_availability_gates():
    big = SiteDimensions(cells=1_048_576, cell_dx_m=20, cell_dy_m=20, native_spacing_m=20, rows=1024, cols=1024)
    gate = check_site("big", big)
    assert gate.code == GRID_TOO_LARGE and not gate.routable
    small = replace(big, cells=10_000, rows=100, cols=100)
    assert check_site("small", small).routable
    gate = check_site("small", small, terrain_available="preview only")
    assert gate.code == TERRAIN_NOT_AVAILABLE
    with pytest.raises(MarswalkError) as error:
        gate.require()
    assert error.value.code == TERRAIN_NOT_AVAILABLE


def test_arcadia_mola_is_refused_with_real_dimensions():
    support, z, valid, verdict = arcadia_context()
    assert support.shape == (11, 11)
    assert support.cell_dx_m == pytest.approx(9717.5, abs=1) and support.cell_dy_m == pytest.approx(14817.8, abs=1)
    assert verdict.eligible is False and verdict.fallback_ids == ("coarse_elevation_context",)
    gate = arcadia_gate(clearance_m=0.35)
    assert gate.code == NO_TERRAIN_EVIDENCE
    outcomes = {name: outcome for name, outcome, _ in gate.checks}
    assert outcomes == {"evidence": FAIL, "resolution": FAIL, "size": PASS, "terrain": FAIL}
    baseline = build_baseline(support, z, valid)
    snapshot = MissionSnapshot("m", 1, support.pack_id, support.pack_version, "s", (5, 7), (5, 5), (), (), 3600, 900)
    with pytest.raises(MarswalkError) as error:
        plan_marswalk(baseline, snapshot, evidence=verdict)
    assert error.value.code == NO_TERRAIN_EVIDENCE


def test_jezero_control_evidence_passes_but_routing_is_refused():
    gate = jezero_gate(clearance_m=0.35)
    outcomes = {name: outcome for name, outcome, _ in gate.checks}
    assert outcomes == {"evidence": PASS, "resolution": PASS, "size": FAIL, "terrain": FAIL}
    assert gate.evidence.native_spacing_m == 20.0
    assert gate.dimensions.cells == 1_048_576 and gate.code == GRID_TOO_LARGE


def test_jezero_window_crop_analysis(tmp_path, monkeypatch):
    y, x = np.mgrid[0:1024, 0:1024].astype("<f4")
    data = (x * np.float32(20 * math.tan(math.radians(10)))).astype("<f4").tobytes()
    window = tmp_path / "jezero-elevation.f32"
    window.write_bytes(data)
    with pytest.raises(MarswalkError):
        jezero_gate(window=window)                                   # wrong digest is refused
    monkeypatch.setattr(site_module, "JEZERO_WINDOW_SHA256", sha256(data).hexdigest())
    gate = jezero_gate(window=window, crop=(100, 100, 50, 50))
    assert gate.dimensions.cells == 2_500
    assert {n: o for n, o, _ in gate.checks}["size"] == PASS
    assert gate.code == TERRAIN_NOT_AVAILABLE                         # contract v1: preview only
    assert gate.data["crop_analysis"]["slope_deg"]["median"] == pytest.approx(10, abs=0.01)
    with pytest.raises(MarswalkError):
        jezero_gate(window=window, crop=(1000, 0, 50, 50))


def test_healpix_cells_are_not_terrain():
    d = healpix_dimensions()
    assert d.cells == 196_608 and d.cell_m == pytest.approx(27_098, rel=1e-3)
    assert healpix_gate().code == TERRAIN_TOO_COARSE


def test_evidence_result_must_be_a_capability_result():
    with pytest.raises(MarswalkError) as error:
        evidence_verdict({"requested": {}})
    assert error.value.code == "INVALID_EVIDENCE"


# ------------------------------------------------------------------ profiles as data
def test_example_profiles_round_trip():
    assert load_profile(EXAMPLES / "profile-human.json") == HumanProfile()
    assert load_profile(EXAMPLES / "profile-rover-hypothetical.json") == hypothetical_crew_rover()
    assert load_profile(EXAMPLES / "profile-human-15deg.json").max_slope_deg == 15.0
    assert load_profile(profile_to_dict(hypothetical_crew_rover())) == hypothetical_crew_rover()


@pytest.mark.parametrize("change, message", [
    ({"mass_kgs": 1}, "unknown"),
    ({"battery_capacity_j": 7.2e7}, "not both"),
    ({"platform": "drone"}, "platform"),
    ({"mass_kg": -5}, "mass_kg"),
])
def test_bad_rover_profiles_are_refused(change, message):
    data = json.loads((EXAMPLES / "profile-rover-hypothetical.json").read_text()) | change
    with pytest.raises(MarswalkError, match=message):
        load_profile(data)


def test_human_speed_above_walk_to_run_limit_is_rejected_not_clamped():
    assert HumanProfile(v_flat_mps=0.97).v_flat_mps == 0.97          # 0.97 x 1.19 = 1.15 m/s
    with pytest.raises(MarswalkError, match="walk-to-run"):
        HumanProfile(v_flat_mps=1.0)


def test_fed_rover_mass_changes_energy():
    rover = hypothetical_crew_rover()
    used = []
    for mass in (rover.mass_kg, rover.mass_kg * 2):
        baseline, snapshot = demo_inputs(platform="rover", with_time=False)
        snapshot = replace(snapshot, profile=replace(rover, mass_kg=mass))
        used.append(plan_marswalk(baseline, snapshot).direct_leg.energy_j)
    assert used[1] > used[0] > 0


def test_human_slope_limit_profile_refuses_steep_edges():
    baseline, snapshot = demo_inputs(with_time=False)
    limited = plan_marswalk(baseline, replace(snapshot, profile=HumanProfile(max_slope_deg=1.0)))
    assert limited.status != OK or not limited.plans[0].passed or limited.direct_leg.max_slope_deg <= 1.0


# ------------------------------------------------------------------ rover walkback
def test_rover_walkback_uses_a_third_dijkstra_run():
    baseline, snapshot = demo_inputs(platform="rover", closed=True)
    result = plan_marswalk(baseline, snapshot)
    assert result.status == OK and result.recommendation == "science:transect"
    assert result.dijkstra_runs == result.router.dijkstra_runs + 1
    assert rule(result.plan("science:transect"), "walkback")[0] == PASS
    assert result.to_dict()["walkback"]["policy"]["speed_mps"] == 0.75
    without = plan_marswalk(baseline, snapshot, walkback=None)
    assert without.walkback is None and "walkback" not in dict((r, o) for r, o, _ in without.plans[0].constraints)


def test_walkback_rejects_a_science_trip_the_crew_could_not_walk_back_from():
    baseline, snapshot = demo_inputs(platform="rover", closed=True, remaining_s=3540, with_time=False)
    result = plan_marswalk(baseline, snapshot)
    transect = result.plan("science:transect")
    assert transect.ledger.check == PASS                              # time alone would allow it
    outcome, reason = rule(transect, "walkback")
    assert outcome == FAIL and "beyond B - R" in reason
    assert result.recommendation != "science:transect"


def ramp(angle_deg):
    rows, cols, cell = 9, 15, 5.0
    z = np.tile(np.arange(cols) * cell * math.tan(math.radians(angle_deg)), (rows, 1))
    support = TerrainSupport.from_affine(z.shape, (cell, 0, 0, 0, -cell, rows * cell), native_spacing_m=cell,
                                         pack_id="ramp", pack_version="1")
    baseline = build_baseline(support, z, np.ones(z.shape, bool), policy=ScreenPolicy(slope_limit_deg=30))
    snapshot = MissionSnapshot("m", 1, "ramp", "1", "s", (4, 11), (4, 3), (), (), 3600, 900,
                               profile=hypothetical_crew_rover(), power=PowerScenario("none"))
    return baseline, snapshot


def test_rover_can_drive_where_the_crew_cannot_walk_back():
    baseline, snapshot = ramp(18)                                    # rover limit 20 deg, walking limit 15 deg
    result = plan_marswalk(baseline, snapshot)
    assert result.direct_leg.ok
    assert result.status == RETURN_WALKBACK_EXCEEDED
    assert "no walkable route home" in rule(result.plans[0], "walkback")[1]
    baseline, snapshot = ramp(12)
    assert plan_marswalk(baseline, snapshot).status == OK


def test_breakdown_switches_to_walking_mode():
    baseline, snapshot = demo_inputs(platform="rover", closed=True, with_time=False)
    result = plan_marswalk(baseline, snapshot)
    cell = result.plan("science:transect").legs[0][1].goal
    walking = breakdown_snapshot(snapshot, cell, 720)
    assert walking.profile.platform == "human" and walking.profile.v_flat_mps == 0.75
    assert walking.profile.max_slope_deg == 15.0 and walking.tasks == () and walking.power is None
    assert walking.remaining_s == snapshot.remaining_s - 720 and walking.revision == snapshot.revision + 1
    walk = plan_marswalk(baseline, walking)
    assert walk.status == OK and walk.recommendation == "direct_return"
    with pytest.raises(MarswalkError):
        breakdown_snapshot(snapshot, cell, snapshot.remaining_s + 1)
    with pytest.raises(MarswalkError, match="walk-to-run"):
        WalkbackPolicy(speed_mps=1.2)


# ------------------------------------------------------------------ weather
def feed(*messages, required=False, max_age_s=600):
    return WeatherFeed(stations=(WeatherStation("base-1", (80, 40)),), messages=messages, required=required,
                       max_age_s=max_age_s)


def msg(variable, value, unit, *, kind="observed", t="2021-02-18T20:40:00Z", station="base-1", **kw):
    return WeatherMessage(station, variable, value, unit, kind, t, **kw)


def levels(assessment):
    return [a.level for a in assessment.alerts]


def test_weather_levels():
    now = DEMO_TIME_UTC
    assert levels(assess_weather(feed(msg("wind_speed", 5, "m/s")), now)) == [NOMINAL]
    assert levels(assess_weather(feed(msg("wind_speed", 16, "m/s")), now)) == [CAUTION]
    warning = assess_weather(feed(msg("wind_speed", 21, "m/s")), now)
    assert levels(warning) == [WARNING] and warning.return_now and not warning.link_lost
    forecast = assess_weather(feed(msg("wind_speed", 30, "m/s"), msg("wind_speed", 30, "m/s", kind="forecast")), now)
    assert levels(forecast)[1] == ADVISORY and forecast.return_now           # the observed 30 m/s drives it
    only_forecast = assess_weather(feed(msg("wind_speed", 4, "m/s"), msg("wind_speed", 30, "m/s", kind="forecast")),
                                   now)
    assert not only_forecast.return_now


@pytest.mark.parametrize("message", [
    msg("wind_speed", 5, "km/h"),                       # wrong unit
    msg("wind_speed", 500, "m/s"),                      # outside the sane range
    msg("wind_speed", 5, "m/s", station="base-9"),      # unknown station
    msg("humidity", 5, "%"),                            # no declared limit
    msg("wind_speed", 5, "m/s", t="2021-02-18T22:00:00Z"),   # timestamp in the future
])
def test_bad_weather_messages_are_rejected_never_used(message):
    assessment = assess_weather(feed(message), DEMO_TIME_UTC)
    assert levels(assessment)[0] == REJECTED and assessment.link_lost


def test_stale_feed_is_link_lost_and_fails_closed_when_required():
    old = msg("wind_speed", 5, "m/s", t="2021-02-18T19:00:00Z")
    optional = assess_weather(feed(old), DEMO_TIME_UTC)
    assert STALE in levels(optional) and LINK_LOST in levels(optional)
    assert optional.rule("science")[0] == PASS
    required = assess_weather(feed(old, required=True), DEMO_TIME_UTC)
    assert required.rule("science")[0] == UNKNOWN
    assert required.rule("direct_return")[0] == PASS


def test_dust_warning_removes_solar_credit():
    assessment = assess_weather(feed(msg("dust_optical_depth", 2.5, "1")), DEMO_TIME_UTC)
    assert assessment.no_solar_credit and not assessment.return_now
    solar = PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25, atmospheric_transmittance=0.6)
    assert without_solar(solar).atmospheric_transmittance == 0.0
    assert without_solar(PowerScenario("none")).kind == "none"


def test_wind_warning_forces_return_in_the_plan():
    baseline, snapshot = demo_inputs()
    calm = plan_marswalk(baseline, replace(snapshot, weather=feed(msg("wind_speed", 5, "m/s"))))
    assert calm.recommendation == "science:transect"
    windy = plan_marswalk(baseline, replace(snapshot, weather=feed(msg("wind_speed", 22, "m/s"))))
    assert windy.status == OK and windy.recommendation == "direct_return"
    assert rule(windy.plans[0], "weather")[0] == PASS
    assert all(rule(p, "weather")[0] == FAIL for p in windy.plans[1:])
    assert windy.to_dict()["weather"]["return_now"] is True


def test_weather_needs_a_plan_time():
    baseline, snapshot = demo_inputs(with_time=False)
    with pytest.raises(MarswalkError, match="time_utc"):
        plan_marswalk(baseline, replace(snapshot, weather=feed(msg("wind_speed", 5, "m/s"))))


@pytest.mark.parametrize("name", ["weather-wind-warning.json", "weather-forecast-only.json",
                                  "weather-link-lost.json", "weather-dust-warning.json",
                                  "weather-jezero-meda-replay.json"])
def test_example_weather_feeds_load(name):
    data = json.loads((EXAMPLES / name).read_text())
    assessment = assess_weather(feed_from_dict(data), data.get("now_utc", DEMO_TIME_UTC))
    assert assessment.alerts


def test_meda_replay_is_tagged_historical():
    data = json.loads((EXAMPLES / "weather-jezero-meda-replay.json").read_text())
    assessment = assess_weather(feed_from_dict(data), data["now_utc"])
    assert levels(assessment) == [NOMINAL]
    assert assessment.alerts[0].value == 9.08 and assessment.alerts[0].provenance == "historical_replay"


# ------------------------------------------------------------------ search horizon
def test_search_horizon_keeps_feasible_answers():
    baseline, snapshot = demo_inputs(closed=True, with_time=False)
    full = plan_marswalk(baseline, snapshot, search_horizon=False)
    limited = plan_marswalk(baseline, snapshot, search_horizon=True)
    assert limited.search_horizon_s == snapshot.remaining_s - snapshot.reserve_s
    assert full.search_horizon_s is None and limited.recommendation == full.recommendation
    assert limited.direct_leg.seconds == full.direct_leg.seconds
    for a, b in zip(full.plans, limited.plans):
        if a.passed:
            assert b.passed and b.ledger.total_use == pytest.approx(a.ledger.total_use)
    small = plan_marswalk(baseline, snapshot)                         # auto: off below 250,000 cells
    assert small.search_horizon_s is None


# ------------------------------------------------------------------ CLI
def test_cli_sites_and_breakdown(capsys):
    assert main(["sites", "--json"]) == 0
    gates = {g["site_id"]: g for g in json.loads(capsys.readouterr().out.splitlines()[-1])}
    assert gates["synthetic-demo"]["status"] == "routable"
    assert gates["synthetic-fixture-v1"]["dimensions"]["cell_dx_m"] == 10
    assert gates["arcadia-planitia"]["code"] == NO_TERRAIN_EVIDENCE
    assert gates["jezero-control"]["checks"][0]["outcome"] == PASS
    assert main(["demo", "--platform", "rover", "--rover-fails-at-min", "12"]) == 0
    assert "ROVER FAILS" in capsys.readouterr().out
    assert main(["demo", "--weather", str(EXAMPLES / "weather-wind-warning.json")]) == 0
    assert "[WARNING] wind_speed 22 m/s" in capsys.readouterr().out


def test_phase_zero_checks_native_spacing_and_synthetic_boundary():
    baseline, _ = demo_inputs()
    coarse = replace(baseline.support, native_spacing_m=100)
    assert gate_for_support(coarse).code == TERRAIN_TOO_COARSE
    source_backed = replace(baseline.support, classification="source_backed")
    assert gate_for_support(source_backed).code == TERRAIN_NOT_AVAILABLE
    assert gate_for_support(baseline.support, clearance_m=20).obstacle_visibility["status"] == "not_observable"


def test_outbound_search_limit_keeps_exact_return_and_reports_cutoff():
    baseline, snapshot = demo_inputs(with_time=False)
    snapshot = replace(snapshot, remaining_s=snapshot.reserve_s + 1)
    full = plan_marswalk(baseline, snapshot, search_horizon=False)
    limited = plan_marswalk(baseline, snapshot, search_horizon=True)
    assert full.plan("science:transect").legs[0][1].ok
    assert limited.plan("science:transect").legs[0][1].status == LEG_SEARCH_LIMIT
    assert limited.direct_leg == full.direct_leg


def test_walkback_detail_describes_selected_route():
    baseline, snapshot = demo_inputs(platform="rover", closed=True)
    result = plan_marswalk(baseline, snapshot, alternatives_k=4)
    assert result.recommendation == "science:transect"
    assert rule(result.plan(result.recommendation), "walkback")[0] == PASS
    assert result.walkback["per_plan"][result.recommendation]["slack_s"] >= 0


def test_breakdown_advances_weather_clock_and_preserves_completed_work():
    _, snapshot = demo_inputs(platform="rover", closed=True)
    weather = feed(msg("wind_speed", 22, "m/s"))
    completed = snapshot.tasks[0].id
    snapshot = replace(snapshot, time_utc=DEMO_TIME_UTC, weather=weather, completed_task_ids=(completed,))
    walking = breakdown_snapshot(snapshot, snapshot.current_cell, 601)
    assert walking.completed_task_ids == (completed,)
    assert [task.id for task in walking.tasks] == [completed]
    assert assess_weather(weather, snapshot.time_utc).return_now
    assert assess_weather(weather, walking.time_utc).link_lost


def test_future_observation_cannot_activate_warning():
    forecast_time = "2100-01-01T00:00:01Z"
    warning = replace(msg("wind_speed", 22, "m/s"), time_utc=forecast_time)
    assessment = assess_weather(feed(warning), "2100-01-01T00:00:00Z")
    assert assessment.link_lost and not assessment.return_now
