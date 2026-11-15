"""Shared SIMULATED fixture for the Trade-off Envelope tests (not a test module).

Synthetic demo terrain, the example crew with smaller batteries, a nominal
simulated weather feed, and the example envelope. With these inputs:
direct_return and science:photo-set are GREEN, science:transect is AMBER
(EV2's battery crosses its L1 floor but holds the L2 floor), and both
two-stop options are RED.
"""
import copy
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path

from runtime.humancost import load_crew, load_policy, prepare
from runtime.marswalk import feed_from_dict, plan_marswalk
from runtime.marswalk.demo import DEMO_TIME_UTC, demo_inputs
from runtime.tradeoff import assess, envelope_body_sha256, load_envelope

ROOT = Path(__file__).resolve().parents[2]
CREW = ROOT / "runtime/examples/crew-human-factors.json"
POLICY = ROOT / "runtime/examples/human-cost-policy.json"
ENVELOPE = ROOT / "runtime/examples/tradeoff-envelope-simulated.json"
NOW = DEMO_TIME_UTC                                   # 2021-02-18T20:43:49Z
CLASS_ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2}
WEATHER = {"provenance": "simulated", "required": False, "max_age_s": 600,
           "stations": [{"id": "base-1", "cell": [80, 40], "provenance": "simulated"}],
           "messages": [{"station_id": "base-1", "variable": "wind_speed", "value": 8.0, "unit": "m/s",
                         "kind": "observed", "time_utc": "2021-02-18T20:41:00Z", "provenance": "simulated"}]}
SIGNATURES = [
    {"role": "flight_director", "id": "SIM-FD-01", "reason": "simulated: priority-1 transect", "signed_utc": NOW},
    {"role": "crew_surgeon", "id": "SIM-CS-01", "reason": "simulated: margins reviewed", "signed_utc": NOW},
]
CONSENT = [{"astronaut": "EV1", "response": "consent"}, {"astronaut": "EV2", "response": "consent"}]


def crew_data(battery_wh=155.0):
    data = json.loads(CREW.read_text())
    for person in data["astronauts"]:
        person["initial_battery_wh"] = battery_wh
    return data


def policy_data():
    return json.loads(POLICY.read_text())


def envelope_data():
    return json.loads(ENVELOPE.read_text())


def sign(data):
    """Re-sign an edited envelope so only the edit under test can cause a refusal."""
    digest = envelope_body_sha256(data)
    for signature in data["signatures"]:
        signature["sha256"] = digest
    return data


def telemetry_data(crew, policy, *, observed_utc="2021-02-18T20:43:00Z", scale=1.0):
    """Readings generated from the model itself (ratio ``scale`` to nominal)."""
    loaded = load_crew(crew)
    people = {p.id: p for p in loaded.astronauts}
    rows = []
    for item in prepare(loaded, load_policy(policy))["astronauts"]:
        oxygen = scale * item["rates_flat_per_h"]["oxygen"] / 3600 * 600
        rer = people[item["id"]].respiratory_exchange_ratio
        rows.append({"id": item["id"], "elapsed_s": 600, "oxygen_used_g": oxygen,
                     "co2_produced_g": oxygen * rer * 44.01 / 31.998})
    return {"schema": "tradeoff-telemetry-v1", "provenance": "simulated", "observed_utc": observed_utc,
            "astronauts": rows}


@lru_cache(maxsize=None)
def marswalk_plan(remaining_s=6 * 3600, weather_json=json.dumps(WEATHER), crew_status="ok", multistop=True):
    baseline, snapshot = demo_inputs(remaining_s=remaining_s, crew_status=crew_status)
    if weather_json is not None:
        snapshot = replace(snapshot, weather=feed_from_dict(json.loads(weather_json)))
    return plan_marswalk(baseline, snapshot, multistop=multistop)


def run(*, crew=None, policy=None, envelope=None, telemetry="model", plan=None, now=NOW,
        decision_window_s=3600, one_way_light_time_s=600, accepted=0):
    crew = crew_data() if crew is None else crew
    policy = policy_data() if policy is None else policy
    loaded = load_envelope(sign(copy.deepcopy(envelope_data() if envelope is None else envelope)), now_utc=now)
    if telemetry == "model":
        telemetry = telemetry_data(crew, policy)
    result = assess(marswalk_plan() if plan is None else plan, crew, policy, loaded, now_utc=now,
                    telemetry=telemetry, decision_window_s=decision_window_s,
                    one_way_light_time_s=one_way_light_time_s, accepted_amber_count=accepted)
    return result, loaded


def classes(result):
    return {a["option_id"]: a["class"] for a in result["assessments"]}


def option(result, option_id):
    return next(a for a in result["assessments"] if a["option_id"] == option_id)


def green_only(result):
    return "AMBER" not in classes(result).values()


def never_better(before, after):
    """No option moved to a better class."""
    return all(CLASS_ORDER[after[k]] >= CLASS_ORDER[before[k]] for k in before)
