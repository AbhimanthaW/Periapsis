"""T0/T1/T5/T7: envelope contract, option table, card, audit log, output schema, determinism."""
import json

import pytest

from runtime.humancost import load_crew, load_policy
from runtime.marswalk.errors import MarswalkError
from runtime.tradeoff import (L0_RESERVE_FLOOR_FRACTION, build_options, load_envelope, record_assessment,
                              serialize, verify)
from runtime.tradeoff import audit
from runtime.tests.tradeoff_world import (ENVELOPE, NOW, classes, crew_data, envelope_data, marswalk_plan, option,
                                          policy_data, run, sign)

FORBIDDEN_KEYS = {"rank", "ranking", "score", "risk_score", "risk", "band", "combined", "index", "who_should_go"}
FORBIDDEN_WORDS = ("safe", "survival", "probability of harm")


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def test_example_envelope_loads_and_every_number_is_labelled_assumed():
    envelope = load_envelope(ENVELOPE, now_utc=NOW)
    assert envelope.consumption_margin_factor >= 1 and envelope.habitat_delegate == "habitat_operator"

    def entries(value):
        if isinstance(value, dict):
            if "value" in value:
                yield value
            else:
                for inner in value.values():
                    yield from entries(inner)
        elif isinstance(value, list):
            for inner in value:
                yield from entries(inner)

    found = list(entries(envelope_data()))
    assert len(found) >= 12 and all(e["status"] == "assumed" and e["unit"] for e in found)


@pytest.mark.parametrize("change", [
    lambda d: d.update(unknown=1),                                              # unknown key
    lambda d: d.pop("provenance"),                                              # missing label
    lambda d: d.update(provenance="evidence"),
    lambda d: d.pop("consumption_margin_factor"),                               # never defaulted
    lambda d: d["consumption_margin_factor"].pop("unit"),                       # explicit units
    lambda d: d["consumption_margin_factor"].update(unit="percent"),
    lambda d: d["consumption_margin_factor"].update(value=0.9),                 # would loosen every ledger
    lambda d: d["consumption_margin_factor"].update(value=float("nan")),
    lambda d: d["exceptions"][0].update(requires_crew_consent=False),           # consent never assumed
    lambda d: d["exceptions"][0].update(requires_roles=["flight_director"]),
    lambda d: d["exceptions"][0].update(requires_roles=["flight_director", "science_lead"]),
    lambda d: d["exceptions"][0]["reserve_floor_fraction"].update(nitrogen={"value": 0.2, "unit": "fraction_of_initial", "status": "assumed"}),
    lambda d: d["objectives"][0].update(set_by="flight_director"),
    lambda d: d["personal_overrides"][0].update(visibility="everyone"),
    lambda d: d["personal_overrides"][0].update(set_by="flight_director"),
    lambda d: d["authority"].update(habitat_delegate="crew_surgeon"),
    lambda d: d["authority"].pop("response_allowance_s"),
    lambda d: d["signatures"].pop(),                                            # a role has not signed
    lambda d: d["signatures"][1].update(id=d["signatures"][0]["id"]),           # same person twice
    lambda d: d["signatures"][0].update(signed_utc="2021-02-19T00:00:00Z"),     # signed in the future
])
def test_envelope_refuses_invalid_input(change):
    data = sign(envelope_data())
    change(data)
    try:
        sign(data)                      # re-sign, so only the change under test can cause the refusal
    except ValueError:
        pass                            # NaN cannot be hashed; the loader must refuse it itself
    with pytest.raises(MarswalkError, match="INVALID_ENVELOPE"):
        load_envelope(data, now_utc=NOW)


def test_envelope_edited_after_signing_is_refused():
    data = envelope_data()
    data["exceptions"][0]["reserve_floor_fraction"]["oxygen"]["value"] = 0.15
    with pytest.raises(MarswalkError, match="changed after signing"):
        load_envelope(data, now_utc=NOW)


def test_l0_floors_are_code_constants_below_one():
    assert set(L0_RESERVE_FLOOR_FRACTION) == {"oxygen", "cooling_water", "battery"}
    assert all(0 < value < 1 for value in L0_RESERVE_FLOOR_FRACTION.values())


