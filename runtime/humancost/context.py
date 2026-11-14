"""Optional, explicitly simulated phase context; no inferred physiological effects."""

import math

from runtime.marswalk.errors import MarswalkError


# These names match the concepts and units in documentation/EVA-CONTEXT.md.
ENVIRONMENT = {
    "radiation_dose_rate_mgy_day": ("mGy/day", 0, None),
    "temperature_k": ("K", 0, None),
    "wind_speed_m_s": ("m/s", 0, None),
    "atmospheric_pressure_pa": ("Pa", 0, None),
    "dust_concentration_mg_m3": ("mg/m3", 0, None),
    "solar_illumination_deg": ("degrees", -90, 90),
    "surface_traction": ("1", 0, None),
    "regolith_sinkage_mm": ("mm", 0, None),
    "obstacle_density_count_m2": ("count/m2", 0, None),
    "communication_signal_available": ("boolean", None, None),
    "visibility_distance_m": ("m", 0, None),
    "communication_latency_s": ("s", 0, None),
}
OBSERVATIONS = {
    "heart_rate_bpm": ("bpm", 0, None),
    "core_body_temperature_c": ("degC", None, None),
    "suit_internal_pressure_kpa_abs": ("kPa absolute", 0, None),
}


def _invalid(reason):
    raise MarswalkError("INVALID_HUMAN_FACTORS", reason)


def _fields(raw, allowed, label):
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("data_status") != "simulated":
        _invalid(f"{label} must be an object tagged data_status='simulated'")
    if len(raw) < 2:
        _invalid(f"{label} must contain at least one value")
    unknown = set(raw) - set(allowed) - {"data_status"}
    if unknown:
        _invalid(f"{label} has unknown fields {sorted(unknown)}")
    result = {"data_status": "simulated"}
    for key in sorted(set(raw) - {"data_status"}):
        value = raw[key]
        if key == "communication_signal_available":
            if type(value) is not bool:
                _invalid(f"{label}.{key} must be boolean")
        else:
            _, low, high = allowed[key]
            if type(value) not in (int, float) or not math.isfinite(value):
                _invalid(f"{label}.{key} must be finite")
            if (low is not None and value < low) or (high is not None and value > high):
                _invalid(f"{label}.{key} is outside its allowed range")
            if key in ("temperature_k", "atmospheric_pressure_pa", "heart_rate_bpm",
                       "suit_internal_pressure_kpa_abs") and value == 0:
                _invalid(f"{label}.{key} must be positive")
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
