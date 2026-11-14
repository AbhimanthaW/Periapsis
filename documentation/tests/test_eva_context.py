"""Physics controls and documentation isolation for the opt-in EVA cases."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from marsdoc import CapabilityQuery, DocumentationEngine, Package
from marsdoc.eva_context import METRICS, fixture_fields, local_radio, read_data, solar_elevation
from runtime.marswalk.mobility import ToblerScaled
from runtime.marswalk.traversability import horn_slope_deg

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "evidence/jezero/jezero-evidence.json"


@pytest.fixture
def engine():
    return DocumentationEngine(Package.model_validate_json(PACKAGE.read_bytes()))


def test_fixture_has_28_finite_values_and_conserves_consumables(engine):
    settings = read_data("scenario-v1.json")
    cell = engine.grid.cell_at(settings["site_lon_lat"]).id
    start = engine.eva_context(cell, elapsed_s=0)["fields"]
    demo = engine.eva_context(cell, elapsed_s=1200)["fields"]
    assert set(demo) == METRICS.keys() and len(demo) == 28
    assert all(entry["value"] is not None and entry["data_status"].startswith("synthetic") for entry in demo.values())
    json.dumps(demo, allow_nan=False)
    assert demo["energy_consumption"]["value"] + demo["suit_battery_charge"]["value"] == pytest.approx(
        start["suit_battery_charge"]["value"])
    assert demo["oxygen_consumption"]["value"] + demo["suit_oxygen_reserve"]["value"] == pytest.approx(
        start["suit_oxygen_reserve"]["value"])
    assert demo["water_consumption"]["cooling_water_used_kg"] + demo["suit_cooling_water_reserve"]["value"] == pytest.approx(
        start["suit_cooling_water_reserve"]["value"])
    assert demo["radiation_dose_rate"]["fixture_integrated_absorbed_dose_mgy"] == pytest.approx(0.25 / 72)
    pace = ToblerScaled()
    assert demo["walking_speed"]["value"] == pytest.approx(1 / pace.seconds(1, settings["signed_grade"]))


def test_budget_exhaustion_and_telemetry_no_extrapolation():
    settings = read_data("scenario-v1.json")
    values = fixture_fields(settings, settings["mission_clock_s"])
    assert values["remaining_eva_duration"]["value"] == 0
    assert values["suit_cooling_water_reserve"]["value"] >= 0
    assert values["heart_rate"]["value"] is None
    assert values["core_body_temperature"]["data_status"] == "unavailable"
    assert values["spacesuit_internal_pressure"]["value"] is None
    with pytest.raises(ValueError, match="within"):
        fixture_fields(settings, float("nan"))
    assert fixture_fields(settings | {"co2_removal_g_s": 0}, 1200)[
        "co2_accumulation_removal_load"]["unremoved_mass_g"] > 0


def test_geometric_and_radio_controls():
    assert solar_elevation(0, 0, 0) == 90
    assert solar_elevation(0, 0, 180) == -90
    settings = read_data("scenario-v1.json")
    assert local_radio(settings | {"link_terrain_elevations_m": [0, None, 0]}) == ("unknown", None)
    assert local_radio(settings | {"link_terrain_elevations_m": [0, 12, 0]})[0] == "clearance_not_demonstrated"
    clear = settings | {"link_antenna_height_m": 20}
    assert local_radio(clear)[0] == "available_in_fixture"
    assert local_radio(clear | {"link_tx_dbm": 0, "link_receiver_min_dbm": -60})[0] == "insufficient_fixture_margin"


def test_historical_jezero_values_replace_only_scoped_fields(engine):
    site = engine.grid.cell_at((77.45, 18.44)).id
    prior = engine.summarize(site)
    query = CapabilityQuery.model_validate_json(PACKAGE.with_name("jezero-route.json").read_bytes())
    initial_eligibility = engine.resolve(query)
    result = engine.eva_context(site, case="jezero-sol36")
    assert result["data_status"] == "mixed_historical_and_synthetic"
    fields = result["fields"]
    assert len(fields) == 28
    for key, value in {"temperature": 238.71, "wind_speed": 9.08, "atmospheric_pressure": 737.47}.items():
        assert fields[key]["value"] == value and fields[key]["data_status"] == "historical_measurement"
        assert fields[key]["sclk"] == "670144481"
    assert fields["solar_illumination"]["value"] == 55.49
    assert fields["communication_latency"]["value"] == pytest.approx(14.32169718 * 60)
    slope = fields["terrain_slope"]
    kernel = np.array(slope["elevation_kernel_m"])
    assert slope["value"] == horn_slope_deg(kernel, np.isfinite(kernel), 20, 20)[1, 1]
    assert slope["value"] == pytest.approx(2.76918, abs=1e-5)
    assert fields["walking_speed"] == engine.eva_context(site)["fields"]["walking_speed"]
    assert fields["radiation_dose_rate"]["data_status"] == "synthetic_assumption"
    assert engine.summarize(site) == prior
    assert engine.resolve(query) == initial_eligibility
    gale = engine.grid.cell_at((137.4417, -4.5895)).id
    rad = engine.eva_context(gale, case="gale-rad")["fields"]["radiation_dose_rate"]
    assert rad["value"] == 0.21 and rad["data_status"] == "historical_summary"
    assert rad["reported_plus_minus_mgy_day"] == 0.04
    assert "fixture_integrated_absorbed_dose_mgy" not in rad
    for wrong_cell, case in ((gale, "jezero-sol36"), (site, "gale-rad")):
        outside = engine.eva_context(wrong_cell, case=case)
        assert all(entry["value"] is None for entry in outside["fields"].values())


def test_cli_preserves_default_shape_and_supports_both_contexts():
    command = [sys.executable, "-m", "marsdoc", str(PACKAGE), "--point", "77.45", "18.44"]
    original = json.loads(subprocess.check_output(command))
    extended = json.loads(subprocess.check_output([*command, "--synthetic-context", "--eva-context", "jezero-sol36"]))
    assert extended["documentation"] == original
    assert extended["eva_context"]["fields"]["temperature"]["value"] == 238.71
    assert extended["synthetic_science_context"]["data_status"] == "synthetic"
    query = [sys.executable, "-m", "marsdoc", str(PACKAGE), "--query", str(PACKAGE.with_name("jezero-route.json"))]
    denied = subprocess.run([*query, "--eva-context", "synthetic"], capture_output=True, text=True, check=False)
    assert denied.returncode == 2
    assert "requires --cell or --point" in denied.stderr
