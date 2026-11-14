"""Invariant tests for the Trade-off Envelope (plan section 10, software-logic row)."""
import copy

import pytest

from runtime.marswalk.errors import MarswalkError
from runtime.tradeoff import accept, is_executable
from runtime.tests.tradeoff_world import (CONSENT, NOW, SIGNATURES, WEATHER, classes, crew_data, envelope_data,
                                          marswalk_plan, never_better, option, policy_data, run)

SCALES = (1.0, 1.05, 1.15, 1.3, 1.6, 2.0)
A = lambda value, unit: {"value": value, "unit": unit, "status": "assumed"}      # noqa: E731


def _sweep(build):
    """Classes along a sweep; a refusal ends the sweep (a refusal offers nothing)."""
    seen = []
    for scale in SCALES:
        try:
            seen.append(classes(build(scale)))
        except MarswalkError:
            break
    return seen


def _monotone_worse(seen):
    return all(never_better(a, b) for a, b in zip(seen, seen[1:]))


# ---------------------------------------------------------------- 1. more consumption never upgrades
@pytest.mark.parametrize("walker", ["EV1", "EV2"])
@pytest.mark.parametrize("field", ["metabolic_baseline_w", "suit_joint_power_w", "drinking_water_l_h", "mass_kg"])
@pytest.mark.parametrize("battery", [155.0, 650.0])
def test_raising_a_crew_consumption_rate_never_upgrades_a_class(walker, field, battery):
    def build(scale):
        crew = crew_data(battery_wh=battery)
        person = next(p for p in crew["astronauts"] if p["id"] == walker)
        person[field] *= scale
        return run(crew=crew)[0]                      # telemetry regenerated from the changed model

    seen = _sweep(build)
    assert len(seen) >= 2 and _monotone_worse(seen)


@pytest.mark.parametrize("key", ["electrical_base_w", "net_external_heat_w", "cooling_electrical_w_per_thermal_w",
                                 "mars_gravity_m_s2"])
def test_raising_a_policy_consumption_term_never_upgrades_a_class(key):
    def build(scale):
        policy = policy_data()
        policy["parameters"][key]["value"] *= scale
        return run(policy=policy)[0]

    seen = _sweep(build)
    assert len(seen) >= 2 and _monotone_worse(seen)


def test_raising_the_margin_factor_never_upgrades_a_class():
    def build(scale):
        envelope = envelope_data()
        envelope["consumption_margin_factor"]["value"] = 1.0 + 0.3 * scale
        return run(envelope=envelope)[0]

    seen = _sweep(build)
    assert len(seen) == len(SCALES) and _monotone_worse(seen)
    assert seen[0]["science:transect"] == "AMBER" and seen[-1]["science:transect"] == "RED"


# ---------------------------------------------------------------- 2. a tighter envelope never adds options
def _tighten_margin(d): d["consumption_margin_factor"]["value"] = 1.45
def _tighten_l2_battery(d): d["exceptions"][0]["reserve_floor_fraction"]["battery"]["value"] = 0.20
def _tighten_l2_oxygen(d): d["exceptions"][0]["reserve_floor_fraction"]["oxygen"]["value"] = 0.30
def _drop_exception(d): d["exceptions"].clear()
def _demote_objective(d): d["objectives"][0]["priority_class"] = 2
def _drop_objective(d): d["objectives"].pop(0)
def _zero_cap(d): d["max_accepted_amber_per_eva"]["value"] = 0
def _short_telemetry_age(d): d["telemetry"]["max_age_s"]["value"] = 10
def _high_min_ratio(d): d["telemetry"]["min_observed_to_nominal_ratio"]["value"] = 1.0
def _tight_tolerance(d): d["telemetry"]["co2_o2_tolerance_fraction"]["value"] = 1e-9
def _long_allowance(d): d["authority"]["response_allowance_s"]["value"] = 36000
def _no_delegate(d): d["authority"]["habitat_delegate"] = None
def _early_expiry(d): d["expires_utc"] = "2021-02-18T20:43:50Z"
def _raise_override(d): d["personal_overrides"][0]["reserve_floor_fraction"]["oxygen"]["value"] = 0.6


