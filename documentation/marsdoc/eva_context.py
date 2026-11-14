"""Scoped historical examples and an opt-in EVA bookkeeping fixture."""
from importlib.resources import files
import json
import math

import numpy as np

DATA = files("marsdoc").joinpath("eva")
CASES = ("synthetic", "jezero-sol36", "gale-rad")
METRICS = {
    "radiation_dose_rate": "mGy/day",
    "temperature": "K",
    "wind_speed": "m/s",
    "atmospheric_pressure": "Pa",
    "energy_consumption": "Wh",
    "oxygen_consumption": "g",
    "water_consumption": "L",
    "co2_accumulation_removal_load": "g",
    "metabolic_expenditure": "kJ",
    "suit_battery_charge": "Wh",
    "suit_cooling_demand": "W",
    "dust_concentration": "mg/m³",
    "solar_illumination": "degrees",
    "terrain_slope": "degrees",
    "surface_traction": "1",
    "regolith_sinkage": "mm",
    "obstacle_density": "count/m²",
    "suit_mobility_resistance": "W",
    "communication_signal_availability": "state",
    "visibility_distance": "m",
    "walking_speed": "m/s",
    "heart_rate": "bpm",
    "core_body_temperature": "°C",
    "spacesuit_internal_pressure": "kPa absolute",
    "suit_oxygen_reserve": "g",
    "suit_cooling_water_reserve": "kg",
    "remaining_eva_duration": "s",
    "communication_latency": "s",
}
LIGHT_SPEED_M_S = 299_792_458
MOLAR_VOLUME_L = 22.414  # dry gas at 0 C and 1 atm
MODEL = "eva-context-v1"


def read_data(name):
    return json.loads(DATA.joinpath(name).read_text(encoding="utf-8"))


def record(metric, value, method, *, status="synthetic_derived", **details):
    return {"value": value, "unit": METRICS[metric], "data_status": status,
            "method": method, **details}


def solar_elevation(lat_deg, declination_deg, hour_angle_deg):
    lat, dec, hour = map(math.radians, (lat_deg, declination_deg, hour_angle_deg))
    vertical = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(hour)
    return math.degrees(math.asin(min(1.0, max(-1.0, vertical))))


def local_radio(s):
    """Straight, evenly-spaced terrain profile. The fixture declines unknown clearance."""
    profile = s["link_terrain_elevations_m"]
    if len(profile) < 3 or any(z is None or not math.isfinite(z) for z in profile):
        return "unknown", None
    distance = s["link_distance_m"]
    wavelength = LIGHT_SPEED_M_S / s["link_frequency_hz"]
    loss = 20 * math.log10(4 * math.pi * distance / wavelength)
    margin = s["link_tx_dbm"] + s["link_gains_dbi"] - s["link_misc_loss_db"] - loss - s["link_receiver_min_dbm"]
    for i, ground in enumerate(profile[1:-1], start=1):
        f = i / (len(profile) - 1)
        ray = (1 - f) * profile[0] + f * profile[-1] + s["link_antenna_height_m"]
        first_fresnel = math.sqrt(wavelength * distance * f * (1 - f))
        if ray - ground < 0.6 * first_fresnel:
            return "clearance_not_demonstrated", margin
    return ("available_in_fixture" if margin >= 0 else "insufficient_fixture_margin"), margin


