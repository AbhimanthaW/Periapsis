"""Regression checks for the simulated, routing-independent human calculator."""

import json
import math
from pathlib import Path

import pytest

from runtime.humancost import Phase, evaluate, load_crew, load_policy, prepare, serialize
from runtime.humancost.calculator import _demand_ratios
from runtime.marswalk.errors import MarswalkError
from runtime.marswalk.profiles import load_profile


ROOT = Path(__file__).resolve().parents[2]
CREW = ROOT / "runtime/examples/crew-human-factors.json"
POLICY = ROOT / "runtime/examples/human-cost-policy.json"
ROUTE = [Phase("outbound", "outbound", 3600, 40),
         Phase("dwell", "dwell", 1800, 0),
         Phase("return", "return", 3300, 12)]


def fixture_data():
    return json.loads(CREW.read_text()), json.loads(POLICY.read_text())


def default_reserves(policy):
    for resource in ("oxygen", "cooling_water", "battery"):
        policy["parameters"][f"{resource}_raised_fraction"]["value"] = policy["parameters"][f"{resource}_reserve_fraction"]["value"]
    policy["parameters"]["drinking_water_raised_l"]["value"] = policy["parameters"]["drinking_water_reserve_l"]["value"]
    return policy


@pytest.mark.parametrize("change", [
    lambda d: d["astronauts"][0].update(unknown=1),
    lambda d: d["astronauts"][0].pop("mass_kg"),
    lambda d: d["astronauts"][0].update(mass_kg=float("nan")),
    lambda d: d["astronauts"][0].update(mechanical_efficiency=0),
    lambda d: d["astronauts"][0].update(respiratory_exchange_ratio=1.2),
    lambda d: d["astronauts"][1].update(id="REF"),
    lambda d: d.update(reference_id="MISSING"),
    lambda d: d.update(provenance="evidence"),
    lambda d: d["astronauts"][0].update(sustainable_metabolic_w=600),
])
def test_crew_refuses_invalid_data(change):
    data, _ = fixture_data()
    change(data)
    with pytest.raises(MarswalkError, match="INVALID_HUMAN_FACTORS"):
        load_crew(data)


def test_policy_refuses_invalid_thresholds():
    _, policy = fixture_data()
    policy["parameters"]["utilisation_warning"]["value"] = 0.6
    with pytest.raises(MarswalkError, match="INVALID_HUMAN_FACTORS"):
        load_policy(policy)


def test_golden_flat_and_route():
    crew, policy = fixture_data()
    policy = default_reserves(policy)
    before = prepare(crew, policy)
    assert before["routing_inputs"]["remaining_s"] == 12049
    assert before["routing_inputs"]["limited_by"] == {"astronaut": "EV2", "resource": "battery"}
    assert load_profile(before["routing_inputs"]["profile"]).crew_size == 2
    a, b = before["astronauts"]
    assert (a["id"], b["id"]) == ("EV1", "EV2")
    assert (a["budget_s"], b["budget_s"]) == (12534, 12049)
    assert (a["demand_class"], b["demand_class"]) == ("nominal", "elevated")
    assert a["rates_flat_per_h"]["oxygen"] == pytest.approx(65.74, rel=1e-3)
    assert b["rates_flat_per_h"]["oxygen"] == pytest.approx(78.00, rel=1e-3)
    result = evaluate(crew, policy, ROUTE)
    ev1, ev2 = result["astronauts"]
    assert (ev1["risk"], ev1["band"], ev1["driver"]) == (70, "nominal", "battery")
    assert (ev2["risk"], ev2["band"], ev2["driver"]) == (73, "caution", "battery")
    assert result["route"] == {"check": "pass", "risk": 73, "band": "caution", "limited_by": "EV2", "breach": None}
    for person, expected in ((ev1, (2383.804, 166.634, 1.07278, .725, 363.739)),
                             (ev2, (2845.661, 198.022, 1.26378, .845833, 379.019))):
        assert person["metabolic_energy_kj"] == pytest.approx(expected[0], rel=1e-3)
        assert [ledger["total_use"] for ledger in person["ledgers"]] == pytest.approx(expected[1:], rel=1e-3)


def test_raised_reserve_changes_ev2_budget_and_risk():
    original = evaluate(CREW, POLICY, ROUTE)
    assert original["routing_inputs"]["remaining_s"] == 11296
    assert original["route"]["risk"] == 78
    assert original["astronauts"][1]["ledgers"][3]["reserve"] == 162.5


