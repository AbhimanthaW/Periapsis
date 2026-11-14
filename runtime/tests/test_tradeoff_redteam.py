"""Red-team tests: every case must end in GREEN-only or a refusal (plan section 10)."""
import copy
import json

import pytest

from runtime.marswalk.errors import MarswalkError
from runtime.tradeoff import (accept, accepted_count, is_executable, load_envelope, record_assessment,
                              record_decision, route_authority, verify, withdraw)
from runtime.tests.tradeoff_world import (CONSENT, NOW, SIGNATURES, WEATHER, classes, crew_data, envelope_data,
                                          green_only, marswalk_plan, never_better, option, policy_data, run, sign,
                                          telemetry_data)

A = lambda value, unit: {"value": value, "unit": unit, "status": "assumed"}      # noqa: E731
OK = dict(now_utc=NOW, signatures=SIGNATURES, crew_responses=CONSENT, decision_window_s=3600,
          one_way_light_time_s=600, prior_accepted_count=0)


def _amber():
    result, envelope = run()
    return option(result, "science:transect"), envelope


def _accept(**changes):
    amber, envelope = _amber()
    return accept(amber, envelope, **{**OK, **changes})


def test_baseline_acceptance_works_so_the_refusals_below_mean_something():
    record = _accept()
    assert record["status"] == "accepted" and record["authority"]["authority"] == "earth"
    assert [s["role"] for s in record["signatures"]] == ["flight_director", "crew_surgeon"]
    assert record["risk_budget"] == {"unit": "accepted AMBER options", "used_after": 1, "cap": 2}
    assert record["tripwires"] is None


def test_envelope_that_relaxes_l0_is_refused():
    data = envelope_data()
    data["exceptions"][0]["reserve_floor_fraction"]["oxygen"]["value"] = 0.05
    with pytest.raises(MarswalkError, match="relaxes the immutable L0 floor"):
        load_envelope(sign(data), now_utc=NOW)
    data = envelope_data()
    data["exceptions"][0]["reserve_floor_fraction"]["battery"]["value"] = 0.0
    with pytest.raises(MarswalkError, match="INVALID_ENVELOPE"):
        load_envelope(sign(data), now_utc=NOW)


def test_personal_override_looser_than_the_mission_value_is_refused():
    data = envelope_data()
    data["personal_overrides"][0]["reserve_floor_fraction"]["oxygen"]["value"] = 0.25     # EV2 mission value 0.35
    with pytest.raises(MarswalkError, match="personal values may only tighten"):
        run(envelope=data)
    data = envelope_data()
    data["personal_overrides"].append({
        "astronaut": "EV1", "reserve_floor_fraction": {"battery": A(0.12, "fraction_of_initial")},
        "set_by": "crew_surgeon", "reason": "simulated", "visibility": "surgeon_only"})
    with pytest.raises(MarswalkError, match="personal values may only tighten"):
        run(envelope=data)


def test_exception_tighter_than_the_mission_reserve_is_refused_not_silently_applied():
    data = envelope_data()
    data["exceptions"][0]["reserve_floor_fraction"]["battery"]["value"] = 0.30
    with pytest.raises(MarswalkError, match="cannot tighten"):
        run(envelope=data)


def test_personal_tightening_survives_inside_an_exception():
    """EV2's surgeon-set oxygen floor still binds under L2: the exception cannot loosen it."""
    result, envelope = run()
    ev2 = next(p for p in option(result, "science:transect")["per_astronaut"] if p["id"] == "EV2")
    oxygen = next(r for r in ev2["resources"] if r["resource"] == "oxygen")
    assert oxygen["margin_l2"] == pytest.approx(oxygen["margin_l1"])
    battery = next(r for r in ev2["resources"] if r["resource"] == "battery")
    assert battery["margin_l2"] - battery["margin_l1"] == pytest.approx(0.05 * 155.0, abs=1e-5)   # 0.20 -> 0.15, +raise kept