def fixture_fields(s, elapsed_s):
    """Constant-activity accounting; physiological samples are declared telemetry."""
    if not math.isfinite(elapsed_s) or not 0 <= elapsed_s <= s["mission_clock_s"]:
        raise ValueError("elapsed seconds must be within the fixture mission clock")
    grade = s["signed_grade"]
    speed = s["flat_speed_m_s"] * math.exp(
        -s["pace_grade_decay"] * (abs(grade + s["pace_optimum_downhill_grade"]) - s["pace_optimum_downhill_grade"])
    )
    joint_w = s["suit_joint_torque_nm"] * s["suit_joint_angular_speed_rad_s"]
    uphill_w = s["mass_kg"] * s["mars_gravity_m_s2"] * speed * max(0, grade)
    metabolic_w = s["metabolic_baseline_w"] + (uphill_w + joint_w) / s["mechanical_efficiency"]
    rer = s["respiratory_exchange_ratio"]
    oxygen_l_min = metabolic_w * 60 / (4184 * (3.941 + 1.106 * rer))
    oxygen_g_s = oxygen_l_min * 31.998 / (MOLAR_VOLUME_L * 60)
    co2_g_s = oxygen_l_min * rer * 44.01 / (MOLAR_VOLUME_L * 60)
    cooling_w = max(0.0, metabolic_w - uphill_w + s["net_external_heat_w"])
    water_kg_s = cooling_w / s["cooling_water_heat_j_kg"]
    electrical_w = s["electrical_base_w"] + cooling_w * s["cooling_electrical_w_per_thermal_w"]
    drinking_l_s = s["drinking_water_l_h"] / 3600
    oxygen = s["initial_oxygen_g"] - oxygen_g_s * elapsed_s
    cooling_water = s["initial_cooling_water_kg"] - water_kg_s * elapsed_s
    electricity = s["initial_battery_wh"] - electrical_w * elapsed_s / 3600
    drinking = s["initial_drinking_water_l"] - drinking_l_s * elapsed_s
    cooling_limit = cooling_water / water_kg_s if water_kg_s else math.inf
    limits = {"clock": s["mission_clock_s"] - elapsed_s,
              "battery": electricity * 3600 / electrical_w,
              "oxygen": oxygen / oxygen_g_s,
              "cooling_water": cooling_limit,
              "drinking_water": drinking / drinking_l_s}
    bottleneck = min(limits, key=limits.get)
    extinction = s["dust_mg_m3"] * 1e-6 * s["visible_mass_extinction_m2_kg"]
    contact_pa = s["mass_kg"] * s["mars_gravity_m_s2"] / s["boot_contact_area_m2"]
    radio_state, margin = local_radio(s)
    modelled = {
        "energy_consumption": (electrical_w * elapsed_s / 3600, "constant-electrical-load"),
        "oxygen_consumption": (oxygen_g_s * elapsed_s, "inverse-weir-dry-gas"),
        "water_consumption": (drinking_l_s * elapsed_s, "declared-drinking-rate"),
        "co2_accumulation_removal_load": (co2_g_s * elapsed_s, "inverse-weir-rer"),
        "metabolic_expenditure": (metabolic_w * elapsed_s / 1000, "baseline-plus-mechanical-work"),
        "suit_battery_charge": (max(0.0, electricity), "electrical-ledger"),
        "suit_cooling_demand": (cooling_w, "steady-heat-balance"),
        "solar_illumination": (solar_elevation(s["site_lon_lat"][1], s["synthetic_solar_declination_deg"],
                                                s["synthetic_solar_hour_angle_deg"]), "spherical-solar-elevation"),
        "terrain_slope": (math.degrees(math.atan(abs(grade))), "declared-path-grade"),
        "regolith_sinkage": (10 * (contact_pa / s["soil_pressure_at_1cm_pa"]) ** (1 / s["soil_sinkage_exponent"]),
                            "plate-pressure-power-law"),
        "obstacle_density": (s["obstacle_count"] / s["mapped_area_m2"], "count-per-survey-area"),
        "suit_mobility_resistance": (joint_w, "joint-torque-times-angular-speed"),
        "visibility_distance": (-math.log(s["contrast_threshold"]) / extinction, "homogeneous-contrast-extinction"),
        "walking_speed": (speed, "marswalk-tobler-shape"),
        "suit_oxygen_reserve": (max(0.0, oxygen), "oxygen-ledger"),
        "suit_cooling_water_reserve": (max(0.0, cooling_water), "evaporative-water-ledger"),
        "remaining_eva_duration": (max(0.0, limits[bottleneck]), "minimum-constant-rate-budget"),
        "communication_latency": (s["synthetic_earth_mars_range_km"] * 1000 / LIGHT_SPEED_M_S, "range-over-c"),
    }
    result = {key: record(key, value, method) for key, (value, method) in modelled.items()}
    result["radiation_dose_rate"] = record(
        "radiation_dose_rate", s["synthetic_dose_rate_mgy_day"], "declared-fixture-rate",
        status="synthetic_assumption", fixture_integrated_absorbed_dose_mgy=
        s["synthetic_dose_rate_mgy_day"] * elapsed_s / 86400,
    )
    for key, input_key in {
        "temperature": "synthetic_air_temperature_k",
        "wind_speed": "synthetic_horizontal_wind_m_s", "atmospheric_pressure": "synthetic_pressure_pa",
        "dust_concentration": "dust_mg_m3",
        "surface_traction": "boot_friction_coefficient",
    }.items():
        result[key] = record(key, s[input_key], "declared-fixture-input", status="synthetic_assumption")
    telemetry_t = s["synthetic_telemetry_elapsed_s"]
    for key, input_key in (("heart_rate", "heart_rate_bpm"),
                           ("core_body_temperature", "core_body_temperature_c"),
                           ("spacesuit_internal_pressure", "suit_internal_pressure_kpa_abs")):
        samples = s["synthetic_telemetry"][input_key]
        within = telemetry_t[0] <= elapsed_s <= telemetry_t[-1]
        result[key] = record(key, float(np.interp(elapsed_s, telemetry_t, samples)) if within else None,
                             "linear-fixture-telemetry", status="synthetic_telemetry" if within else "unavailable",
                             limitation="No extrapolation beyond the telemetry interval.")
    result["communication_signal_availability"] = record(
        "communication_signal_availability", radio_state, "clearance-and-free-space-budget", link_margin_db=margin,
    )
    result["co2_accumulation_removal_load"].update(
        removal_capacity_g_s=s["co2_removal_g_s"],
        unremoved_mass_g=max(0.0, co2_g_s - s["co2_removal_g_s"]) * elapsed_s,
    )
    result["remaining_eva_duration"]["limiting_resource"] = bottleneck
    result["obstacle_density"]["minimum_obstacle_height_m"] = s["obstacle_min_height_m"]
    result["visibility_distance"]["extinction_m_inverse"] = extinction
    result["energy_consumption"]["electrical_load_w"] = electrical_w
    result["metabolic_expenditure"]["metabolic_power_w"] = metabolic_w
    result["suit_battery_charge"]["capacity_wh"] = s["battery_capacity_wh"]
    result["water_consumption"]["cooling_water_used_kg"] = water_kg_s * elapsed_s
    return result


