"""T4 · Deterministic classifier: GREEN / AMBER / RED with the first failing rule.

P0 has no Monte Carlo. Each option's nominal human-cost ledger is multiplied
by ONE fixed consumption margin factor from the envelope, and the prefix rule
is re-run: after every phase, ``initial - factor x cumulative use`` must stay
at or above the reserve floor.

    GREEN  every Marswalk hard constraint passes, and every astronaut and
           resource holds its L1 floor in every phase.
    AMBER  not GREEN only because an L1 floor is crossed; the pre-signed L2
           floors for the option's priority class(es) hold; and every AMBER
           gate is open (direct return GREEN, weather assessed with no
           WARNING, envelope unexpired, telemetry fresh and plausible, an
           authority reachable in the decision window, risk budget has room).
           Executable ONLY after an acceptance record (accept.py).
    RED    anything else, with the first failing rule. Never executable.

"Return now" is never AMBER. If it is not GREEN the output says so loudly.

Bad or missing inputs close the AMBER gates; they never change a GREEN, because
GREEN rests only on the planner's own constraints and the conservative ledger.
The model prices and classifies. It does not decide, execute, rank crew, or
produce any combined score.
"""
from dataclasses import asdict

from runtime.humancost import load_crew, load_policy, prepare
from runtime.humancost.calculator import RESOURCES, UNITS
from runtime.humancost.factors import Crew, Policy
from runtime.marswalk.errors import PASS
from runtime.marswalk.weather import WARNING

from ._common import canonical, digest, model_version, refuse, utc, utc_text
from .accept import AMBER, GREEN, NONE, RED, route_authority
from .card import tradeoff_cards
from .envelope import reserve_floors
from .options import ROUTE_OK, build_options
from .telemetry import load_telemetry, telemetry_gate

CODE = "INVALID_ASSESSMENT"
SCHEMA, SET_SCHEMA = "tradeoff-assessment-v1", "tradeoff-assessment-set-v1"
EPS = 1e-12
LIMITS = (
    "Deterministic P0: one fixed consumption margin factor; no probabilities are computed.",
    "Crew, envelope and telemetry values are simulated; thresholds and the margin factor are assumptions.",
    "Starting stores in the crew file are read as the stores at the time of assessment.",
    "Pace model is illustrative; dwell uses the flat-walking metabolic rate.",
    "margin_s is a flat-rate estimate of time left above the L1 floor, not a measured endurance.",
    "Reserve margins describe consumable reserves only; they are not a statement about crew health.",
)


def _r(value):
    return None if value is None else round(float(value), 6)


def _ledger_view(option, floors, factor, exception_classes, people):
    """Per astronaut and per resource: margins and the first phase that crosses each floor."""
    view, first_l1, first_l2, hard = [], None, None, None
    for item in option.human_cost["astronauts"]:
        person, mine = people[item["id"]], floors[item["id"]]
        for metric in item["phase_metrics"]:
            if hard is not None:
                break
            if metric["max_slope_deg"] is not None and metric["max_slope_deg"] > item["max_slope_deg"]:
                hard = f"human_cost:slope_limit:{item['id']}:{metric['phase']}"
            elif metric["metabolic_power_w"] is not None and metric["metabolic_power_w"] > person.peak_metabolic_w:
                hard = f"human_cost:metabolic_peak:{item['id']}:{metric['phase']}"
        l2_floor = None
        if exception_classes:
            l2_floor = {r: max(mine["l2"][c][r] for c in exception_classes) for r in RESOURCES}
        resources, fractions = [], {}
        for ledger in item["ledgers"]:
            resource = ledger["resource"]
            breach_l1 = breach_l2 = None
            for row in ledger["rows"]:
                remaining = ledger["initial"] - factor * row["cumulative_use"]
                if breach_l1 is None and remaining < mine["l1"][resource] - EPS:
                    breach_l1 = row["phase"]
                if l2_floor is not None and breach_l2 is None and remaining < l2_floor[resource] - EPS:
                    breach_l2 = row["phase"]
            end = ledger["initial"] - factor * ledger["total_use"]
            margin_l1 = end - mine["l1"][resource]
            fractions[resource] = margin_l1 / (ledger["initial"] - mine["l1"][resource])
            if breach_l1 is not None and first_l1 is None:
                first_l1 = f"reserve_floor_l1:{item['id']}:{resource}:{breach_l1}"
            if breach_l2 is not None and first_l2 is None:
                first_l2 = f"reserve_floor_l2:{item['id']}:{resource}:{breach_l2}"
            resources.append({
                "resource": resource, "unit": UNITS[resource],
                "margin_l1": _r(margin_l1),
                "margin_l2": None if l2_floor is None else _r(end - l2_floor[resource]),
                "reserve_breached_l1": breach_l1 is not None, "breach_phase_l1": breach_l1,
                "reserve_breached_l2": None if l2_floor is None else breach_l2 is not None,
                "breach_phase_l2": breach_l2,
            })
        driver = min(RESOURCES, key=lambda r: (fractions[r], RESOURCES.index(r)))
        flat = item["rates_flat_per_h"]
        margin_s = min(next(x["margin_l1"] for x in resources if x["resource"] == r) * 3600 / (factor * flat[r])
                       for r in RESOURCES)
        view.append({
            "id": item["id"], "driver": driver,
            "p_breach": {"estimate": None, "upper95": None}, "p_exhaust_draws": None,
            "margin_s": _r(margin_s), "burn_rate": {"p10": None, "p50": None, "p90": None},
            "resources": resources, "flags": list(item["flags"]),
        })
    return view, hard, first_l1, first_l2