def _add_battery_override(d):
    d["personal_overrides"].append({
        "astronaut": "EV1", "reserve_floor_fraction": {"battery": A(0.4, "fraction_of_initial")},
        "set_by": "crew_surgeon", "reason": "simulated", "visibility": "surgeon_only"})


TIGHTENINGS = [_tighten_margin, _tighten_l2_battery, _tighten_l2_oxygen, _drop_exception, _demote_objective,
               _drop_objective, _zero_cap, _short_telemetry_age, _high_min_ratio, _tight_tolerance,
               _long_allowance, _no_delegate, _early_expiry, _raise_override, _add_battery_override]


@pytest.mark.parametrize("tighten", TIGHTENINGS, ids=lambda f: f.__name__.lstrip("_"))
@pytest.mark.parametrize("window_s", [3600, 600])            # Earth reachable / habitat delegate only
@pytest.mark.parametrize("battery", [155.0, 650.0])
def test_tightening_an_envelope_value_never_adds_a_green_or_amber_option(tighten, window_s, battery):
    crew = crew_data(battery_wh=battery)
    before = classes(run(crew=crew, decision_window_s=window_s)[0])
    envelope = envelope_data()
    tighten(envelope)
    try:
        after = classes(run(crew=crew, envelope=envelope, decision_window_s=window_s)[0])
    except MarswalkError:
        return                                               # refused: nothing is offered at all
    assert never_better(before, after)


def test_the_tightenings_do_bite():
    """Guard against a vacuous sweep: several tightenings really remove the AMBER option."""
    assert classes(run()[0])["science:transect"] == "AMBER"
    for tighten in (_tighten_margin, _tighten_l2_battery, _drop_exception, _demote_objective, _zero_cap,
                    _short_telemetry_age, _add_battery_override):
        envelope = envelope_data()
        tighten(envelope)
        assert classes(run(envelope=envelope)[0])["science:transect"] == "RED", tighten.__name__


# ---------------------------------------------------------------- 3. more reserve never lowers a class
@pytest.mark.parametrize("walker", ["EV1", "EV2"])
@pytest.mark.parametrize("store", ["initial_oxygen_g", "initial_cooling_water_kg", "initial_drinking_water_l",
                                   "initial_battery_wh"])
@pytest.mark.parametrize("battery", [60.0, 120.0, 155.0])
def test_adding_reserve_never_moves_an_option_to_a_worse_class(walker, store, battery):
    def build(scale):
        crew = crew_data(battery_wh=battery)
        next(p for p in crew["astronauts"] if p["id"] == walker)[store] *= scale
        return run(crew=crew)[0]

    seen = _sweep(build)
    assert len(seen) == len(SCALES)
    assert all(never_better(later, earlier) for earlier, later in zip(seen, seen[1:]))


def test_adding_battery_to_both_walkers_recovers_green():
    assert classes(run(crew=crew_data(battery_wh=155.0))[0])["science:transect"] == "AMBER"
    assert classes(run(crew=crew_data(battery_wh=650.0))[0])["science:transect"] == "GREEN"


# ---------------------------------------------------------------- 4. RED is never executable
def test_red_is_never_executable_even_with_a_borrowed_acceptance():
    result, envelope = run()
    amber = option(result, "science:transect")
    record = accept(amber, envelope, now_utc=NOW, signatures=SIGNATURES, crew_responses=CONSENT,
                    decision_window_s=3600, one_way_light_time_s=600, prior_accepted_count=0)
    assert record["status"] == "accepted" and is_executable(amber, record, now_utc=NOW)
    reds = [a for a in result["assessments"] if a["class"] == "RED"]
    assert reds
    for red in reds:
        assert not is_executable(red, now_utc=NOW)
        assert not is_executable(red, record, now_utc=NOW)
        forged = {**record, "option_id": red["option_id"]}
        assert not is_executable(red, forged, now_utc=NOW)
        refused = accept(red, envelope, now_utc=NOW, signatures=SIGNATURES, crew_responses=CONSENT,
                         decision_window_s=3600, one_way_light_time_s=600, prior_accepted_count=0)
        assert refused["status"] == "refused" and refused["reason"] == "RED is never executable"