def test_option_table_keeps_no_route_apart_from_reserve_breach():
    crew, policy = load_crew(crew_data()), load_policy(policy_data())
    options = build_options(marswalk_plan(), crew, policy)
    assert [o.id for o in options][:3] == ["direct_return", "science:transect", "science:photo-set"]
    transect = next(o for o in options if o.id == "science:transect")
    assert [p.kind for p in transect.phases] == ["outbound", "dwell", "return"]
    outbound_leg = transect.plan.legs[0][1]
    assert transect.phases[0].time_s == pytest.approx(outbound_leg.seconds)
    assert transect.phases[0].gain_m == pytest.approx(outbound_leg.ascent_m)
    assert transect.phases[0].distance_m == pytest.approx(outbound_leg.length_m)
    assert transect.phases[0].max_slope_deg == pytest.approx(outbound_leg.max_slope_deg)
    assert all(o.route_status == "ok" and o.human_cost is not None for o in options)
    multi = next(o for o in options if o.id == "multi:transect>photo-set")
    assert [p.name for p in multi.phases] == ["outbound", "dwell:transect", "transfer", "dwell:photo-set", "return"]

    # A closed-off task has no route: no ledger is invented and the reason is a route reason.
    import numpy as np
    from runtime.marswalk import MissionSnapshot, ScreenPolicy, Task, TerrainSupport, build_baseline, plan_marswalk
    z = np.zeros((5, 12))
    screen = np.zeros((5, 12), bool)
    screen[:, 6] = True
    support = TerrainSupport.from_affine(z.shape, (5.0, 0, 0, 0, -5.0, 25.0), native_spacing_m=5.0,
                                         pack_id="test", pack_version="1")
    baseline = build_baseline(support, z, np.isfinite(z), screen, policy=ScreenPolicy())
    snapshot = MissionSnapshot("m", 1, "test", "1", "s", (2, 2), (2, 0), (Task("far", (2, 10), 60, 1),), (),
                               3600, 0)
    walled = build_options(plan_marswalk(baseline, snapshot), crew, policy)
    far = next(o for o in walled if o.id == "science:far")
    assert far.route_status == "no_route" and far.human_cost is None
    assert walled[0].route_status == "ok"


def test_no_route_option_is_red_with_a_route_reason():
    import numpy as np
    from runtime.marswalk import MissionSnapshot, ScreenPolicy, Task, TerrainSupport, build_baseline, plan_marswalk
    z = np.zeros((5, 12))
    screen = np.zeros((5, 12), bool)
    screen[:, 6] = True
    support = TerrainSupport.from_affine(z.shape, (5.0, 0, 0, 0, -5.0, 25.0), native_spacing_m=5.0,
                                         pack_id="test", pack_version="1")
    baseline = build_baseline(support, z, np.isfinite(z), screen, policy=ScreenPolicy())
    snapshot = MissionSnapshot("m", 1, "test", "1", "s", (2, 2), (2, 0), (Task("far", (2, 10), 60, 1),), (),
                               3600, 0)
    result, _ = run(plan=plan_marswalk(baseline, snapshot))
    far = option(result, "science:far")
    assert far["class"] == "RED" and far["first_failing_rule"] == "route:no_route"
    assert far["per_astronaut"] == [] and far["route"]["status"] == "no_route"
    assert classes(result)["direct_return"] == "GREEN"


def test_fixture_classes_and_per_resource_report():
    result, _ = run()
    assert classes(result) == {"direct_return": "GREEN", "science:transect": "AMBER",
                               "science:photo-set": "GREEN", "multi:transect>photo-set": "RED",
                               "multi:photo-set>transect": "RED"}
    amber = option(result, "science:transect")
    assert amber["first_failing_rule"] is None and amber["requires_acceptance"] is True
    assert amber["exceeds_l1"] == "reserve_floor_l1:EV2:battery:return"
    ev2 = next(p for p in amber["per_astronaut"] if p["id"] == "EV2")
    battery = next(r for r in ev2["resources"] if r["resource"] == "battery")
    assert ev2["driver"] == "battery" and battery["unit"] == "Wh"
    assert battery["margin_l1"] < 0 <= battery["margin_l2"]
    assert battery["reserve_breached_l1"] is True and battery["reserve_breached_l2"] is False
    assert {r["resource"] for r in ev2["resources"]} == {"oxygen", "cooling_water", "drinking_water", "battery"}
    # photo-set is priority class 2: no pre-signed exception, so it could never be AMBER
    assert option(result, "science:photo-set")["science"]["exception_classes_applied"] == []
    red = option(result, "multi:transect>photo-set")
    assert red["first_failing_rule"].startswith("reserve_floor_l1:")