def test_expired_envelope_is_refused_and_cannot_accept():
    with pytest.raises(MarswalkError, match="envelope expired"):
        load_envelope(envelope_data(), now_utc="2021-02-19T04:00:00Z")
    amber, envelope = _amber()                                 # loaded while valid, used after expiry
    late = accept(amber, envelope, **{**OK, "now_utc": "2021-02-19T05:00:00Z"})
    assert late["status"] == "refused" and "expired" in late["reason"]
    result, _ = run()
    from runtime.tradeoff import assess
    after = assess(marswalk_plan(), crew_data(), policy_data(), envelope, now_utc="2021-02-19T05:00:00Z",
                   telemetry=telemetry_data(crew_data(), policy_data(), observed_utc="2021-02-19T04:59:30Z"),
                   decision_window_s=3600, one_way_light_time_s=600)
    assert green_only(after) and option(after, "science:transect")["first_failing_rule"] == "amber_gate:envelope_unexpired"


@pytest.mark.parametrize("signatures, reason", [
    ([SIGNATURES[0]], "missing signature from crew_surgeon"),
    ([SIGNATURES[1]], "missing signature from flight_director"),
    ([], "missing signature from flight_director, crew_surgeon"),
    ([SIGNATURES[0], {**SIGNATURES[1], "id": SIGNATURES[0]["id"]}], "signatures must come from different people"),
    ([SIGNATURES[0], {**SIGNATURES[1], "reason": "  "}], "crew_surgeon signed without a reason"),
    ([SIGNATURES[0], {**SIGNATURES[1], "role": "habitat_operator"}], "role 'habitat_operator' may not sign this acceptance"),
])
def test_missing_or_wrong_role_is_refused(signatures, reason):
    record = _accept(signatures=signatures)
    assert record["status"] == "refused" and record["reason"] == reason


def test_science_lead_signature_is_refused_everywhere():
    data = envelope_data()
    data["signatures"][0]["role"] = "science_lead"
    with pytest.raises(MarswalkError, match="science_lead signature on a risk envelope is refused"):
        load_envelope(sign(data), now_utc=NOW)
    lead = {"role": "science_lead", "id": "SIM-SL-01", "reason": "this stop matters", "signed_utc": NOW}
    for signatures in ([lead, SIGNATURES[1]], [*SIGNATURES, lead], [lead]):
        record = _accept(signatures=signatures)
        assert record["status"] == "refused" and "science_lead signature is refused" in record["reason"]


def test_crew_veto_or_silence_blocks_acceptance():
    refuse = _accept(crew_responses=[CONSENT[0], {"astronaut": "EV2", "response": "refuse"}])
    assert refuse["status"] == "refused" and refuse["reason"] == "crew veto: EV2 refused"
    silent = _accept(crew_responses=[CONSENT[0]])
    assert silent["status"] == "refused" and "no consent recorded from EV2" in silent["reason"]
    veto = _accept(vetoes=[{"by": "crew_surgeon", "reason": "simulated concern"}])
    assert veto["status"] == "refused" and veto["reason"].startswith("vetoed by crew_surgeon")
    amber, envelope = _amber()
    record = accept(amber, envelope, **OK)
    withdrawn = withdraw(record, by="EV2", reason="changed my mind", now_utc=NOW)
    assert is_executable(amber, record, now_utc=NOW) and not is_executable(amber, withdrawn, now_utc=NOW)


def test_stale_or_missing_telemetry_means_green_only():
    crew, policy = crew_data(), policy_data()
    for telemetry in (None,
                      telemetry_data(crew, policy, observed_utc="2021-02-18T20:30:00Z"),      # 829 s old, limit 120
                      telemetry_data(crew, policy, observed_utc="2021-02-18T21:00:00Z")):     # from the future
        result, envelope = run(telemetry=telemetry)
        assert green_only(result)
        transect = option(result, "science:transect")
        assert transect["first_failing_rule"] == "amber_gate:telemetry"
        assert accept(transect, envelope, **OK)["status"] == "refused"
    partial = telemetry_data(crew, policy)
    partial["astronauts"].pop()
    assert green_only(run(telemetry=partial)[0])
    unlabelled = telemetry_data(crew, policy)
    unlabelled.pop("provenance")
    with pytest.raises(MarswalkError, match="INVALID_TELEMETRY"):
        run(telemetry=unlabelled)


def test_an_old_assessment_cannot_be_accepted_later():
    record = _accept(now_utc="2021-02-18T20:50:00Z",
                     signatures=[{**s, "signed_utc": "2021-02-18T20:49:00Z"} for s in SIGNATURES])
    assert record["status"] == "refused" and "assess again" in record["reason"]


