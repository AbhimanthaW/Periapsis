"""Deterministic estimates of simulated EVA consumables, separate from routing."""

from dataclasses import dataclass
import json
import math

from runtime.marswalk.errors import MarswalkError
from runtime.marswalk.profiles import load_profile

from .context import validate_context
from .factors import Crew, Policy, load_crew, load_policy


RESOURCES = ("oxygen", "cooling_water", "drinking_water", "battery")
UNITS = {"oxygen": "g", "cooling_water": "kg", "drinking_water": "L", "battery": "Wh"}


@dataclass(frozen=True)
class Phase:
    name: str
    kind: str
    time_s: float
    gain_m: float
    distance_m: float | None = None
    max_slope_deg: float | None = None
    environment: dict | None = None
    observations: dict | None = None


def _invalid(reason):
    raise MarswalkError("INVALID_HUMAN_FACTORS", reason)


def _inputs(crew, policy):
    return (crew if isinstance(crew, Crew) else load_crew(crew),
            policy if isinstance(policy, Policy) else load_policy(policy))


def _phases(phases, walker_ids):
    if not isinstance(phases, (list, tuple)) or not phases:
        _invalid("phases must be a nonempty ordered sequence")
    result, names = [], set()
    for raw in phases:
        try:
            phase = raw if isinstance(raw, Phase) else Phase(**raw)
        except (TypeError, ValueError) as error:
            _invalid(f"invalid phase: {error}")
        if not isinstance(phase.name, str) or not phase.name or phase.name in names:
            _invalid("phase names must be nonempty and unique")
        if phase.kind not in ("outbound", "dwell", "transfer", "return"):
            _invalid(f"{phase.name}: unsupported phase kind")
        for key, value in (("time_s", phase.time_s), ("gain_m", phase.gain_m)):
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                _invalid(f"{phase.name}.{key} must be finite and nonnegative")
        if phase.time_s == 0 and phase.gain_m != 0:
            _invalid(f"{phase.name}: zero-duration ascent is invalid")
        if phase.kind == "dwell" and phase.gain_m != 0:
            _invalid(f"{phase.name}: dwell cannot gain elevation")
        for key, value in (("distance_m", phase.distance_m), ("max_slope_deg", phase.max_slope_deg)):
            if value is not None and (type(value) not in (float, int) or not math.isfinite(value) or value < 0):
                _invalid(f"{phase.name}.{key} must be finite and nonnegative when supplied")
        if phase.max_slope_deg is not None and phase.max_slope_deg >= 90:
            _invalid(f"{phase.name}.max_slope_deg must be below 90")
        if phase.kind == "dwell" and (phase.distance_m not in (None, 0) or phase.max_slope_deg is not None):
            _invalid(f"{phase.name}: dwell has no walking distance or slope")
        if phase.time_s == 0 and phase.distance_m not in (None, 0):
            _invalid(f"{phase.name}: nonzero distance requires positive duration")
        if phase.distance_m is not None and phase.gain_m > phase.distance_m:
            _invalid(f"{phase.name}: elevation gain cannot exceed path length")
        if phase.distance_m is not None and phase.time_s and not math.isfinite(phase.distance_m / phase.time_s):
            _invalid(f"{phase.name}: derived walking speed is non-finite")
        environment, observations = validate_context(phase.environment, phase.observations, walker_ids)
        names.add(phase.name)
        result.append((phase, environment, observations))
    return result


def _flat_power(person):
    return person.metabolic_baseline_w + person.suit_joint_power_w / person.mechanical_efficiency