def _weather_gate(marswalk_plan):
    weather = marswalk_plan.weather
    if weather is None:
        return False, "weather not assessed for this plan", "not_assessed"
    if weather.link_lost:
        return False, "weather link lost; conditions unknown", "link_lost"
    if any(alert.level == WARNING for alert in weather.alerts):
        return False, "a weather WARNING is active", "warning"
    return True, "weather assessed; no WARNING active", "no_warning"


def assess(marswalk_plan, crew, policy, envelope, *, now_utc, telemetry=None, decision_window_s=None,
           one_way_light_time_s=None, accepted_amber_count=0):
    """Classify every Marswalk candidate. Returns a ``tradeoff-assessment-set-v1`` dict.

    ``envelope`` is a loaded ``Envelope``. ``telemetry`` is a path, mapping or None.
    ``accepted_amber_count`` is the number of AMBER options already accepted this EVA
    (``audit.accepted_count``). Nothing here mutates the plan or the snapshot.
    """
    now = utc(now_utc, "now_utc", CODE)
    crew = crew if isinstance(crew, Crew) else load_crew(crew)
    policy = policy if isinstance(policy, Policy) else load_policy(policy)
    if type(accepted_amber_count) is not int or accepted_amber_count < 0:
        refuse(CODE, "accepted_amber_count must be a non-negative integer")
    telemetry = None if telemetry is None else load_telemetry(telemetry)
    prepared = prepare(crew, policy)
    floors = reserve_floors(envelope, crew, policy, prepared)
    people = {p.id: p for p in crew.astronauts}
    factor = envelope.consumption_margin_factor
    options = build_options(marswalk_plan, crew, policy)
    snapshot = marswalk_plan.snapshot

    def exception_classes(option):
        classes = [envelope.priority_class(task) for task in option.task_ids]
        if not classes or any(c is None or envelope.exception(c) is None for c in classes):
            return ()
        return tuple(sorted(set(classes)))

    # Pass 1: everything that does not depend on the AMBER gates.
    rows = []
    for option in options:
        row = {"option": option, "view": [], "rule": None, "l1": None, "l2": None, "classes": ()}
        hard_constraint = next(((rule, outcome) for rule, outcome, _ in option.plan.constraints
                                if outcome != PASS), None)
        if option.route_status != ROUTE_OK:
            row["rule"] = f"route:{option.route_status}"
        else:
            row["classes"] = exception_classes(option)
            row["view"], hard_cost, row["l1"], row["l2"] = _ledger_view(option, floors, factor, row["classes"], people)
            if hard_constraint is not None or not option.plan.constraints:
                row["rule"] = ("hard_constraint:not_evaluated" if hard_constraint is None
                               else f"hard_constraint:{hard_constraint[0]}:{hard_constraint[1]}")
            elif hard_cost is not None:
                row["rule"] = hard_cost
        row["green"] = row["rule"] is None and row["l1"] is None
        rows.append(row)

    direct_green = rows[0]["green"]
    weather_ok, weather_reason, weather_state = _weather_gate(marswalk_plan)
    telemetry_ok, telemetry_reason, telemetry_age = telemetry_gate(telemetry, envelope, crew, prepared, now)
    authority = route_authority(envelope, decision_window_s, one_way_light_time_s)
    budget_ok = accepted_amber_count < envelope.max_accepted_amber_per_eva
    gates = [
        ("direct_return_green", direct_green,
         "direct return is GREEN" if direct_green else "direct return is not GREEN"),
        ("weather", weather_ok, weather_reason),
        ("envelope_unexpired", not envelope.expired(now),
         f"envelope valid until {envelope.expires_utc}" if not envelope.expired(now)
         else f"envelope expired at {envelope.expires_utc}"),
        ("telemetry", telemetry_ok, telemetry_reason),
        ("authority", authority["authority"] != NONE, authority["reason"]),
        ("risk_budget", budget_ok,
         f"{accepted_amber_count} of {envelope.max_accepted_amber_per_eva} AMBER acceptances used"),
    ]
    closed_gate = next((name for name, ok, _ in gates if not ok), None)

    inputs = {
        "assessed_utc": utc_text(now),
        "authority": authority,
        "snapshot": {"mission_id": snapshot.mission_id, "revision": snapshot.revision},
        "telemetry_age_s": _r(telemetry_age), "weather_bundle": None, "weather_state": weather_state,
        "envelope_sha256": envelope.sha256,
        "crew_sha256": digest(asdict(crew)),
        "policy_sha256": digest({"values": {k: list(v) if isinstance(v, tuple) else v
                                            for k, v in policy.values.items()},
                                 "statuses": policy.statuses, "base_profile": policy.base_profile}),
        "plan_sha256": digest([p.to_dict() for p in marswalk_plan.plans]),
        "telemetry_sha256": None if telemetry is None else digest(telemetry),
    }
    model = {"id": "tradeoff-envelope", "version": model_version(), "seed": None, "draws": None,
             "method": "deterministic ledger x consumption margin factor",
             "consumption_margin_factor": factor}

    assessments = []
    for row in rows:
        option = row["option"]
        if row["green"]:
            cls, rule = GREEN, None
        elif row["rule"] is not None:
            cls, rule = RED, row["rule"]
        elif option.kind == "direct_return":
            cls, rule = RED, row["l1"]                       # return now is never AMBER
        elif not row["classes"]:
            cls, rule = RED, row["l1"]                       # no pre-signed exception covers this option
        elif row["l2"] is not None:
            cls, rule = RED, row["l2"]
        elif closed_gate is not None:
            cls, rule = RED, f"amber_gate:{closed_gate}"
        else:
            cls, rule = AMBER, None
        assessments.append({
            "schema": SCHEMA, "option_id": option.id, "class": cls, "first_failing_rule": rule,
            "requires_acceptance": cls == AMBER,
            "exceeds_l1": row["l1"] if cls == AMBER else None,
            "route": {"status": option.route_status, "reason": option.route_reason or None},
            "science": {"task_ids": list(option.task_ids), "science_value": option.science_value,
                        "priority_classes": {t: envelope.priority_class(t) for t in option.task_ids},
                        "exception_classes_applied": list(row["classes"]),
                        "expected_value": None, "p_complete": None},
            "per_astronaut": row["view"],
            "versus": None, "tripwires": None, "latest_decision_utc": None,
            "inputs": inputs, "model": model, "limits": list(LIMITS),
        })

    cards = tradeoff_cards(assessments, {o.id: o for o in options})
    for card in cards:
        target = next(a for a in assessments if a["option_id"] == card["option_id"])
        target["versus"] = {"option_id": card["versus"]["option_id"], "class": GREEN}

    direct = assessments[0]
    alert = None
    if direct["class"] != GREEN:
        alert = (f"RETURN NOW IS NOT GREEN ({direct['first_failing_rule']}). No option costs less than "
                 "returning now. Humans must act; this model does not decide.")
    return {
        "schema": SET_SCHEMA, "provenance": "simulated", "assessed_utc": inputs["assessed_utc"],
        "return_now": {"option_id": direct["option_id"], "class": direct["class"], "alert": alert},
        "amber_gates": [{"gate": name, "open": ok, "reason": reason} for name, ok, reason in gates],
        "authority": authority,
        "assessments": assessments, "cards": cards,
        "model": model, "limits": list(LIMITS),
    }


def serialize(result):
    """Canonical bytes: the same inputs give the same bytes."""
    return canonical(result)