def evaluate_eva_context(grid, cell_id, case="synthetic", elapsed_s=None):
    if case not in CASES:
        raise ValueError(f"unknown EVA context case: {case}")
    grid.parse_id(cell_id)
    scenario = read_data("scenario-v1.json")
    elapsed = scenario["elapsed_s"] if elapsed_s is None else elapsed_s
    fields = fixture_fields(scenario, elapsed)
    source = read_data("historical-v1.json")[case] if case != "synthetic" else None
    anchor = source["anchor_lon_lat"] if source else scenario["site_lon_lat"]
    applicable = cell_id == grid.cell_at(anchor).id
    if applicable and source:
        for key, observation in source["fields"].items():
            fields[key] = record(key, **observation)
    if not applicable:
        fields = {key: record(key, None, "outside-case-anchor-cell", status="unavailable") for key in METRICS}
    return {
        "method_version": MODEL, "data_status": "mixed_historical_and_synthetic" if applicable and source else (
            "synthetic" if applicable else "unavailable"),
        "cell_id": cell_id, "case_id": case, "fixture_id": scenario["id"], "fixture_elapsed_s": elapsed,
        "anchor_lon_lat": anchor, "source_scope": source["scope"] if applicable and source else None,
        "fixture_scope": "An independent synthetic EVA, shown alongside the selected historical case.",
        "fields": {key: fields[key] for key in METRICS},
        "limitations": ["Synthetic records are software demonstration inputs.",
                        "Historical records describe their own sensor or model scope and epoch.",
                        "Scenario calculations use the independent synthetic inputs. Documentation and eligibility use the evidence catalogue.",
                        "The fixture clock and budgets exclude return reserves and contingency authority."],
    }