def test_amber_is_not_executable_without_or_after_its_acceptance():
    result, envelope = run()
    amber = option(result, "science:transect")
    assert not is_executable(amber, now_utc=NOW)
    record = accept(amber, envelope, now_utc=NOW, signatures=SIGNATURES, crew_responses=CONSENT,
                    decision_window_s=3600, one_way_light_time_s=600, prior_accepted_count=0)
    assert record["expires_utc"] == "2021-02-18T21:13:49Z"               # now + acceptance_valid_s
    assert is_executable(amber, record, now_utc="2021-02-18T21:13:48Z")
    assert not is_executable(amber, record, now_utc="2021-02-18T21:13:49Z")
    changed = copy.deepcopy(amber)
    changed["per_astronaut"][0]["margin_s"] = 1.0                        # a different assessment
    assert not is_executable(changed, record, now_utc=NOW)
    assert is_executable(option(result, "direct_return"), now_utc=NOW)   # GREEN needs no acceptance


# ---------------------------------------------------------------- 5. return now
@pytest.mark.parametrize("kwargs", [
    {}, {"telemetry": None}, {"decision_window_s": None}, {"accepted": 99},
    {"plan": ("weather", None)}, {"plan": ("crew_status", "issue")}, {"plan": ("remaining_s", 300)},
    {"crew": 650.0}, {"crew": 20.0},
])
def test_direct_return_is_always_present_and_green_whenever_its_constraints_pass(kwargs):
    kwargs = dict(kwargs)
    plan = marswalk_plan()
    if "plan" in kwargs:
        key, value = kwargs.pop("plan")
        plan = (marswalk_plan(weather_json=None) if key == "weather"
                else marswalk_plan(**{key: value}))
    if "crew" in kwargs:
        kwargs["crew"] = crew_data(battery_wh=kwargs["crew"])
    result, _ = run(plan=plan, **kwargs)
    direct = result["assessments"][0]
    assert direct["option_id"] == "direct_return" == result["return_now"]["option_id"]
    assert direct["class"] in ("GREEN", "RED")                           # never AMBER
    reserves_hold = not any(r["reserve_breached_l1"] for p in direct["per_astronaut"] for r in p["resources"])
    expected_green = plan.plans[0].passed and reserves_hold
    assert (direct["class"] == "GREEN") == expected_green
    if expected_green:
        assert result["return_now"]["alert"] is None
    else:
        # said loudly, and nothing else is offered above it
        assert result["return_now"]["alert"].startswith("RETURN NOW IS NOT GREEN")
        assert direct["first_failing_rule"] in result["return_now"]["alert"]
        assert set(classes(result).values()) == {"RED"}


def test_return_now_not_green_cases_are_reached():
    over_time, _ = run(plan=marswalk_plan(remaining_s=300))
    assert over_time["assessments"][0]["first_failing_rule"] == "hard_constraint:time_budget:fail"
    starved, _ = run(crew=crew_data(battery_wh=20.0))
    assert starved["assessments"][0]["first_failing_rule"].startswith("reserve_floor_l1:")
    assert WEATHER["messages"][0]["kind"] == "observed"


def test_bad_inputs_remove_amber_but_never_change_a_green():
    baseline = classes(run()[0])
    for kwargs in ({"telemetry": None}, {"decision_window_s": None}, {"accepted": 2},
                   {"plan": marswalk_plan(weather_json=None)}):
        after = classes(run(**kwargs)[0])
        assert "AMBER" not in after.values()
        assert {k for k, v in after.items() if v == "GREEN"} == {k for k, v in baseline.items() if v == "GREEN"}
