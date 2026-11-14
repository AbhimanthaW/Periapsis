"""Strict, versioned inputs for the simulated human consumables calculator."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping

from runtime.marswalk.errors import MarswalkError


@dataclass(frozen=True)
class Astronaut:
    id: str
    mass_kg: float
    metabolic_baseline_w: float
    mechanical_efficiency: float
    suit_joint_power_w: float
    respiratory_exchange_ratio: float
    sustainable_metabolic_w: float
    peak_metabolic_w: float
    initial_oxygen_g: float
    initial_cooling_water_kg: float
    initial_drinking_water_l: float
    drinking_water_l_h: float
    initial_battery_wh: float
    co2_removal_g_s: float


@dataclass(frozen=True)
class Crew:
    provenance: str
    reference_id: str
    astronauts: tuple[Astronaut, ...]


@dataclass(frozen=True)
class Policy:
    values: dict
    statuses: dict
    base_profile: dict


ASTRONAUT_NUMBERS = tuple(k for k in Astronaut.__dataclass_fields__ if k != "id")
POLICY_VALUES = (
    "mars_gravity_m_s2", "net_external_heat_w", "cooling_water_heat_j_kg",
    "electrical_base_w", "cooling_electrical_w_per_thermal_w",
    "oxygen_reserve_fraction", "oxygen_raised_fraction",
    "cooling_water_reserve_fraction", "cooling_water_raised_fraction",
    "battery_reserve_fraction", "battery_raised_fraction",
    "drinking_water_reserve_l", "drinking_water_raised_l",
    "utilisation_caution", "utilisation_warning", "utilisation_fail",
    "demand_elevated", "demand_high", "time_reserve_s", "slope_candidates_deg",
)


def _refuse(reason):
    raise MarswalkError("INVALID_HUMAN_FACTORS", reason)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read(source):
    if isinstance(source, Mapping):
        return dict(source)
    try:
        return json.loads(Path(source).read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_pairs,
                          parse_constant=lambda token: _refuse(f"non-finite number {token}"))
    except (OSError, ValueError, TypeError) as error:
        if isinstance(error, MarswalkError):
            raise
        _refuse(f"cannot read JSON input: {error}")


def _object(value, expected, name):
    if not isinstance(value, dict):
        _refuse(f"{name} must be an object")
    missing, unknown = set(expected) - value.keys(), value.keys() - set(expected)
    if missing or unknown:
        _refuse(f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return value


def _number(value, name, *, minimum=0, maximum=None, strictly_positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        _refuse(f"{name} must be a finite number")
    if value < minimum or (strictly_positive and value == 0) or (maximum is not None and value > maximum):
        _refuse(f"{name} is outside its allowed range")
    return float(value)


def load_crew(source):
    data = _object(_read(source), ("schema", "provenance", "reference_id", "astronauts"), "crew")
    if data["schema"] != "crew-human-factors-v1" or data["provenance"] != "simulated":
        _refuse("crew schema or provenance is unsupported")
    if not isinstance(data["reference_id"], str) or not data["reference_id"]:
        _refuse("reference_id must be a nonempty string")
    if not isinstance(data["astronauts"], list) or len(data["astronauts"]) < 2:
        _refuse("astronauts must include a reference and at least one walker")
    people = []
    for index, raw in enumerate(data["astronauts"]):
        person = _object(raw, ("id", *ASTRONAUT_NUMBERS), f"astronauts[{index}]")
        if not isinstance(person["id"], str) or not person["id"].strip():
            _refuse(f"astronauts[{index}].id must be a nonempty string")
        values = {k: _number(person[k], f"{person['id']}.{k}",
                             strictly_positive=k != "co2_removal_g_s")
                  for k in ASTRONAUT_NUMBERS}
        if not 0 < values["mechanical_efficiency"] <= 1:
            _refuse(f"{person['id']}.mechanical_efficiency must be in (0, 1]")
        if not 0.7 <= values["respiratory_exchange_ratio"] <= 1.0:
            _refuse(f"{person['id']}.respiratory_exchange_ratio must be in [0.7, 1.0]")
        if values["sustainable_metabolic_w"] >= values["peak_metabolic_w"]:
            _refuse(f"{person['id']}: sustainable power must be below peak power")
        people.append(Astronaut(person["id"], **values))
    ids = [person.id for person in people]
    if len(set(ids)) != len(ids) or data["reference_id"] not in ids:
        _refuse("astronaut ids must be unique and include reference_id")
    return Crew("simulated", data["reference_id"], tuple(sorted(people, key=lambda p: p.id)))


def load_policy(source):
    data = _object(_read(source), ("schema", "parameters", "base_profile"), "policy")
    if data["schema"] != "human-cost-policy-v1":
        _refuse("policy schema is unsupported")
    params = _object(data["parameters"], POLICY_VALUES, "policy.parameters")
    values, statuses = {}, {}
    for key in POLICY_VALUES:
        entry = _object(params[key], ("value", "status"), f"policy.parameters.{key}")
        if entry["status"] not in ("assumed", "sourced"):
            _refuse(f"{key}.status must be assumed or sourced")
        statuses[key] = entry["status"]
        if key == "slope_candidates_deg":
            angles = entry["value"]
            if not isinstance(angles, list) or not angles or any(
                _number(a, "slope candidate", strictly_positive=True) >= 90 for a in angles
            ):
                _refuse("slope_candidates_deg must contain angles in (0, 90)")
            if len(set(angles)) != len(angles):
                _refuse("slope candidates must be unique")
            values[key] = tuple(sorted(map(float, angles), reverse=True))
        else:
            values[key] = _number(entry["value"], key)
    for key in ("mars_gravity_m_s2", "cooling_water_heat_j_kg", "electrical_base_w"):
        if values[key] == 0:
            _refuse(f"{key} must be positive")
    for key in ("oxygen", "cooling_water", "battery"):
        low, high = values[f"{key}_reserve_fraction"], values[f"{key}_raised_fraction"]
        if not 0 <= low <= high < 1:
            _refuse(f"{key} reserve fractions must satisfy 0 <= default <= raised < 1")
    if values["drinking_water_raised_l"] < values["drinking_water_reserve_l"]:
        _refuse("raised drinking water reserve must be at least the default")
    if not (0 <= values["utilisation_caution"] < values["utilisation_warning"]
            < values["utilisation_fail"] == 1):
        _refuse("utilisation bands must increase to 1")
    if not 1 <= values["demand_elevated"] < values["demand_high"]:
        _refuse("demand bands must increase from at least 1")
    if int(values["time_reserve_s"]) != values["time_reserve_s"] or values["time_reserve_s"] > 86400:
        _refuse("time_reserve_s must be whole seconds within 0..86400")
    profile = _object(data["base_profile"], ("v_flat_mps", "pace_model", "neighbours"), "base_profile")
    if profile["pace_model"] != "tobler_scaled" or type(profile["neighbours"]) is not int or profile["neighbours"] not in (4, 8):
        _refuse("base_profile must use tobler_scaled with 4 or 8 neighbours")
    _number(profile["v_flat_mps"], "v_flat_mps", strictly_positive=True)
    return Policy(values, statuses, dict(profile))