def _use(person, policy, time_s, gain_m):
    v = policy.values
    mechanical_j = person.mass_kg * v["mars_gravity_m_s2"] * gain_m
    metabolic_j = _flat_power(person) * time_s + mechanical_j / person.mechanical_efficiency
    heat_j = metabolic_j - mechanical_j + v["net_external_heat_w"] * time_s
    if not all(math.isfinite(x) for x in (mechanical_j, metabolic_j, heat_j)) or heat_j < 0:
        _invalid("non-finite or negative phase energy is unsupported")
    # Integrating the fixture's L/min rate over seconds cancels both factors of 60.
    oxygen_l = metabolic_j / (4184 * (3.941 + 1.106 * person.respiratory_exchange_ratio))
    use = {
        "oxygen": oxygen_l * 31.998 / 22.414,
        "cooling_water": heat_j / v["cooling_water_heat_j_kg"],
        "drinking_water": person.drinking_water_l_h * time_s / 3600,
        "battery": (v["electrical_base_w"] * time_s
                    + v["cooling_electrical_w_per_thermal_w"] * heat_j) / 3600,
    }
    co2_g = oxygen_l * person.respiratory_exchange_ratio * 44.01 / 22.414
    if not all(math.isfinite(x) for x in (*use.values(), co2_g)):
        _invalid("non-finite phase consumption is unsupported")
    return use, metabolic_j, mechanical_j, heat_j, co2_g


def _reserves(person, policy, raised):
    v = policy.values
    suffix = "raised" if raised else "reserve"
    return {
        "oxygen": person.initial_oxygen_g * v[f"oxygen_{suffix}_fraction"],
        "cooling_water": person.initial_cooling_water_kg * v[f"cooling_water_{suffix}_fraction"],
        "drinking_water": v[f"drinking_water_{suffix}_l"],
        "battery": person.initial_battery_wh * v[f"battery_{suffix}_fraction"],
    }


def _initial(person):
    return {"oxygen": person.initial_oxygen_g, "cooling_water": person.initial_cooling_water_kg,
            "drinking_water": person.initial_drinking_water_l, "battery": person.initial_battery_wh}


def _demand_ratios(person, reference, policy):
    personal, *_ = _use(person, policy, 3600, 0)
    baseline, *_ = _use(reference, policy, 3600, 0)
    return {resource: personal[resource] / baseline[resource] for resource in RESOURCES}


def _band(utilisation, policy):
    v = policy.values
    if utilisation > v["utilisation_fail"]:
        return "fail"
    if utilisation > v["utilisation_warning"]:
        return "warning"
    if utilisation > v["utilisation_caution"]:
        return "caution"
    return "nominal"


def _slope_limit(person, policy):
    v = policy.values
    speed = policy.base_profile["v_flat_mps"]
    for angle in v["slope_candidates_deg"]:
        grade = math.tan(math.radians(angle))
        tobler = speed * math.exp(-3.5 * (abs(grade + 0.05) - 0.05))
        power = _flat_power(person) + person.mass_kg * v["mars_gravity_m_s2"] * tobler * grade / person.mechanical_efficiency
        if not math.isfinite(power):
            _invalid(f"{person.id}: non-finite slope power")
        if power <= person.peak_metabolic_w:
            return angle
    _invalid(f"{person.id}: no candidate slope fits peak metabolic power")