@pytest.mark.parametrize("scale", [0.0, 0.05, 0.2, 0.49])
def test_stuck_low_oxygen_reading_never_makes_an_option_look_better(scale):
    crew, policy = crew_data(), policy_data()
    honest = classes(run()[0])
    without = classes(run(telemetry=None)[0])
    stuck = telemetry_data(crew, policy, scale=scale)
    if scale == 0.0:
        for row in stuck["astronauts"]:
            row["co2_produced_g"] = 1.0
    result, _ = run(telemetry=stuck)
    low = classes(result)
    assert green_only(result) and never_better(honest, low) and low == without
    assert option(result, "science:transect")["first_failing_rule"] == "amber_gate:telemetry"
    # the low reading changes no margin at all: readings never enter the ledger
    margins = lambda r: [(a["option_id"], p["id"], x["resource"], x["margin_l1"])                # noqa: E731
                         for a in r["assessments"] for p in a["per_astronaut"] for x in p["resources"]]
    assert margins(result) == margins(run()[0])


def test_one_stuck_sensor_or_a_co2_disagreement_is_enough():
    crew, policy = crew_data(), policy_data()
    one = telemetry_data(crew, policy)
    one["astronauts"][1]["oxygen_used_g"] *= 0.2
    one["astronauts"][1]["co2_produced_g"] *= 0.2
    assert green_only(run(telemetry=one)[0])
    disagree = telemetry_data(crew, policy)
    disagree["astronauts"][0]["oxygen_used_g"] *= 0.7           # O2 reads low, CO2 does not
    result, _ = run(telemetry=disagree)
    assert green_only(result)
    assert "disagree" in next(g["reason"] for g in result["amber_gates"] if g["gate"] == "telemetry")
    high = telemetry_data(crew, policy, scale=1.5)              # above the 1.3 margin factor
    result, _ = run(telemetry=high)
    assert green_only(result)
    assert "above the consumption margin factor" in next(g["reason"] for g in result["amber_gates"]
                                                         if g["gate"] == "telemetry")


def test_ten_small_acceptances_cannot_exceed_the_risk_budget(tmp_path):
    log = tmp_path / "audit.jsonl"
    statuses = []
    for _ in range(10):
        used = accepted_count(log, "demo-eva-envelope-simulated")
        result, envelope = run(accepted=used)
        record_assessment(log, result)
        transect = option(result, "science:transect")
        record = accept(transect, envelope, **{**OK, "prior_accepted_count": used})
        record_decision(log, record)
        statuses.append((transect["class"], record["status"]))
    assert statuses[:2] == [("AMBER", "accepted")] * 2
    assert statuses[2:] == [("RED", "refused")] * 8
    assert accepted_count(log, "demo-eva-envelope-simulated") == 2 and verify(log)["records"] == 20
    # even handed a stale AMBER assessment, the budget itself refuses
    amber, envelope = _amber()
    over = accept(amber, envelope, **{**OK, "prior_accepted_count": 2})
    assert over["status"] == "refused" and over["reason"].startswith("risk budget exhausted")


def test_tampered_audit_line_breaks_verification(tmp_path):
    log = tmp_path / "audit.jsonl"
    result, envelope = run()
    record_assessment(log, result)
    record_decision(log, accept(option(result, "science:transect"), envelope, **OK))
    record_assessment(log, result)
    assert verify(log)["ok"] and verify(log)["records"] == 3
    lines = log.read_bytes().split(b"\n")
    original = list(lines)

    lines[1] = lines[1].replace(b'"status":"accepted"', b'"status":"refused"')
    log.write_bytes(b"\n".join(lines))
    state = verify(log)
    assert not state["ok"] and state["first_bad_line"] == 2
    with pytest.raises(MarswalkError, match="INVALID_AUDIT"):
        record_assessment(log, result)                          # refuses to extend a broken chain
    with pytest.raises(MarswalkError, match="INVALID_AUDIT"):
        accepted_count(log, "demo-eva-envelope-simulated")      # and the risk budget fails closed

    edited = json.loads(original[0])                            # a careful edit that keeps valid JSON
    edited["body"]["options"][1]["class"] = "GREEN"
    lines = list(original)
    lines[0] = json.dumps(edited, sort_keys=True, separators=(",", ":")).encode()
    log.write_bytes(b"\n".join(lines))
    assert verify(log)["first_bad_line"] == 1

    log.write_bytes(b"\n".join([original[0], original[2], b""]))    # a removed middle record
    assert verify(log)["first_bad_line"] == 2
    log.write_bytes(b"\n".join([original[1], original[0], original[2], b""]))   # reordered
    assert verify(log)["first_bad_line"] == 1
    log.write_bytes(b"\n".join(original))
    assert verify(log)["ok"]


