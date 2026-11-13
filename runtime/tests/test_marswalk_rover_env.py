"""Rover mobility (05), environmental models (06) and their budgets/constraints."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
import subprocess
import sys

import numpy as np
import pytest

from contracts.fixtures.generate import build
from runtime.marswalk import MarswalkError, MissionSnapshot, ScreenPolicy, TerrainSupport, build_baseline
from runtime.marswalk import plan_marswalk
from runtime.marswalk.config import RoverProfile, Task
from runtime.marswalk.demo import DEMO_SITE, demo_inputs
from runtime.marswalk.environment import (ACTIVE, CONTEXT_ONLY, INACTIVE, UNVERIFIED, EnvironmentalVariable,
                                          Observation, PowerScenario, activate_environment,
                                          comms_and_forecast_assessment, mars_sun, supply_energy_j,
                                          terrain_illumination)
from runtime.marswalk.errors import (FAIL, INSUFFICIENT_TERRAIN_EVIDENCE, OK, PASS,
                                    RETURN_ENERGY_SEARCH_EXHAUSTED, RETURN_ENERGY_UNVERIFIED,
                                    RETURN_ENVIRONMENT_UNVERIFIED, UNKNOWN)
from runtime.marswalk.mobility import TAG_CLEARANCE, TAG_OK, TAG_REFUSED_GRADE, TAG_UNSUPPORTED
from runtime.marswalk.resources import EnergyPhase, energy_ledger
from runtime.marswalk.rover import MARS_GRAVITY_MPS2, RoverMobility, hypothetical_crew_rover, traction_assessment
from runtime.marswalk.routing import TerrainGraph, available_backends

KWH = 3.6e6


def grid(z, *, cell=5.0, policy=ScreenPolicy()):
    z = np.asarray(z, float)
    support = TerrainSupport.from_affine(z.shape, (cell, 0, 0, 0, -cell, z.shape[0] * cell),
                                         native_spacing_m=cell, pack_id="t", pack_version="1")
    return build_baseline(support, z, np.isfinite(z), policy=policy)


def rover(**changes):
    return replace(hypothetical_crew_rover(), **changes)


def snapshot(b, current, home, *, tasks=(), remaining_s=36_000, reserve_s=0, profile=None, **extra):
    return MissionSnapshot("m", 1, "t", "1", "s", tuple(current), tuple(home), tuple(tasks), (), remaining_s,
                           reserve_s, (), profile or rover(), **extra)


# ------------------------------------------------------------------ 01 rover operating profile
@pytest.mark.parametrize("change", [
    {"drivetrain_efficiency": 0.0}, {"drivetrain_efficiency": 1.5}, {"battery_reserve_j": 30 * KWH},
    {"initial_charge_j": 25 * KWH}, {"source_type": "sourced"}, {"power_source": "nuclear"},
    {"max_incline_deg": 95.0}, {"nominal_speed_mps": 0.0}, {"mass_kg": float("inf")}, {"neighbours": 6},
])
def test_rover_profile_refuses_invalid_records(change):
    with pytest.raises(MarswalkError, match="INVALID_PROFILE"):
        rover(**change)


def test_sourced_rover_needs_a_citation_and_profiles_are_typed():
    assert rover(source_type="sourced", source="team vehicle sheet v2").source_type == "sourced"
    b = grid(np.zeros((5, 5)))
    with pytest.raises(MarswalkError, match="INVALID_PROFILE"):
        snapshot(b, (2, 2), (2, 0), profile="not a profile").validate((5, 5))


# ------------------------------------------------------------------ 05 rover traversal time + energy
def test_rover_limits_are_checked_before_duration():
    z = np.zeros((7, 9))
    z[:, 5:] = np.arange(4) * 5.0 * math.tan(math.radians(30))      # 30 deg ramp in the east
    z[3, 2] += 1.0                                                   # 1 m block on the flat
    b = grid(z)
    g = TerrainGraph(b, RoverMobility(rover(max_incline_deg=20.0, clearance_m=0.35)))
    tag = {(int(s), int(d)): int(t) for s, d, t in zip(g.src, g.dst, g.times.tag)}
    n = lambda r, c: r * 9 + c
    assert tag[(n(3, 6), n(3, 7))] == TAG_REFUSED_GRADE             # too steep
    assert tag[(n(3, 1), n(3, 2))] == TAG_CLEARANCE                  # block taller than clearance
    assert tag[(n(0, 0), n(0, 1))] == TAG_UNSUPPORTED                # border: no 3x3 support
    assert tag[(n(5, 1), n(5, 2))] == TAG_OK
    assert np.isinf(g.times.seconds[g.times.tag != TAG_OK]).all()
    assert np.isinf(g.times.energy_j[g.times.tag != TAG_OK]).all()


def test_rover_time_and_energy_follow_the_declared_physics():
    p = rover(rolling_resistance=0.1, drivetrain_efficiency=0.5, auxiliary_power_w=100.0, max_incline_deg=40.0)
    mob = RoverMobility(p)
    b = grid(np.zeros((5, 5)))
    length, src, dst = np.array([5.0, 5.0, 5.0]), np.array([12, 12, 12]), np.array([13, 13, 13])
    flat, up, down = (mob.edge_times(length, np.array([dz] * 3), src, dst, b) for dz in (0.0, 0.5, -0.5))
    weight = (p.mass_kg + p.payload_kg) * MARS_GRAVITY_MPS2
    assert flat.seconds[0] == pytest.approx(5.0 / p.nominal_speed_mps)
    assert flat.energy_j[0] == pytest.approx(0.1 * weight * 5.0 / 0.5 + 100.0 * 5.0 / p.nominal_speed_mps)
    assert up.energy_j[0] > flat.energy_j[0]
    surface = math.hypot(5.0, 0.5)
    work_down = weight * -0.5 + 0.1 * weight * 5.0             # rolling uses the horizontal component
    expected_down = max(work_down, 0.0) / 0.5 + 100.0 * surface / p.nominal_speed_mps
    assert down.energy_j[0] == pytest.approx(expected_down)
    steep = mob.edge_times(length, np.array([2.5] * 3), src, dst, b)       # net work < 0 downhill is clipped
    steep_down = mob.edge_times(length, np.array([-2.5] * 3), src, dst, b)
    assert steep_down.energy_j[0] == pytest.approx(100.0 * math.hypot(5.0, 2.5) / p.nominal_speed_mps)
    assert steep.energy_j[0] > steep_down.energy_j[0]


def test_traction_is_explicitly_not_calibrated():
    assert traction_assessment()["status"] == "not_calibrated"


# ------------------------------------------------------------------ 07 energy ledger
def test_energy_ledger_prefix_capacity_and_unknown():
    ok = energy_ledger([EnergyPhase("out", "outbound", 2.0, 5.0, 10), EnergyPhase("back", "return", 3.0, 0.0, 10)],
                       initial_j=8.0, reserve_j=4.0, capacity_j=10.0)
    assert ok.check == PASS and [r.remaining_s for r in ok.rows] == [10.0, 7.0] and ok.margin == 3.0
    # supply arriving later in a phase cannot rescue a breach inside it
    late = energy_ledger([EnergyPhase("out", "outbound", 5.0, 100.0, 10)], initial_j=8.0, reserve_j=4.0, capacity_j=10.0)
    assert late.check == FAIL
    missing = energy_ledger([EnergyPhase("out", "outbound", 1.0, None, 10)], initial_j=8.0, reserve_j=4.0, capacity_j=10.0)
    assert missing.check == UNKNOWN and missing.margin is None


# ------------------------------------------------------------------ 06 solar geometry
def test_mars24_sun_matches_known_events():
    start_my36 = mars_sun("2021-02-07T12:00:00Z", 0.0, 0.0)          # Mars Year 36 began on 7 Feb 2021
    assert start_my36.solar_longitude_deg == pytest.approx(0.0, abs=0.5)
    landing = mars_sun("2021-02-18T20:43:49Z", 18.44, 77.45)          # Perseverance touchdown (spacecraft time)
    assert landing.local_mean_solar_time_h == pytest.approx(15.88, abs=0.05)
    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    year = [mars_sun(t0 + timedelta(days=d), 0.0, 0.0) for d in range(0, 700, 3)]
    assert max(s.declination_deg for s in year) == pytest.approx(25.44, abs=0.05)
    assert min(s.heliocentric_distance_au for s in year) == pytest.approx(1.381, abs=0.002)
    noon = min(year, key=lambda s: abs(s.local_true_solar_time_h - 12.0))
    assert noon.elevation_deg == pytest.approx(90 - abs(noon.declination_deg), abs=1.0)


def test_time_inputs_are_strict_utc():
    for bad in ("2021-02-18 20:00", "2021-02-18T20:00:00+05:30", "2012-08-06T05:17:57Z", 1234):
        with pytest.raises(MarswalkError, match="INVALID_TIME"):
            mars_sun(bad, 0, 0)


def test_terrain_illumination_states():
    z = np.zeros((40, 40))
    z[:, 25:27] = 10.0                                                 # 10 m wall 25 m east of the test cell
    b = grid(z)
    cell = (20, 20)

    class Sun:
        def __init__(self, el, az):
            self.elevation_deg, self.azimuth_deg = el, az

        @property
        def above_horizon(self):
            return self.elevation_deg > 0

    assert terrain_illumination(b, [cell], Sun(20, 90))[cell] == "shadow"      # ray reaches 9.1 m at the wall
    assert terrain_illumination(b, [cell], Sun(20, 270))[cell] == "unresolved"
    assert terrain_illumination(b, [cell], Sun(20, 270), horizon_upper_bound_m=10)[cell] == "lit"
    assert terrain_illumination(b, [(20, 0)], Sun(20, 270), horizon_upper_bound_m=10)[(20, 0)] == "unresolved"
    assert terrain_illumination(b, [cell], Sun(1, 270))[cell] == "unresolved"  # leaves grid below the ceiling
    assert terrain_illumination(b, [cell], Sun(-5, 270))[cell] == "night"


# ------------------------------------------------------------------ 06 power availability
def test_power_scenarios():
    curve = PowerScenario("declared_curve", curve=((0, 100.0), (100, 300.0)))
    assert supply_energy_j(curve, 0, 100) == pytest.approx(20_000.0)
    assert supply_energy_j(curve, 0, 200) is None                      # beyond the declared curve
    assert supply_energy_j(PowerScenario("non_solar", constant_w=110.0), 0, 10) == 1100.0
    assert supply_energy_j(PowerScenario("none"), 0, 10) == 0.0
    solar = PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25, atmospheric_transmittance=0.6,
                          horizon_upper_bound_m=0)
    terrain = grid(np.zeros((7, 7)))
    location = dict(baseline=terrain, stationary_cell=(3, 3), lat_deg=18.44, lon_east_deg=77.45)
    assert supply_energy_j(solar, 0, 600) is None                      # needs time and site
    day = supply_energy_j(solar, 0, 600, time_utc="2021-02-18T20:43:49Z", **location)
    night = supply_energy_j(solar, 0, 600, time_utc="2021-02-19T10:00:00Z", **location)
    assert day > 0 and night == pytest.approx(0.0)
    with pytest.raises(MarswalkError, match="INVALID_POWER"):
        PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25)
    with pytest.raises(MarswalkError, match="INVALID_POWER"):
        PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25, atmospheric_transmittance=0.6,
                      orientation="tilted")


# ------------------------------------------------------------------ 06 environmental activation
def test_activation_classes():
    obs = Observation("air_temperature", -60.0, "degC", "2021-03-01T12:00:00Z", "Jezero", "MEDA ATS", "±1 K", "pds:x")
    variables = (
        EnvironmentalVariable("hist", "air_temperature", "historical_context", effect="return_now",
                              authorized_by="ops", observations=(obs,)),
        EnvironmentalVariable("off", "wind", "inactive"),
        EnvironmentalVariable("unauth", "solar_particle_event", "explicit_scenario", effect="return_now"),
        EnvironmentalVariable("pred", "dust", "supported_prediction", effect="return_now", authorized_by="ops"),
        EnvironmentalVariable("drill", "solar_particle_event", "explicit_scenario", effect="return_now",
                              authorized_by="ops", purpose="drill", scenario_id="s"),
        EnvironmentalVariable("window", "dust", "explicit_scenario", effect="return_now", authorized_by="ops",
                              purpose="drill", scenario_id="s", valid_from_utc="2030-01-01T00:00:00Z"),
        EnvironmentalVariable("req", "dust", "historical_context", effect="block_cells", cells=((1, 1),),
                              required=True),
    )
    got = {a.id: a.status for a in activate_environment(variables, scenario_id="s", time_utc="2026-11-14T00:00:00Z")}
    assert got == {"hist": CONTEXT_ONLY, "off": INACTIVE, "unauth": UNVERIFIED, "pred": UNVERIFIED,
                   "drill": ACTIVE, "window": INACTIVE, "req": UNVERIFIED}
    no_time = activate_environment(variables[5:6], scenario_id="s")
    assert no_time[0].status == UNVERIFIED


def test_active_return_now_blocks_science_but_not_the_return():
    baseline, snap = demo_inputs(sep_alert=True)
    result = plan_marswalk(baseline, snap)
    assert result.status == OK and result.recommendation == "direct_return"
    for plan in result.plans[1:]:
        rules = {r: o for r, o, _ in plan.constraints}
        assert rules["environment"] == FAIL
    assert "environment" not in {r for r, _, _ in result.plans[0].constraints}


def test_required_unverified_environment_leaves_science_unknown():
    baseline, snap = demo_inputs()
    pending = EnvironmentalVariable("dust-check", "dust", "supported_prediction", effect="return_now",
                                    authorized_by="ops", required=True)
    result = plan_marswalk(baseline, replace(snap, environment=(pending,)))
    assert result.recommendation == "direct_return"
    assert {r: o for r, o, _ in result.plan("science:transect").constraints}["environment"] == UNKNOWN


def test_active_block_cells_reroute_like_a_closure():
    b = grid(np.zeros((7, 9)))
    human = MissionSnapshot("m", 1, "t", "1", "s", (3, 0), (3, 8), (), (), 36_000, 0)
    base = plan_marswalk(b, human).direct_leg.seconds
    wall = EnvironmentalVariable("dust-cell", "local_dust", "explicit_scenario", effect="block_cells",
                                 authorized_by="ops", purpose="closure drill", scenario_id="s",
                                 cells=tuple((r, 4) for r in range(1, 7)))
    after = plan_marswalk(b, replace(human, environment=(wall,)))
    assert after.direct_leg.seconds > base and (3, 4) not in after.direct_leg.cells


def test_comms_and_forecasts_are_explicitly_not_modelled():
    out = comms_and_forecast_assessment()
    assert out["communications"]["status"] == out["weather_forecast"]["status"] == "not_modelled"


# ------------------------------------------------------------------ rover plans end to end
def test_rover_demo_plan_has_energy_and_solar_context():
    baseline, snap = demo_inputs(platform="rover", closed=True)
    result = plan_marswalk(baseline, snap)
    assert result.status == OK and result.recommendation is not None
    for plan in result.plans:
        if plan.passed:
            assert plan.energy_ledger.check == PASS and plan.energy_ledger.total_use > 0
    out = result.to_dict()
    assert out["platform"] == "rover" and out["profile"]["source_type"] == "hypothetical"
    assert out["profile"]["traction"]["status"] == "not_calibrated"
    assert out["environment"]["solar"]["status"] == "computed"
    assert "energy_j" in out["objectives_used"]


def test_rover_without_power_scenario_cannot_be_recommended():
    baseline, snap = demo_inputs(platform="rover")
    result = plan_marswalk(baseline, replace(snap, power=None))
    rules = {r: (o, why) for r, o, why in result.plans[0].constraints}
    assert rules["energy_budget"][0] == UNKNOWN and "no power scenario" in rules["energy_budget"][1]
    assert result.recommendation is None and result.status == RETURN_ENERGY_UNVERIFIED


def test_low_battery_blocks_science_before_the_return():
    baseline, snap = demo_inputs(platform="rover")
    p = snap.profile
    direct = plan_marswalk(baseline, snap).plan("direct_return").energy_ledger.total_use
    tight = replace(p, initial_charge_j=p.battery_reserve_j + direct * 1.05)
    result = plan_marswalk(baseline, replace(snap, profile=tight, power=PowerScenario("none")))
    assert result.plans[0].passed and result.recommendation == "direct_return"
    assert all(not plan.passed for plan in result.plans[1:])


def test_human_plans_are_unchanged_by_the_new_inputs():
    baseline, snap = demo_inputs(closed=True, with_time=False)
    plain = plan_marswalk(baseline, snap)
    assert plain.recommendation == "science:photo-set"
    assert all(p.energy_ledger is None for p in plain.plans)
    assert plain.to_dict()["environment"]["solar"]["status"] == "not_declared"
    assert DEMO_SITE == (18.44, 77.45)



def test_solar_dwell_in_shadow_or_unknown_horizon_earns_no_charge(monkeypatch):
    from runtime.marswalk import environment

    sun = environment.SunPosition("2021-02-18T20:43:49Z", 0, 0, 1, 12, 12, 20, 90, 500)
    monkeypatch.setattr(environment, "mars_sun", lambda *args: sun)
    z = np.zeros((9, 13))
    z[:, 8] = 10
    b = grid(z)
    power = PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25,
                          atmospheric_transmittance=0.6, horizon_upper_bound_m=10)
    context = dict(time_utc=sun.time_utc, lat_deg=0, lon_east_deg=0, baseline=b)
    assert supply_energy_j(power, 0, 120, stationary_cell=(4, 6), **context) == 0
    assert supply_energy_j(power, 0, 120, stationary_cell=(4, 11), **context) == 0
    assert supply_energy_j(power, 0, 120, **context) == 0
    assert supply_energy_j(power, 0, 120, stationary_cell=(4, 1), max_charge_w=25, **context) == 3000


@pytest.mark.parametrize("kwargs", [
    dict(kind="non_solar", constant_w=float("inf")),
    dict(kind="non_solar", constant_w=float("nan")),
    dict(kind="declared_curve", curve=((0, 1), (0, 2))),
    dict(kind="declared_curve", curve=((0, 1), (float("inf"), 2))),
    dict(kind="declared_curve", curve=((0, 1), (1, float("nan")))),
    dict(kind="solar_derived", panel_area_m2=float("inf"), panel_efficiency=0.3, atmospheric_transmittance=0.6),
])
def test_nonfinite_or_ambiguous_power_is_refused(kwargs):
    with pytest.raises(MarswalkError, match="INVALID_POWER"):
        PowerScenario(**kwargs)


def test_rover_source_must_match_declared_supply():
    b = grid(np.zeros((5, 5)))
    snap = snapshot(b, (2, 1), (2, 3), profile=rover(power_source="none"),
                    power=PowerScenario("non_solar", constant_w=500))
    with pytest.raises(MarswalkError, match="INVALID_POWER"):
        plan_marswalk(b, snap)


def test_rover_rejects_excess_discharge_and_missing_power_ratings():
    b = grid(np.zeros((5, 5)))
    snap = snapshot(b, (2, 1), (2, 3), profile=rover(max_discharge_w=200), power=PowerScenario("none"))
    result = plan_marswalk(b, snap)
    assert result.direct_leg.ok and result.recommendation is None
    assert result.status == RETURN_ENERGY_SEARCH_EXHAUSTED
    assert "discharge power exceeded" in result.plans[0].energy_ledger.reason
    missing = plan_marswalk(b, replace(snap, profile=rover(max_discharge_w=None)))
    assert missing.status == RETURN_ENERGY_UNVERIFIED


@pytest.mark.parametrize("backend", available_backends())
def test_slower_flat_return_is_feasible_when_fastest_climb_is_not(backend):
    z = np.zeros((7, 9))
    z[3, 4] = 0.4
    b = grid(z)
    p = rover(neighbours=4, rolling_resistance=0.005, auxiliary_power_w=1, clearance_m=1)
    snap = snapshot(b, (3, 1), (3, 7), profile=p, power=PowerScenario("none"))
    fast = plan_marswalk(b, snap, backend=backend)
    assert (3, 4) in fast.direct_leg.cells
    available = fast.direct_leg.energy_j * 0.6
    tight = replace(snap, profile=replace(p, initial_charge_j=p.battery_reserve_j + available))
    result = plan_marswalk(b, tight, backend=backend)
    assert result.recommendation == "direct_return"
    assert result.direct_leg.seconds > fast.direct_leg.seconds
    assert result.direct_leg.energy_j < available
    assert (3, 4) not in result.direct_leg.cells
    assert result.direct_gate.travel_s == result.direct_leg.seconds


def test_prediction_and_short_or_wrong_scope_scenario_cannot_activate():
    b, snap = demo_inputs()
    common = dict(effect="return_now", purpose="dust drill", authorized_by="ops",
                  scenario_id=snap.scenario_id, required=True)
    prediction = EnvironmentalVariable("prediction", "dust", "supported_prediction", validation_ref="unverified",
                                       cells=((1, 1),), **common)
    short = EnvironmentalVariable("short", "dust", "explicit_scenario",
                                  valid_to_utc="2021-02-18T20:45:00Z", **common)
    wrong = replace(short, id="wrong", scenario_id="another-site", valid_to_utc=None)
    for variable in (prediction, short, wrong, replace(short, valid_to_utc=None, purpose=" ")):
        result = plan_marswalk(b, replace(snap, environment=(variable,)))
        assert result.activations[0].status == UNVERIFIED
        assert dict((r, o) for r, o, _ in result.plans[1].constraints)["environment"] == UNKNOWN


def test_rover_border_stencil_is_unknown_terrain_and_renders_no_path():
    b = grid(np.zeros((5, 5)))
    result = plan_marswalk(b, snapshot(b, (2, 0), (2, 3), power=PowerScenario("none")))
    assert result.status == INSUFFICIENT_TERRAIN_EVIDENCE
    assert not result.direct_leg.cells


def test_pre_2017_observation_is_context_without_extending_solar_model():
    when = "2012-08-06T05:17:57Z"
    obs = Observation("dose_rate", 1, "mGy/day", when, "Gale", "RAD", "unknown", "pds:fixture")
    history = EnvironmentalVariable("hist", "dose_rate", "historical_context", observations=(obs,))
    b, snap = demo_inputs()
    out = plan_marswalk(b, replace(snap, time_utc=when, environment=(history,))).to_dict()["environment"]
    assert out["historical_context"][0]["time_utc"] == when
    assert out["solar"]["status"] == "unsupported_epoch"
    with pytest.raises(MarswalkError, match="INVALID_TIME"):
        mars_sun(datetime(2012, 8, 6, tzinfo=timezone.utc), 0, 0)


def test_rover_pack_cli_replans_around_closure(tmp_path):
    pack = tmp_path / "rover-pack"
    build(pack, rover=True)
    command = [sys.executable, "-m", "runtime.marswalk", "plan", str(pack),
               "--platform", "rover", "--power", "battery-only"]
    baseline = json.loads(subprocess.check_output(command))
    replanned = json.loads(subprocess.check_output([*command, "--closure", "mid"]))
    assert baseline["status"] == replanned["status"] == OK
    assert baseline["recommendation"] == replanned["recommendation"] == "science:science-a"
    assert [3, 4] in baseline["direct_return"]["cells"]
    assert [3, 4] not in replanned["direct_return"]["cells"]
    assert replanned["direct_return"]["seconds"] > baseline["direct_return"]["seconds"]



def test_shaded_dwell_cannot_fund_return(monkeypatch):
    from runtime.marswalk import environment

    sun = environment.SunPosition("2021-02-18T20:43:49Z", 0, 0, 1, 12, 12, 20, 90, 500)
    monkeypatch.setattr(environment, "mars_sun", lambda *args: sun)
    power = PowerScenario("solar_derived", panel_area_m2=6, panel_efficiency=0.25,
                          atmospheric_transmittance=0.6, horizon_upper_bound_m=10)
    profile = rover(auxiliary_power_w=0, science_power_w=0, rolling_resistance=0.02,
                    battery_capacity_j=20_000, battery_reserve_j=1000, initial_charge_j=3500)
    task = Task("measure", (4, 6), 120, 1)
    flat = grid(np.zeros((9, 13)))
    snap = snapshot(flat, (4, 4), (4, 2), profile=profile, tasks=(task,), time_utc=sun.time_utc,
                    site_lat_deg=0, site_lon_east_deg=0, power=power)
    lit = plan_marswalk(flat, snap)
    assert lit.recommendation == "science:measure"

    z = np.zeros((9, 13))
    z[:, 8] = 10
    shaded = plan_marswalk(grid(z), snap)
    assert shaded.recommendation == "direct_return"
    assert shaded.plan("science:measure").energy_ledger.check == FAIL



def test_required_unknown_closure_prevents_a_return_recommendation():
    b, snap = demo_inputs()
    closure = EnvironmentalVariable("forecast-closure", "dust", "supported_prediction", effect="block_cells",
                                    cells=((1, 1),), required=True, validation_ref="unverified")
    result = plan_marswalk(b, replace(snap, environment=(closure,)))
    assert result.direct_leg.ok and result.recommendation is None
    assert result.status == RETURN_ENVIRONMENT_UNVERIFIED
    assert {r: o for r, o, _ in result.plans[0].constraints}["environment"] == UNKNOWN