def prepare(crew, policy):
    crew, policy = _inputs(crew, policy)
    reference = next(p for p in crew.astronauts if p.id == crew.reference_id)
    walkers = [p for p in crew.astronauts if p.id != crew.reference_id]
    astronauts = []
    for person in walkers:
        flat_use, *_ = _use(person, policy, 3600, 0)
        ratios = _demand_ratios(person, reference, policy)
        maximum = max(ratios.values())
        demand_class = ("high" if maximum > policy.values["demand_high"] else
                        "elevated" if maximum > policy.values["demand_elevated"] else "nominal")
        reserves = _reserves(person, policy, demand_class != "nominal")
        initial = _initial(person)
        usable = {r: initial[r] - reserves[r] for r in RESOURCES}
        if any(amount <= 0 for amount in usable.values()):
            _invalid(f"{person.id}: reserve leaves no usable resource")
        endurance = {r: usable[r] * 3600 / flat_use[r] for r in RESOURCES}
        if any(not math.isfinite(t) for t in endurance.values()):
            _invalid(f"{person.id}: non-finite flat endurance")
        limiting = min(RESOURCES, key=lambda r: (endurance[r], RESOURCES.index(r)))
        astronauts.append({
            "id": person.id, "demand_class": demand_class, "demand_ratios": ratios,
            "flat_power_w": _flat_power(person),
            "rates_flat_per_h": flat_use, "budget_s": math.floor(endurance[limiting]),
            "limiting_resource": limiting,
            "pace_scenario": "slow" if demand_class == "high" or _flat_power(person) > person.sustainable_metabolic_w else "nominal",
            "max_slope_deg": _slope_limit(person, policy), "ledgers": [], "risk": None,
            "band": None, "driver": None, "flags": [], "check": None, "reason": None,
        })
    limiting_person = min(astronauts, key=lambda a: (a["budget_s"], a["id"]))
    profile = {
        "platform": "human", "profile_id": "human-pair-personalised",
        "pace_model": policy.base_profile["pace_model"],
        "pace_scenario": "slow" if any(a["pace_scenario"] == "slow" for a in astronauts) else "nominal",
        "neighbours": policy.base_profile["neighbours"], "crew_size": len(walkers),
        "provenance": crew.provenance, "v_flat_mps": policy.base_profile["v_flat_mps"],
        "max_slope_deg": min(a["max_slope_deg"] for a in astronauts),
    }
    load_profile(profile)
    return {
        "schema": "human-cost-v1", "provenance": crew.provenance,
        "routing_inputs": {
            "remaining_s": min(86400, limiting_person["budget_s"]),
            "reserve_s": int(policy.values["time_reserve_s"]), "crew_status": "ok",
            "profile": profile,
            "limited_by": {"astronaut": limiting_person["id"], "resource": limiting_person["limiting_resource"]},
        },
        "astronauts": astronauts, "route": None,
        "policy": {key: {"value": list(value) if isinstance(value, tuple) else value,
                         "status": policy.statuses[key]} for key, value in policy.values.items()},
        "assumptions": ["Crew data are simulated, not telemetry or medical clearance.",
                        "Flat-rate endurance is a planning estimate; evaluate each route separately.",
                        "Drinking and cooling during dwell use the same rates as flat walking.",
                        "Time reserve is additional to the consumable reserves."],
    }