def test_window_shorter_than_the_light_time_round_trip_with_no_delegate_is_green_only():
    data = envelope_data()
    data["authority"]["habitat_delegate"] = None
    # round trip 2 x 600 s + 120 s allowance = 1320 s; the window is 1319 s
    result, envelope = run(envelope=data, decision_window_s=1319, one_way_light_time_s=600)
    assert green_only(result) and result["authority"]["authority"] == "none"
    assert option(result, "science:transect")["first_failing_rule"] == "amber_gate:authority"
    amber, _ = _amber()
    stale_amber = {**amber, "inputs": {**amber["inputs"], "envelope_sha256": envelope.sha256}}
    record = accept(stale_amber, envelope, **{**OK, "decision_window_s": 1319})
    assert record["status"] == "refused" and "GREEN options only" in record["reason"]
    # one second more and Earth can answer
    assert classes(run(envelope=data, decision_window_s=1320, one_way_light_time_s=600)[0])["science:transect"] == "AMBER"


def test_with_a_delegate_only_the_delegate_may_sign_and_consent_is_still_needed():
    result, envelope = run(decision_window_s=600, one_way_light_time_s=600)
    assert result["authority"]["authority"] == "habitat_delegate"
    amber = option(result, "science:transect")
    assert amber["class"] == "AMBER"
    short = {**OK, "decision_window_s": 600}
    earth = accept(amber, envelope, **short)
    assert earth["status"] == "refused" and "only habitat_operator may sign" in earth["reason"]
    delegate = [{"role": "habitat_operator", "id": "SIM-HO-01", "reason": "simulated", "signed_utc": NOW}]
    assert accept(amber, envelope, **{**short, "signatures": delegate})["status"] == "accepted"
    no_consent = accept(amber, envelope, **{**short, "signatures": delegate, "crew_responses": []})
    assert no_consent["status"] == "refused"


def test_light_time_is_an_input_and_missing_inputs_fail_closed():
    _, envelope = run()
    assert route_authority(envelope, 3600, None)["authority"] == "none"
    assert route_authority(envelope, None, 600)["authority"] == "none"
    assert route_authority(envelope, 3600, 180)["authority"] == "earth"
    assert route_authority(envelope, 3600, 1320)["round_trip_s"] == 2760
    assert route_authority(envelope, 3600, 1741)["authority"] == "habitat_delegate"
    with pytest.raises(MarswalkError):
        route_authority(envelope, 3600, -1)


def test_weather_warning_or_lost_link_means_green_only():
    warning = copy.deepcopy(WEATHER)
    warning["messages"][0]["value"] = 22.0                      # at the simulated warning limit
    result, _ = run(plan=marswalk_plan(weather_json=json.dumps(warning)))
    assert green_only(result)
    lost = copy.deepcopy(WEATHER)
    lost["messages"][0]["time_utc"] = "2021-02-18T19:00:00Z"
    result, _ = run(plan=marswalk_plan(weather_json=json.dumps(lost)))
    assert green_only(result)
    assert next(g for g in result["amber_gates"] if g["gate"] == "weather")["open"] is False
    forecast_only = copy.deepcopy(WEATHER)
    forecast_only["messages"].append({"station_id": "base-1", "variable": "wind_speed", "value": 25.0,
                                      "unit": "m/s", "kind": "forecast", "time_utc": "2021-02-18T20:40:00Z",
                                      "valid_to_utc": "2021-02-18T23:00:00Z", "provenance": "simulated"})
    result, _ = run(plan=marswalk_plan(weather_json=json.dumps(forecast_only)))
    assert classes(result)["science:transect"] == "AMBER"       # a forecast alone changes nothing


def test_assessment_under_another_envelope_or_model_version_is_refused():
    amber, envelope = _amber()
    other = envelope_data()
    other["envelope_id"] = "another-envelope"
    other_loaded = load_envelope(sign(other), now_utc=NOW)
    assert accept(amber, other_loaded, **OK)["reason"] == "the assessment was made under a different envelope"
    old = {**amber, "model": {**amber["model"], "version": "0" * 64}}
    assert accept(old, envelope, **OK)["reason"] == "the assessment was made by a different model version"
    green = option(run()[0], "direct_return")
    assert accept(green, envelope, **OK)["status"] == "refused"
