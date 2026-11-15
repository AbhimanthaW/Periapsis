"""T6 · Acceptance protocol (minimal P0 form).

An AMBER option becomes executable only through an acceptance record:

  * signatures from ``flight_director`` AND ``crew_surgeon``, each with a
    reason, from different people;
  * consent from every walking astronaut (silence is not consent);
  * no veto from anyone;
  * room in the per-EVA risk budget. In P0 the budget is a COUNT of accepted
    AMBER options against the envelope cap, so many small acceptances cannot
    add up to one large one;
  * an authority that can answer inside the decision window (latency routing).

Latency routing: Earth roles are available only if
``decision_window_s >= 2 x one_way_light_time_s + response_allowance_s``.
Otherwise only the habitat delegate named in the envelope may sign (crew
consent is still required), and with no delegate the decision is GREEN-only.
One-way light time is an input; no value is built in.

The ``science_lead`` sets priorities and can never sign. RED is never
executable. GREEN needs no acceptance. An acceptance expires.
"""
from datetime import timedelta

from ._common import digest, model_version, number, obj, refuse, text, utc, utc_text
from .envelope import ACCEPTING_ROLES, SCIENCE_LEAD

CODE = "INVALID_ACCEPTANCE"
SCHEMA = "tradeoff-acceptance-v1"
GREEN, AMBER, RED = "GREEN", "AMBER", "RED"
EARTH, HABITAT, NONE = "earth", "habitat_delegate", "none"


def route_authority(envelope, decision_window_s, one_way_light_time_s):
    """Who can answer in time. Missing inputs give no authority (fail closed)."""
    if decision_window_s is None or one_way_light_time_s is None:
        return {"authority": NONE, "round_trip_s": None, "decision_window_s": decision_window_s,
                "reason": "decision window or one-way light time not supplied"}
    window = number(decision_window_s, "decision_window_s", CODE, minimum=0)
    light = number(one_way_light_time_s, "one_way_light_time_s", CODE, minimum=0)
    needed = 2 * light + envelope.response_allowance_s
    base = {"round_trip_s": needed, "decision_window_s": window}
    if window >= needed:
        return {"authority": EARTH, **base, "reason": "Earth roles can answer inside the decision window"}
    if envelope.habitat_delegate is not None:
        return {"authority": HABITAT, **base,
                "reason": f"Earth cannot answer in time; authority falls to {envelope.habitat_delegate}"}
    return {"authority": NONE, **base,
            "reason": "Earth cannot answer in time and no habitat delegate is named: GREEN options only"}


def _refused(assessment, envelope, now_utc, reason):
    return {"schema": SCHEMA, "status": "refused", "reason": reason,
            "option_id": assessment.get("option_id") if isinstance(assessment, dict) else None,
            "envelope_id": envelope.envelope_id, "envelope_sha256": envelope.sha256, "decided_utc": now_utc}