def evaluate(crew, policy, phases):
    crew, policy = _inputs(crew, policy)
    phases = _phases(phases, [p.id for p in crew.astronauts if p.id != crew.reference_id])
    payload = prepare(crew, policy)
    payload["phase_context"] = [
        {"phase": phase.name, "time_s": phase.time_s, "gain_m": phase.gain_m,
         "environment": environment}
        for phase, environment, _ in phases
    ]
    people = {p.id: p for p in crew.astronauts}
    for item in payload["astronauts"]:
        person = people[item["id"]]
        initial = _initial(person)
        reserves = _reserves(person, policy, item["demand_class"] != "nominal")
        cumulative = dict.fromkeys(RESOURCES, 0.0)
        rows = {r: [] for r in RESOURCES}
        first_breach = None
        energy_j = co2_excess_g = elapsed_s = 0.0
        phase_metrics = []
        for phase, _, observations in phases:
            use, energy, _, _, co2 = _use(person, policy, phase.time_s, phase.gain_m)
            energy_j += energy
            excess = max(0.0, co2 - person.co2_removal_g_s * phase.time_s)
            co2_excess_g += excess
            elapsed_s += phase.time_s
            if not all(math.isfinite(x) for x in (energy_j, co2_excess_g, elapsed_s)):
                _invalid(f"{person.id}: cumulative phase quantities are non-finite")
            phase_metrics.append({
                "phase": phase.name,
                "metabolic_power_w": energy / phase.time_s if phase.time_s else None,
                "walking_speed_m_s": (phase.distance_m / phase.time_s
                                       if phase.distance_m is not None and phase.time_s else None),
                "max_slope_deg": phase.max_slope_deg,
                "co2_excess_load_g": excess,
                "observations": observations.get(person.id),
            })
            if (phase.max_slope_deg is not None and phase.max_slope_deg > item["max_slope_deg"]
                    and first_breach is None):
                first_breach = {"resource": "terrain_slope", "phase": phase.name}
            if phase.time_s and energy / phase.time_s > person.peak_metabolic_w and first_breach is None:
                first_breach = {"resource": "metabolic_peak", "phase": phase.name}
            for resource in RESOURCES:
                cumulative[resource] += use[resource]
                if not math.isfinite(cumulative[resource]):
                    _invalid(f"{person.id}: cumulative {resource} use is non-finite")
                remaining = initial[resource] - cumulative[resource]
                ok = remaining >= reserves[resource] - 1e-12
                rows[resource].append({"phase": phase.name, "kind": phase.kind,
                                       "use": use[resource], "cumulative_use": cumulative[resource],
                                       "remaining": remaining, "prefix_ok": ok})
                if not ok and first_breach is None:
                    first_breach = {"resource": resource, "phase": phase.name}
        item["ledgers"] = [
            {"resource": r, "unit": UNITS[r], "initial": initial[r], "reserve": reserves[r],
             "total_use": cumulative[r], "margin": initial[r] - reserves[r] - cumulative[r],
             "utilisation": cumulative[r] / (initial[r] - reserves[r]), "rows": rows[r]}
            for r in RESOURCES
        ]
        item["co2_excess_load_g"] = co2_excess_g
        item["phase_metrics"] = phase_metrics
        item["remaining_resources"] = {r: initial[r] - cumulative[r] for r in RESOURCES}
        if elapsed_s and energy_j / elapsed_s > person.sustainable_metabolic_w:
            item["flags"].append("workload_above_sustainable")
        if co2_excess_g > 0:
            item["flags"].append("co2_production_above_declared_removal")
        if first_breach:
            if first_breach["resource"] == "terrain_slope":
                reason = f"slope limit exceeded during {first_breach['phase']}"
            elif first_breach["resource"] == "metabolic_peak":
                reason = f"mean metabolic power exceeded declared peak during {first_breach['phase']}"
            else:
                reason = f"{first_breach['resource']} reserve breached during {first_breach['phase']}"
            item.update(check="fail", reason=reason,
                        breach=first_breach, risk=None, band="fail", driver=None)
        else:
            driver = max(RESOURCES, key=lambda r: cumulative[r] / (initial[r] - reserves[r]))
            worst = cumulative[driver] / (initial[driver] - reserves[driver])
            item.update(check="pass", reason="all consumable reserves hold", breach=None,
                        risk=round(100 * worst), band=_band(worst, policy), driver=driver)
    failed = next((a for a in payload["astronauts"] if a["check"] == "fail"), None)
    if failed:
        payload["route"] = {"check": "fail", "risk": None, "band": "fail",
                            "limited_by": failed["id"], "breach": failed["breach"]}
    else:
        limiting = min(payload["astronauts"], key=lambda a: (-a["risk"], a["id"]))
        payload["route"] = {"check": "pass", "risk": limiting["risk"],
                            "band": limiting["band"], "limited_by": limiting["id"], "breach": None}
    return payload


def serialize(payload):
    """Round reported rates and utilisation only, leaving calculations unrounded."""
    import copy
    result = copy.deepcopy(payload)
    for person in result["astronauts"]:
        person["rates_flat_per_h"] = {k: float(f"{v:.6g}") for k, v in person["rates_flat_per_h"].items()}
        for ledger in person["ledgers"]:
            ledger["utilisation"] = round(ledger["utilisation"], 4)
    return json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