def test_p1_fields_are_null_not_invented():
    result, _ = run()
    for assessment in result["assessments"]:
        assert assessment["schema"] == "tradeoff-assessment-v1"
        assert assessment["science"]["expected_value"] is None and assessment["science"]["p_complete"] is None
        assert assessment["tripwires"] is None and assessment["latest_decision_utc"] is None
        assert assessment["model"]["seed"] is None and assessment["model"]["draws"] is None
        for person in assessment["per_astronaut"]:
            assert person["p_breach"] == {"estimate": None, "upper95": None}
            assert person["p_exhaust_draws"] is None
            assert person["burn_rate"] == {"p10": None, "p50": None, "p90": None}


def test_output_has_no_crew_ranking_no_combined_score_and_no_forbidden_words():
    for kwargs in ({}, {"telemetry": None}, {"crew": crew_data(battery_wh=20.0)}):
        result, _ = run(**kwargs)
        assert not FORBIDDEN_KEYS & set(_keys(result))
        text = serialize(result).decode().lower()
        assert not any(word in text for word in FORBIDDEN_WORDS)
        for assessment in result["assessments"]:
            # astronauts are listed by id, never ordered by any margin
            ids = [p["id"] for p in assessment["per_astronaut"]]
            assert ids == sorted(ids)
            assert not [k for k, v in assessment.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def test_card_lists_what_is_added_and_what_it_costs_without_an_exchange_rate():
    result, _ = run()
    assert [c["option_id"] for c in result["cards"]] == ["science:transect"]
    card = result["cards"][0]
    assert card["versus"] == {"option_id": "science:photo-set", "class": "GREEN"}
    assert option(result, "science:transect")["versus"] == card["versus"]
    assert card["adds"]["task_ids"] == ["transect"] and card["adds"]["drops_task_ids"] == ["photo-set"]
    assert card["adds"]["priority_classes"] == {"transect": 1}
    assert card["adds"]["science_value"] == 2 and card["adds"]["science_value_versus"] == 1
    ev2 = next(c for c in card["costs"] if c["astronaut"] == "EV2")
    battery = next(r for r in ev2["resources"] if r["resource"] == "battery")
    assert battery["margin_l1_change"] < 0 and battery["crosses_l1"] is True
    assert battery["margin_l1_change"] == pytest.approx(battery["margin_l1"] - battery["margin_l1_versus"], abs=1e-5)
    assert not {"ratio", "exchange_rate", "per_science", "cost_per_value"} & set(_keys(card))


def test_same_inputs_give_identical_bytes():
    marswalk_plan.cache_clear()
    first = serialize(run()[0])
    marswalk_plan.cache_clear()
    second = serialize(run()[0])
    assert first == second and json.loads(first)["schema"] == "tradeoff-assessment-set-v1"


def test_model_reads_but_never_mutates_the_plan():
    plan = marswalk_plan()
    before = json.dumps([p.to_dict() for p in plan.plans], sort_keys=True)
    recommendation, revision = plan.recommendation, plan.snapshot.revision
    run()
    assert json.dumps([p.to_dict() for p in plan.plans], sort_keys=True) == before
    assert (plan.recommendation, plan.snapshot.revision) == (recommendation, revision)
    # G1: the pricing and classifying modules have no path that rewrites a plan or a limit
    import runtime.tradeoff.card as card
    import runtime.tradeoff.classify as classify
    import runtime.tradeoff.options as options
    for module in (card, classify, options):
        source = open(module.__file__).read()
        assert "enforce_hard_constraints" not in source and "replace(" not in source
        assert "AuthorizedLimit" not in source and "plan_marswalk" not in source


def test_audit_chain_records_and_verifies(tmp_path):
    log = tmp_path / "audit.jsonl"
    assert verify(log) == {"ok": True, "records": 0, "first_bad_line": None, "reason": None, "head_sha256": None}
    result, _ = run()
    first = record_assessment(log, result)
    second = record_assessment(log, result)
    assert second["prev_sha256"] == first["sha256"] and first["prev_sha256"] == "0" * 64
    body = first["body"]
    assert set(body["inputs"]) >= {"envelope_sha256", "crew_sha256", "policy_sha256", "plan_sha256",
                                   "telemetry_sha256"}
    assert body["model"]["version"] and {o["option_id"]: o["class"] for o in body["options"]} == classes(result)
    state = verify(log)
    assert state["ok"] and state["records"] == 2 and state["head_sha256"] == second["sha256"]
    with pytest.raises(MarswalkError, match="INVALID_AUDIT"):
        audit.append(log, "note", {}, time_utc=NOW)
