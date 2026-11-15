"""T0 · Envelope contract ``tradeoff-envelope-v1``.

The envelope is the pre-signed record of what authorised humans agreed before
the EVA: the nominal limits' companion values (L1), the bounded exceptions per
science priority class (L2), who may accept them, and when the agreement ends.

Validation is strict, in the style of ``runtime.marswalk.profiles``: unknown
keys are refused, a missing key is refused (nothing is defaulted), every number
carries an explicit unit and a status, and the provenance label must say
``simulated``. Two rules are structural:

  * An L2 reserve floor may not go below the immutable L0 floor in this file.
  * A personal value may only tighten. That check needs the crew and policy,
    so it runs in ``reserve_floors``.

L0 lives in code on purpose: changing it is a code change with review, never
an input. The L0 numbers are ASSUMPTIONS awaiting review (plan decision D3).
"""
from dataclasses import dataclass

from ._common import digest, entry, obj, read_json, refuse, text, utc

CODE = "INVALID_ENVELOPE"
SCHEMA = "tradeoff-envelope-v1"

FLIGHT_DIRECTOR, CREW_SURGEON, SCIENCE_LEAD = "flight_director", "crew_surgeon", "science_lead"
ACCEPTING_ROLES = (FLIGHT_DIRECTOR, CREW_SURGEON)

# Resources whose reserve is a fraction of the starting store. Drinking water has
# an absolute reserve in the human-cost policy and no L2 exception.
FLOOR_RESOURCES = ("oxygen", "cooling_water", "battery")

# L0: fraction of the starting store that no pre-signed exception may go below.
# status: assumed (team choice, not a sourced physiological or suit limit).
L0_RESERVE_FLOOR_FRACTION = {"oxygen": 0.10, "cooling_water": 0.10, "battery": 0.10}

KEYS = ("schema", "provenance", "envelope_id", "expires_utc", "consumption_margin_factor", "nominal",
        "exceptions", "objectives", "risk_budget_per_eva", "max_accepted_amber_per_eva", "acceptance_valid_s",
        "telemetry", "personal_overrides", "authority", "signatures")


@dataclass(frozen=True)
class ExceptionBounds:
    priority_class: int
    p_breach_max: float                 # P1 only; unused by the deterministic classifier
    reserve_floor_fraction: tuple       # ((resource, fraction), ...)
    requires_roles: tuple

    def floor(self, resource):
        return dict(self.reserve_floor_fraction).get(resource)


@dataclass(frozen=True)
class Envelope:
    envelope_id: str
    expires: object                     # aware datetime
    expires_utc: str
    consumption_margin_factor: float
    p_breach_nominal: float             # P1 only
    exceptions: tuple                   # ExceptionBounds, by priority class
    objectives: tuple                   # ((task_id, priority_class), ...) set by the science lead
    risk_budget_per_eva: float          # P1 only (sum of accepted excess probability)
    max_accepted_amber_per_eva: int     # P0 form of the risk budget
    acceptance_valid_s: int
    telemetry_max_age_s: float
    telemetry_min_ratio: float
    telemetry_co2_o2_tolerance: float
    personal_overrides: tuple           # ((astronaut, ((resource, fraction), ...)), ...)
    earth_roles: tuple
    habitat_delegate: str | None
    response_allowance_s: float
    signatures: tuple                   # ((role, id, signed_utc), ...)
    body_sha256: str                    # what each signature covers (the envelope without "signatures")
    sha256: str                         # the whole document, signatures included

    def exception(self, priority_class):
        return next((e for e in self.exceptions if e.priority_class == priority_class), None)

    def priority_class(self, task_id):
        return dict(self.objectives).get(task_id)

    def expired(self, now):
        return now >= self.expires


def envelope_body_sha256(data):
    """Hash that every envelope signature must carry: the document minus its signatures."""
    return digest({k: v for k, v in data.items() if k != "signatures"})


def _positive_int(value, name):
    if type(value) is not int or value < 1:
        refuse(CODE, f"{name} must be a positive integer")
    return value


