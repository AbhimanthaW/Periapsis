"""Operating profiles fed from data (Subsystem 01).

Human and rover numbers are inputs, not constants. A profile is a JSON object
with a ``platform`` of ``human`` or ``rover`` and exactly the fields of
HumanProfile or RoverProfile. Unknown keys are refused, so a misspelt field
cannot silently fall back to a default. Battery fields may be given in kWh
(``battery_capacity_kwh``, ``battery_reserve_kwh``, ``initial_charge_kwh``)
instead of joules, but not both.

    {"platform": "rover", "profile_id": "my-rover", "source_type": "hypothetical",
     "mass_kg": 1200, "payload_kg": 300, ...}
"""
from dataclasses import fields
import json
from pathlib import Path

from .config import HumanProfile, RoverProfile
from .errors import MarswalkError

KWH_J = 3.6e6
KWH_ALIASES = {"battery_capacity_kwh": "battery_capacity_j", "battery_reserve_kwh": "battery_reserve_j",
               "initial_charge_kwh": "initial_charge_j"}
CLASSES = {"human": HumanProfile, "rover": RoverProfile}


def _read(source):
    if isinstance(source, dict):
        return dict(source)
    path = Path(source)
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise MarswalkError("INVALID_PROFILE", f"cannot read profile {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise MarswalkError("INVALID_PROFILE", f"profile {path} is not valid JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise MarswalkError("INVALID_PROFILE", "a profile must be a JSON object")
    return data


def load_profile(source):
    """Build a validated HumanProfile or RoverProfile from a path or a dict."""
    data = _read(source)
    platform = data.get("platform")
    if not isinstance(platform, str) or platform not in CLASSES:
        raise MarswalkError("INVALID_PROFILE", "profile platform must be 'human' or 'rover'")
    cls = CLASSES[platform]
    for alias, target in KWH_ALIASES.items():
        if alias in data:
            if platform != "rover":
                raise MarswalkError("INVALID_PROFILE", f"{alias} applies only to rover profiles")
            if target in data:
                raise MarswalkError("INVALID_PROFILE", f"give {alias} or {target}, not both")
            value = data.pop(alias)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MarswalkError("INVALID_PROFILE", f"{alias} must be a number")
            try:
                data[target] = float(value) * KWH_J
            except OverflowError as error:
                raise MarswalkError("INVALID_PROFILE", f"{alias} is outside the supported range") from error
    for key in ("profile_id", "pace_model", "pace_scenario", "source_type", "power_source", "provenance", "source"):
        if key in data and not isinstance(data[key], str):
            raise MarswalkError("INVALID_PROFILE", f"{key} must be a string")
    if "neighbours" in data and type(data["neighbours"]) is not int:
        raise MarswalkError("INVALID_PROFILE", "neighbours must be an integer")
    allowed = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MarswalkError("INVALID_PROFILE", f"unknown {platform} profile field(s): {', '.join(unknown)}")
    try:
        return cls(**data)
    except TypeError as error:
        raise MarswalkError("INVALID_PROFILE", f"{platform} profile is incomplete: {error}") from error


def profile_to_dict(profile):
    """The JSON form accepted by load_profile."""
    return {f.name: getattr(profile, f.name) for f in fields(profile)}
