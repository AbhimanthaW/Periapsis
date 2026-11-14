"""Telemetry gate ``tradeoff-telemetry-v1`` (simulated or replayed readings only).

P0 uses telemetry for exactly one thing: deciding whether AMBER may be offered.
A reading NEVER lowers a consumption estimate, so a stuck or implausibly low
sensor cannot make any option look better; it can only remove AMBER.

Checks, per walking astronaut:
  * age        - older than the envelope's limit, or from the future  -> stale
  * low rate   - observed O2 rate below ``min_ratio`` x the nominal flat rate
                 -> implausibly low (stuck-low sensor)
  * cover      - observed O2 rate above ``margin factor`` x the nominal flat
                 rate -> the fixed margin factor no longer covers this person
  * agreement  - CO2 produced / O2 used differs from the declared respiratory
                 exchange ratio by more than the tolerance -> sensors disagree

No medical state is inferred from any reading.
"""
from ._common import number, obj, read_json, refuse, text, utc

CODE = "INVALID_TELEMETRY"
SCHEMA = "tradeoff-telemetry-v1"
O2_G_PER_L, CO2_G_PER_L = 31.998 / 22.414, 44.01 / 22.414     # same constants as runtime.humancost


def load_telemetry(source):
    data = obj(read_json(source, CODE), ("schema", "provenance", "observed_utc", "astronauts"), "telemetry", CODE)
    if data["schema"] != SCHEMA:
        refuse(CODE, f"schema must be {SCHEMA!r}")
    if data["provenance"] != "simulated":
        refuse(CODE, "provenance must be 'simulated'")
    utc(data["observed_utc"], "observed_utc", CODE)
    if not isinstance(data["astronauts"], list) or not data["astronauts"]:
        refuse(CODE, "astronauts must be a nonempty list")
    seen = set()
    for index, raw in enumerate(data["astronauts"]):
        name = f"astronauts[{index}]"
        item = obj(raw, ("id", "elapsed_s", "oxygen_used_g", "co2_produced_g"), name, CODE)
        if text(item["id"], f"{name}.id", CODE) in seen:
            refuse(CODE, f"{name}.id is repeated")
        seen.add(item["id"])
        number(item["elapsed_s"], f"{name}.elapsed_s", CODE, minimum=0, min_open=True)
        number(item["oxygen_used_g"], f"{name}.oxygen_used_g", CODE, minimum=0)
        number(item["co2_produced_g"], f"{name}.co2_produced_g", CODE, minimum=0)
    return data


def telemetry_gate(telemetry, envelope, crew, prepared, now):
    """(ok, reason, age_s). ``telemetry`` is a loaded document or None."""
    if telemetry is None:
        return False, "telemetry missing", None
    age = (now - utc(telemetry["observed_utc"], "observed_utc", CODE)).total_seconds()
    if age < 0:
        return False, "telemetry timestamp is in the future", age
    if age > envelope.telemetry_max_age_s:
        return False, f"telemetry is stale: {age:.0f} s old, limit {envelope.telemetry_max_age_s:.0f} s", age
    people = {p.id: p for p in crew.astronauts}
    readings = {item["id"]: item for item in telemetry["astronauts"]}
    walkers = [a["id"] for a in prepared["astronauts"]]
    if sorted(readings) != sorted(walkers):
        return False, f"telemetry must cover exactly the walking astronauts {sorted(walkers)}", age
    for item in prepared["astronauts"]:
        reading, person = readings[item["id"]], people[item["id"]]
        nominal_g_s = item["rates_flat_per_h"]["oxygen"] / 3600
        ratio = reading["oxygen_used_g"] / reading["elapsed_s"] / nominal_g_s
        if ratio < envelope.telemetry_min_ratio:
            return False, (f"{item['id']}: O2 reading is implausibly low ({ratio:.2f} x nominal, minimum "
                           f"{envelope.telemetry_min_ratio:.2f}); possible stuck sensor"), age
        if ratio > envelope.consumption_margin_factor:
            return False, (f"{item['id']}: O2 use is {ratio:.2f} x nominal, above the consumption margin factor "
                           f"{envelope.consumption_margin_factor:.2f}"), age
        expected = person.respiratory_exchange_ratio * CO2_G_PER_L / O2_G_PER_L
        observed = reading["co2_produced_g"] / reading["oxygen_used_g"]
        if abs(observed / expected - 1) > envelope.telemetry_co2_o2_tolerance:
            return False, f"{item['id']}: O2 and CO2 readings disagree; possible sensor fault", age
    return True, "telemetry fresh and plausible", age