def _fractions(value, name, *, floor_of_l0):
    if not isinstance(value, dict) or not value:
        refuse(CODE, f"{name} must name at least one resource")
    unknown = sorted(set(value) - set(FLOOR_RESOURCES))
    if unknown:
        refuse(CODE, f"{name}: unsupported resource(s) {unknown}; allowed {list(FLOOR_RESOURCES)}")
    out = []
    for resource in FLOOR_RESOURCES:
        if resource not in value:
            continue
        fraction = entry(value[resource], f"{name}.{resource}", "fraction_of_initial", CODE,
                         minimum=0, maximum=1, max_open=True)
        if floor_of_l0 and fraction < L0_RESERVE_FLOOR_FRACTION[resource]:
            refuse(CODE, f"{name}.{resource} = {fraction:g} relaxes the immutable L0 floor "
                         f"{L0_RESERVE_FLOOR_FRACTION[resource]:g}; L0 cannot be changed by an envelope")
        out.append((resource, fraction))
    return tuple(out)


def load_envelope(source, *, now_utc):
    """Validate an envelope (path or mapping) as of ``now_utc``. Refuses; never defaults."""
    data = obj(read_json(source, CODE), KEYS, "envelope", CODE)
    now = utc(now_utc, "now_utc", CODE)
    if data["schema"] != SCHEMA:
        refuse(CODE, f"schema must be {SCHEMA!r}")
    if data["provenance"] != "simulated":
        refuse(CODE, "provenance must be 'simulated'; no other envelope source exists in this project")
    envelope_id = text(data["envelope_id"], "envelope_id", CODE)
    expires = utc(data["expires_utc"], "expires_utc", CODE)
    if expires <= now:
        refuse(CODE, f"envelope expired at {data['expires_utc']}")
    factor = entry(data["consumption_margin_factor"], "consumption_margin_factor", "ratio", CODE, minimum=1)
    nominal = obj(data["nominal"], ("p_breach_max",), "nominal", CODE)
    p_nominal = entry(nominal["p_breach_max"], "nominal.p_breach_max", "probability", CODE,
                      minimum=0, maximum=1, min_open=True, max_open=True)

    if not isinstance(data["exceptions"], list):
        refuse(CODE, "exceptions must be a list (empty means no exception was agreed)")
    exceptions = []
    for index, raw in enumerate(data["exceptions"]):
        name = f"exceptions[{index}]"
        item = obj(raw, ("priority_class", "p_breach_max", "reserve_floor_fraction", "requires_roles",
                         "requires_crew_consent"), name, CODE)
        priority = _positive_int(item["priority_class"], f"{name}.priority_class")
        p_exception = entry(item["p_breach_max"], f"{name}.p_breach_max", "probability", CODE,
                            minimum=p_nominal, maximum=1, max_open=True)
        roles = item["requires_roles"]
        if not isinstance(roles, list) or sorted(roles) != sorted(ACCEPTING_ROLES):
            refuse(CODE, f"{name}.requires_roles must be exactly {list(ACCEPTING_ROLES)}; "
                         f"the {SCIENCE_LEAD} sets priorities and cannot accept risk")
        if item["requires_crew_consent"] is not True:
            refuse(CODE, f"{name}.requires_crew_consent must be true; consent is never assumed")
        exceptions.append(ExceptionBounds(priority, p_exception,
                                          _fractions(item["reserve_floor_fraction"],
                                                     f"{name}.reserve_floor_fraction", floor_of_l0=True),
                                          tuple(ACCEPTING_ROLES)))
    classes = [e.priority_class for e in exceptions]
    if len(set(classes)) != len(classes):
        refuse(CODE, "exceptions must have unique priority classes")

    if not isinstance(data["objectives"], list):
        refuse(CODE, "objectives must be a list")
    objectives = []
    for index, raw in enumerate(data["objectives"]):
        item = obj(raw, ("task_id", "priority_class", "set_by"), f"objectives[{index}]", CODE)
        if item["set_by"] != SCIENCE_LEAD:
            refuse(CODE, f"objectives[{index}].set_by must be {SCIENCE_LEAD!r}")
        objectives.append((text(item["task_id"], f"objectives[{index}].task_id", CODE),
                           _positive_int(item["priority_class"], f"objectives[{index}].priority_class")))
    if len({t for t, _ in objectives}) != len(objectives):
        refuse(CODE, "objectives must have unique task ids")

    risk_budget = entry(data["risk_budget_per_eva"], "risk_budget_per_eva", "probability", CODE,
                        minimum=0, maximum=1, max_open=True)
    cap = entry(data["max_accepted_amber_per_eva"], "max_accepted_amber_per_eva", "count", CODE, minimum=0)
    valid_s = entry(data["acceptance_valid_s"], "acceptance_valid_s", "s", CODE, minimum=0, maximum=86400,
                    min_open=True)
    if cap != int(cap) or valid_s != int(valid_s):
        refuse(CODE, "max_accepted_amber_per_eva and acceptance_valid_s must be whole numbers")

    telemetry = obj(data["telemetry"], ("max_age_s", "min_observed_to_nominal_ratio",
                                        "co2_o2_tolerance_fraction"), "telemetry", CODE)
    max_age = entry(telemetry["max_age_s"], "telemetry.max_age_s", "s", CODE, minimum=0, min_open=True)
    min_ratio = entry(telemetry["min_observed_to_nominal_ratio"], "telemetry.min_observed_to_nominal_ratio",
                      "ratio", CODE, minimum=0, maximum=1, min_open=True)
    tolerance = entry(telemetry["co2_o2_tolerance_fraction"], "telemetry.co2_o2_tolerance_fraction",
                      "fraction", CODE, minimum=0, maximum=1, min_open=True, max_open=True)

    if not isinstance(data["personal_overrides"], list):
        refuse(CODE, "personal_overrides must be a list")
    overrides = []
    for index, raw in enumerate(data["personal_overrides"]):
        name = f"personal_overrides[{index}]"
        item = obj(raw, ("astronaut", "reserve_floor_fraction", "set_by", "reason", "visibility"), name, CODE)
        if item["set_by"] != CREW_SURGEON:
            refuse(CODE, f"{name}.set_by must be {CREW_SURGEON!r}")
        if item["visibility"] != "surgeon_only":
            refuse(CODE, f"{name}.visibility must be 'surgeon_only'")
        text(item["reason"], f"{name}.reason", CODE)
        overrides.append((text(item["astronaut"], f"{name}.astronaut", CODE),
                          _fractions(item["reserve_floor_fraction"], f"{name}.reserve_floor_fraction",
                                     floor_of_l0=True)))
    if len({a for a, _ in overrides}) != len(overrides):
        refuse(CODE, "personal_overrides must name each astronaut once")

    authority = obj(data["authority"], ("earth_roles", "habitat_delegate", "response_allowance_s"),
                    "authority", CODE)
    if not isinstance(authority["earth_roles"], list) or sorted(authority["earth_roles"]) != sorted(ACCEPTING_ROLES):
        refuse(CODE, f"authority.earth_roles must be exactly {list(ACCEPTING_ROLES)}")
    delegate = authority["habitat_delegate"]
    if delegate is not None:
        text(delegate, "authority.habitat_delegate", CODE)
        if delegate in (*ACCEPTING_ROLES, SCIENCE_LEAD):
            refuse(CODE, "authority.habitat_delegate must be a distinct role; it cannot be an Earth role "
                         f"or the {SCIENCE_LEAD}")
    allowance = entry(authority["response_allowance_s"], "authority.response_allowance_s", "s", CODE, minimum=0)

    body_hash = envelope_body_sha256(data)
    if not isinstance(data["signatures"], list):
        refuse(CODE, "signatures must be a list")
    signatures = []
    for index, raw in enumerate(data["signatures"]):
        name = f"signatures[{index}]"
        item = obj(raw, ("role", "id", "signed_utc", "sha256"), name, CODE)
        if item["role"] == SCIENCE_LEAD:
            refuse(CODE, f"{name}: a {SCIENCE_LEAD} signature on a risk envelope is refused; "
                         "the role that values science cannot accept risk")
        if item["role"] not in ACCEPTING_ROLES:
            refuse(CODE, f"{name}.role must be one of {list(ACCEPTING_ROLES)}")
        signed = utc(item["signed_utc"], f"{name}.signed_utc", CODE)
        if signed > now:
            refuse(CODE, f"{name}.signed_utc is in the future")
        if item["sha256"] != body_hash:
            refuse(CODE, f"{name}.sha256 does not match the envelope body; the envelope changed after signing")
        signatures.append((item["role"], text(item["id"], f"{name}.id", CODE), item["signed_utc"]))
    roles = [role for role, _, _ in signatures]
    if sorted(roles) != sorted(ACCEPTING_ROLES):
        refuse(CODE, f"envelope needs exactly one signature from each of {list(ACCEPTING_ROLES)}; got {sorted(roles)}")
    if len({signer for _, signer, _ in signatures}) != len(signatures):
        refuse(CODE, "envelope signatures must come from different people")

    return Envelope(envelope_id, expires, data["expires_utc"], factor, p_nominal,
                    tuple(sorted(exceptions, key=lambda e: e.priority_class)), tuple(sorted(objectives)),
                    risk_budget, int(cap), int(valid_s), max_age, min_ratio, tolerance,
                    tuple(sorted(overrides)), tuple(ACCEPTING_ROLES), delegate, allowance,
                    tuple(sorted(signatures)), body_hash, digest(data))