def test_reference_compared_to_itself_is_one():
    crew = load_crew(CREW)
    reference = next(p for p in crew.astronauts if p.id == crew.reference_id)
    assert set(_demand_ratios(reference, reference, load_policy(POLICY)).values()) == {1.0}


def test_fixture_constant_grade_rates_agree():
    from documentation.marsdoc.eva_context import fixture_fields

    scenario = json.loads((ROOT / "documentation/marsdoc/eva/scenario-v1.json").read_text())
    crew, policy = fixture_data()
    person = next(p for p in crew["astronauts"] if p["id"] == "REF")
    person["suit_joint_power_w"] = scenario["suit_joint_torque_nm"] * scenario["suit_joint_angular_speed_rad_s"]
    person["co2_removal_g_s"] = scenario["co2_removal_g_s"]
    speed = scenario["flat_speed_m_s"] * math.exp(-scenario["pace_grade_decay"] * (
        abs(scenario["signed_grade"] + scenario["pace_optimum_downhill_grade"]) - scenario["pace_optimum_downhill_grade"]))
    gain = speed * scenario["signed_grade"] * 1200
    ref = fixture_fields(scenario, 1200)
    # REF is a comparison baseline in the public payload. Evaluate it as a walker.
    crew["reference_id"] = "EV1"
    walker = next(p for p in evaluate(crew, policy, [Phase("outbound", "outbound", 1200, gain)])["astronauts"] if p["id"] == "REF")
    used = {x["resource"]: x["total_use"] for x in walker["ledgers"]}
    assert used["oxygen"] == pytest.approx(ref["oxygen_consumption"]["value"], rel=1e-12)
    assert used["cooling_water"] == pytest.approx(ref["water_consumption"]["cooling_water_used_kg"], rel=1e-12)
    assert used["battery"] == pytest.approx(ref["energy_consumption"]["value"], rel=1e-12)
    assert walker["co2_produced_g"] == pytest.approx(ref["co2_accumulation_removal_load"]["value"], rel=1e-12)


def test_prefix_breach_is_hard_fail_with_phase_and_resource():
    result = evaluate(CREW, POLICY, [Phase("outbound", "outbound", 100, 0),
                                     Phase("dwell", "dwell", 12000, 0)])
    ev2 = result["astronauts"][1]
    assert ev2["check"] == "fail" and ev2["risk"] is None
    assert ev2["breach"] == {"resource": "drinking_water", "phase": "dwell"}
    assert result["route"]["risk"] is None


def test_slope_personalisation_and_refusal():
    crew, policy = fixture_data()
    crew["astronauts"][0]["id"] = "WALKER"
    crew["astronauts"][1]["id"] = "REF"
    crew["astronauts"][2]["id"] = "OTHER"
    crew["astronauts"][0]["peak_metabolic_w"] = 392
    assert next(a for a in prepare(crew, policy)["astronauts"] if a["id"] == "WALKER")["max_slope_deg"] == 12
    crew["astronauts"][0]["peak_metabolic_w"] = 386
    assert next(a for a in prepare(crew, policy)["astronauts"] if a["id"] == "WALKER")["max_slope_deg"] == 10
    crew["astronauts"][0]["peak_metabolic_w"] = 380
    with pytest.raises(MarswalkError, match="INVALID_HUMAN_FACTORS"):
        prepare(crew, policy)


def test_deterministic_bytes_and_order():
    crew, policy = fixture_data()
    first = serialize(evaluate(crew, policy, ROUTE))
    assert first == serialize(evaluate(crew, policy, ROUTE))
    crew["astronauts"].reverse()
    assert first == serialize(evaluate(crew, policy, ROUTE))


@pytest.mark.parametrize("phase", [
    Phase("bad", "dwell", 1, 2), Phase("bad", "outbound", 0, 1),
    Phase("bad", "outbound", float("nan"), 0),
])
def test_invalid_route_phases_refused(phase):
    with pytest.raises(MarswalkError, match="INVALID_HUMAN_FACTORS"):
        evaluate(CREW, POLICY, [phase])