def accept(assessment, envelope, *, now_utc, signatures, crew_responses, decision_window_s,
           one_way_light_time_s, prior_accepted_count, vetoes=()):
    """Return an acceptance record with status ``accepted`` or ``refused`` (with the reason).

    ``assessment`` is one ``tradeoff-assessment-v1`` object. Malformed input raises
    ``MarswalkError``; a protocol failure returns a refused record so it can be audited.
    """
    now = utc(now_utc, "now_utc", CODE)
    if not isinstance(assessment, dict) or assessment.get("schema") != "tradeoff-assessment-v1":
        refuse(CODE, "assessment must be a tradeoff-assessment-v1 object")
    if type(prior_accepted_count) is not int or prior_accepted_count < 0:
        refuse(CODE, "prior_accepted_count must be a non-negative integer")
    no = lambda reason: _refused(assessment, envelope, now_utc, reason)   # noqa: E731

    if assessment["class"] == RED:
        return no("RED is never executable")
    if assessment["class"] == GREEN:
        return no("GREEN is inside the nominal limits and needs no acceptance")
    if assessment["class"] != AMBER:
        refuse(CODE, "assessment class must be GREEN, AMBER or RED")
    if assessment["inputs"]["envelope_sha256"] != envelope.sha256:
        return no("the assessment was made under a different envelope")
    if assessment["model"]["version"] != model_version():
        return no("the assessment was made by a different model version")
    if envelope.expired(now):
        return no(f"envelope expired at {envelope.expires_utc}")
    assessed = utc(assessment["inputs"]["assessed_utc"], "assessed_utc", CODE)
    age = (now - assessed).total_seconds()
    telemetry_age = assessment["inputs"].get("telemetry_age_s")
    if age < 0 or telemetry_age is None or telemetry_age + age >= envelope.telemetry_max_age_s:
        return no("the assessment is older than the telemetry freshness limit (or from the future); assess again")

    for index, raw in enumerate(vetoes):
        veto = obj(raw, ("by", "reason"), f"vetoes[{index}]", CODE)
        return no(f"vetoed by {text(veto['by'], 'veto.by', CODE)}: {text(veto['reason'], 'veto.reason', CODE)}")

    walkers = [person["id"] for person in assessment["per_astronaut"]]
    responses = {}
    for index, raw in enumerate(crew_responses):
        item = obj(raw, ("astronaut", "response"), f"crew_responses[{index}]", CODE)
        if item["astronaut"] not in walkers or item["astronaut"] in responses:
            refuse(CODE, f"crew_responses[{index}]: unknown or repeated astronaut")
        if item["response"] not in ("consent", "refuse"):
            refuse(CODE, f"crew_responses[{index}].response must be 'consent' or 'refuse'")
        responses[item["astronaut"]] = item["response"]
    refusing = sorted(a for a, r in responses.items() if r == "refuse")
    if refusing:
        return no(f"crew veto: {', '.join(refusing)} refused")
    silent = sorted(set(walkers) - set(responses))
    if silent:
        return no(f"no consent recorded from {', '.join(silent)}; consent is never assumed")

    authority = route_authority(envelope, decision_window_s, one_way_light_time_s)
    if authority["authority"] == NONE:
        return no(authority["reason"])
    if authority != assessment["inputs"].get("authority"):
        return no("authority inputs changed since the assessment; assess again")
    window_s = authority["decision_window_s"]
    if age >= window_s:
        return no("the decision window has expired; assess again")
    required = list(ACCEPTING_ROLES) if authority["authority"] == EARTH else [envelope.habitat_delegate]
    signed = {}
    for index, raw in enumerate(signatures):
        item = obj(raw, ("role", "id", "reason", "signed_utc"), f"signatures[{index}]", CODE)
        if item["role"] == SCIENCE_LEAD:
            return no(f"a {SCIENCE_LEAD} signature is refused: the role that values science cannot accept risk")
        if item["role"] not in required:
            if item["role"] in ACCEPTING_ROLES:
                return no(f"{item['role']} cannot answer inside the decision window; "
                          f"only {envelope.habitat_delegate} may sign")
            return no(f"role {item['role']!r} may not sign this acceptance")
        if item["role"] in signed:
            refuse(CODE, f"signatures[{index}]: role signed twice")
        text(item["id"], f"signatures[{index}].id", CODE)
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            return no(f"{item['role']} signed without a reason")
        when = utc(item["signed_utc"], f"signatures[{index}].signed_utc", CODE)
        if when < assessed or when > now:
            return no(f"{item['role']} signature time is outside the assessment-to-decision interval")
        signed[item["role"]] = item
    missing = [role for role in required if role not in signed]
    if missing:
        return no(f"missing signature from {', '.join(missing)}")
    if len({item["id"] for item in signed.values()}) != len(signed):
        return no("signatures must come from different people")

    if prior_accepted_count >= envelope.max_accepted_amber_per_eva:
        return no(f"risk budget exhausted: {prior_accepted_count} AMBER option(s) already accepted this EVA, "
                  f"cap {envelope.max_accepted_amber_per_eva}")

    valid_s = min(envelope.acceptance_valid_s, window_s - age,
                  envelope.telemetry_max_age_s - telemetry_age - age)
    if valid_s <= 0:
        return no("the assessment has reached the telemetry freshness limit; assess again")
    expires = min(now + timedelta(seconds=valid_s), envelope.expires)
    return {
        "schema": SCHEMA, "status": "accepted", "reason": None,
        "option_id": assessment["option_id"], "assessment_sha256": digest(assessment),
        "envelope_id": envelope.envelope_id, "envelope_sha256": envelope.sha256,
        "snapshot": assessment["inputs"]["snapshot"],
        "decided_utc": now_utc, "expires_utc": utc_text(expires),
        "authority": authority,
        "signatures": [signed[role] for role in required],
        "crew_consent": [{"astronaut": a, "response": "consent"} for a in sorted(walkers)],
        "risk_budget": {"unit": "accepted AMBER options", "used_after": prior_accepted_count + 1,
                        "cap": envelope.max_accepted_amber_per_eva},
        "tripwires": None,       # P1: computed from the Monte Carlo; not available in P0
    }


def withdraw(acceptance, *, by, reason, now_utc):
    """Anyone may withdraw an acceptance at any time. The result is not executable."""
    utc(now_utc, "now_utc", CODE)
    if not isinstance(acceptance, dict) or acceptance.get("schema") != SCHEMA or acceptance.get("status") != "accepted":
        refuse(CODE, "only an accepted record can be withdrawn")
    return {**acceptance, "status": "withdrawn",
            "withdrawn": {"by": text(by, "by", CODE), "reason": text(reason, "reason", CODE), "utc": now_utc}}


def is_executable(assessment, acceptance=None, *, now_utc):
    """GREEN: yes. RED: never. AMBER: only with a matching, unexpired, accepted record."""
    now = utc(now_utc, "now_utc", CODE)
    if not isinstance(assessment, dict) or assessment.get("schema") != "tradeoff-assessment-v1":
        return False
    if assessment.get("class") == GREEN:
        return True
    if assessment.get("class") != AMBER or not isinstance(acceptance, dict):
        return False
    try:
        return (acceptance.get("schema") == SCHEMA and acceptance.get("status") == "accepted"
                and acceptance.get("option_id") == assessment["option_id"]
                and acceptance.get("assessment_sha256") == digest(assessment)
                and utc(acceptance["decided_utc"], "decided_utc", CODE) <= now
                < utc(acceptance["expires_utc"], "expires_utc", CODE))
    except (KeyError, ValueError):
        return False