def reserve_floors(envelope, crew, policy, prepared):
    """Absolute reserve floors per walking astronaut: ``{id: {"l1": {res: x}, "l2": {class: {res: x}}}}``.

    L1 is the human-cost mission reserve (already raised for higher-demand
    astronauts), tightened by any surgeon override. L2 replaces the mission
    DEFAULT fraction with the exception fraction and keeps both personal
    tightenings: the raised-demand increment and the surgeon override.
    A personal value looser than the mission value is refused.
    """
    people = {p.id: p for p in crew.astronauts}
    walkers = [a["id"] for a in prepared["astronauts"]]
    overrides = {astronaut: dict(values) for astronaut, values in envelope.personal_overrides}
    unknown = sorted(set(overrides) - set(walkers))
    if unknown:
        refuse(CODE, f"personal_overrides name astronaut(s) who are not walking: {unknown}")
    v = policy.values
    for exc in envelope.exceptions:
        for resource, fraction in exc.reserve_floor_fraction:
            if fraction > v[f"{resource}_reserve_fraction"]:
                refuse(CODE, f"exception for priority class {exc.priority_class}: {resource} floor {fraction:g} is "
                             f"above the mission reserve {v[f'{resource}_reserve_fraction']:g}; an exception "
                             "cannot tighten, change the mission policy instead")
    initial_key = {"oxygen": "initial_oxygen_g", "cooling_water": "initial_cooling_water_kg",
                   "battery": "initial_battery_wh"}
    result = {}
    for item in prepared["astronauts"]:
        person, raised = people[item["id"]], item["demand_class"] != "nominal"
        l1, l2 = {}, {exc.priority_class: {} for exc in envelope.exceptions}
        for resource in FLOOR_RESOURCES:
            default = v[f"{resource}_reserve_fraction"]
            mission = v[f"{resource}_raised_fraction"] if raised else default
            personal = overrides.get(person.id, {}).get(resource)
            if personal is not None and personal < mission:
                refuse(CODE, f"personal override for {person.id} {resource} = {personal:g} is looser than the "
                             f"mission value {mission:g}; personal values may only tighten")
            initial = getattr(person, initial_key[resource])
            l1_fraction = mission if personal is None else personal
            l1[resource] = l1_fraction * initial
            for exc in envelope.exceptions:
                agreed = exc.floor(resource)
                if agreed is None:
                    fraction = l1_fraction
                else:
                    fraction = agreed + (mission - default)
                    if personal is not None:
                        fraction = max(fraction, personal)
                    fraction = min(fraction, l1_fraction)
                l2[exc.priority_class][resource] = fraction * initial
        water = v["drinking_water_raised_l"] if raised else v["drinking_water_reserve_l"]
        l1["drinking_water"] = water
        for floors in l2.values():
            floors["drinking_water"] = water
        result[person.id] = {"l1": l1, "l2": l2}
    return result


__all__ = ["ACCEPTING_ROLES", "CREW_SURGEON", "Envelope", "ExceptionBounds", "FLIGHT_DIRECTOR",
           "FLOOR_RESOURCES", "L0_RESERVE_FLOOR_FRACTION", "SCIENCE_LEAD", "SCHEMA", "envelope_body_sha256",
           "load_envelope", "reserve_floors"]