def test_phase_context_tracks_dose_vitals_and_derived_fields_without_double_counting():
    environment = {
        "data_status": "simulated", "radiation_dose_rate_mgy_day": .25,
        "temperature_k": 238, "wind_speed_m_s": 7,
        "atmospheric_pressure_pa": 730, "dust_concentration_mg_m3": .25,
        "solar_illumination_deg": 30, "surface_traction": .55,
        "regolith_sinkage_mm": 10, "obstacle_density_count_m2": 11 / 600,
        "communication_signal_available": True, "visibility_distance_m": 100,
        "communication_latency_s": 800,
    }
    observations = {"EV1": {"data_status": "simulated", "heart_rate_bpm": 106,
                            "core_body_temperature_c": 37.1,
                            "suit_internal_pressure_kpa_abs": 30.1}}
    phase = Phase("outbound", "outbound", 3600, 40, distance_m=1800,
                  max_slope_deg=12, environment=environment, observations=observations)
    with_context = evaluate(CREW, POLICY, [phase])
    without_context = evaluate(CREW, POLICY, [Phase("outbound", "outbound", 3600, 40)])
    assert with_context["ambient_absorbed_dose_proxy_mgy"] == pytest.approx(.25 / 24)
    assert with_context["phase_context"][0]["environment"] == environment
    assert "wind_speed_m_s" in with_context["phase_context"][0]["not_in_consumables_model"]
    ev1 = with_context["astronauts"][0]
    assert ev1["phase_metrics"][0]["walking_speed_m_s"] == .5
    assert ev1["phase_metrics"][0]["observations"] == observations["EV1"]
    assert ev1["phase_metrics"][0]["suit_mobility_resistance_w"] == 13.5
    assert ev1["phase_metrics"][0]["cooling_demand_w"] > 0
    assert ev1["remaining_resources"]["oxygen"] == pytest.approx(750 - ev1["ledgers"][0]["total_use"])
    assert ev1["estimated_remaining_eva_s"] > 0
    assert [a["ledgers"] for a in with_context["astronauts"]] == [a["ledgers"] for a in without_context["astronauts"]]
    assert serialize(with_context) == serialize(evaluate(CREW, POLICY, [phase]))


def test_missing_dose_rate_is_unknown_not_zero():
    result = evaluate(CREW, POLICY, [Phase("outbound", "outbound", 100, 0)])
    assert result["ambient_absorbed_dose_proxy_mgy"] is None
    assert result["phase_context"][0]["ambient_absorbed_dose_proxy_mgy"] is None


def test_declared_co2_removal_reports_excess_without_medical_claim():
    crew, policy = fixture_data()
    crew["astronauts"][1]["co2_removal_g_s"] = 0
    result = evaluate(crew, policy, [Phase("outbound", "outbound", 100, 0)])
    ev1 = result["astronauts"][0]
    assert ev1["co2_excess_load_g"] == pytest.approx(ev1["co2_produced_g"])
    assert "co2_production_above_declared_removal" in ev1["flags"]
    assert ev1["check"] == "pass"


def test_route_slope_and_mean_peak_limits_fail_without_risk_score():
    slope = evaluate(CREW, POLICY, [Phase("outbound", "outbound", 100, 0, max_slope_deg=16)])
    assert slope["route"]["check"] == "fail" and slope["route"]["risk"] is None
    assert slope["astronauts"][0]["breach"] == {"resource": "terrain_slope", "phase": "outbound"}
    peak = evaluate(CREW, POLICY, [Phase("outbound", "outbound", 100, 100)])
    assert peak["route"]["check"] == "fail" and peak["route"]["risk"] is None
    assert peak["astronauts"][0]["breach"] == {"resource": "metabolic_peak", "phase": "outbound"}


@pytest.mark.parametrize("phase", [
    Phase("x", "outbound", 10, 0, environment={"data_status": "simulated", "wind_speed_m_s": float("nan")}),
    Phase("x", "outbound", 10, 0, environment={"data_status": "simulated", "unknown": 1}),
    Phase("x", "outbound", 10, 0, observations={"UNKNOWN": {"data_status": "simulated", "heart_rate_bpm": 90}}),
    Phase("x", "outbound", 10, 0, distance_m=1, max_slope_deg=90),
])
def test_invalid_phase_context_refused(phase):
    with pytest.raises(MarswalkError, match="INVALID_HUMAN_FACTORS"):
        evaluate(CREW, POLICY, [phase])
