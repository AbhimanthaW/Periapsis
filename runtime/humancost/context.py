"""Simulated visibility and astronaut readings for the human-cost report."""

import math

from runtime.marswalk.errors import MarswalkError


ENVIRONMENT = {"visibility_distance_m"}
OBSERVATIONS = {"heart_rate_bpm", "suit_temperature_c"}


def _invalid(reason):
    raise MarswalkError("INVALID_HUMAN_FACTORS", reason)


def _fields(raw, allowed, label):
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("data_status") != "simulated":
        _invalid(f"{label} must be an object tagged data_status='simulated'")
    if len(raw) < 2:
        _invalid(f"{label} must contain at least one value")
    unknown = set(raw) - allowed - {"data_status"}
    if unknown:
        _invalid(f"{label} has unknown fields {sorted(unknown)}")
    result = {"data_status": "simulated"}
    for key in sorted(set(raw) - {"data_status"}):
        value = raw[key]
        if type(value) not in (int, float) or not math.isfinite(value):
            _invalid(f"{label}.{key} must be finite")
        if key == "visibility_distance_m" and value < 0:
            _invalid(f"{label}.{key} must be nonnegative")
        if key == "heart_rate_bpm" and value <= 0:
            _invalid(f"{label}.{key} must be positive")
        if key == "suit_temperature_c" and value <= -273.15:
            _invalid(f"{label}.{key} must be above absolute zero")
        result[key] = value
    return result


def validate_context(environment, observations, walker_ids):
    env = _fields(environment, ENVIRONMENT, "phase.environment")
    if observations is None:
        return env, {}
    if not isinstance(observations, dict):
        _invalid("phase.observations must be keyed by astronaut id")
    unknown = set(observations) - set(walker_ids)
    if unknown:
        _invalid(f"phase.observations has unknown astronaut ids {sorted(unknown)}")
    if any(raw is None for raw in observations.values()):
        _invalid("phase.observations entries cannot be null")
    return env, {name: _fields(raw, OBSERVATIONS, f"phase.observations.{name}")
                 for name, raw in sorted(observations.items())}
