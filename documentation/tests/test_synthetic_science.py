import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from marsdoc import DocumentationEngine, Package
from marsdoc.contracts import CapabilityQuery
from marsdoc.science_context import (
    MagneticDipole, MappedArea, MappedLine, SpectralTile, dipole_field, mapped_areas, mapped_valley_length,
    olivine_cell, olivine_indices,
)
from marsdoc.spatial import GEOD, Window, surface_parts
from marsdoc.synthetic_science import BASE_SPECTRUM, DEMO_POINT, FIELDS, rectangle, synthetic_scene

ROOT = Path(__file__).resolve().parents[2]


def test_polygon_union_partial_coverage_and_unknown():
    survey, = surface_parts(rectangle(359, -1, 1, 1))
    window = Window.from_geometry(rectangle(358, -1, 1, 1))
    shape = rectangle(359.2, -0.4, 0.1, 0.4)
    a = MappedArea.prepare("one", "fan", shape)
    b = MappedArea.prepare("two", "fan", shape)
    one = mapped_areas(window, (a,), survey)
    two = mapped_areas(window, (a, b), survey)
    assert 0 < two["mapped_fraction"] < two["surveyed_fraction"] < 1
    assert two["mapped_area_km2"] == one["mapped_area_km2"]
    assert two["feature_ids"] == ["one", "two"]
    assert mapped_areas(window, (), survey)["mapped_fraction"] == 0
    assert mapped_areas(Window.from_geometry(rectangle(4, -1, 5, 1)), (), survey) is None


def test_line_union_clips_across_the_seam_in_mars_kilometres():
    survey_geom = rectangle(359, -1, 1, 1)
    survey, = surface_parts(survey_geom)
    window = Window.from_geometry(survey_geom)
    tributary = ((358.5, 0), (1.5, 0))
    a = MappedLine.prepare("one", tributary)
    b = MappedLine.prepare("two", tuple(reversed(tributary)))
    result = mapped_valley_length(window, (a, b), survey)
    assert result["surveyed_fraction"] == 1
    assert result["length_km"] == pytest.approx(GEOD.inv(359, 0, 1, 0)[2] / 1000)
    assert result["feature_ids"] == ["one", "two"]
    assert mapped_valley_length(window, (), survey)["length_km"] == 0


def test_dipole_pole_equator_sign_and_radial_decay():
    source = MagneticDipole((0, 0), 3390, (0, 90), 100 * 3390**3)
    params = dict(reference_radius_km=3390, sources=(source,))
    eq = dipole_field((0, 0), altitude_km=0, **params)
    pole = dipole_field((0, 90), altitude_km=0, **params)
    south = dipole_field((0, -90), altitude_km=0, **params)
    high = dipole_field((0, 90), altitude_km=3390, **params)
    assert eq["magnitude_nt"] == 100
    assert abs(eq["outward_nt"]) < 1e-12
    assert pole["outward_nt"] == 200 and south["outward_nt"] == -200
    assert high["magnitude_nt"] == 25
    np.testing.assert_allclose(eq["mars_fixed_xyz_nt"], [0, 0, -100], atol=1e-12)
    with pytest.raises(ValueError, match="altitude"):
        dipole_field((0, 0), altitude_km=-1, **params)


def test_local_magnetic_sources_add_as_vectors_before_magnitude():
    first = MagneticDipole((0, 0), 20, (0, 0), 30_000)
    second = MagneticDipole((0, 0), 10, (180, 0), 4_000)
    field = dipole_field((0, 0), reference_radius_km=3390, altitude_km=10, sources=(first, second))
    expected = 2 * (30_000 / 30**3 - 4_000 / 20**3)
    assert field["outward_nt"] == pytest.approx(expected)
    assert field["magnitude_nt"] == pytest.approx(expected)



def test_olivine_calibration_bands_and_missingness():
    assert olivine_indices(BASE_SPECTRUM, post_orbit_7768=False) == pytest.approx((1, 1))
    strong = BASE_SPECTRUM | {1360: 0.195, 1030: 0.30, 1490: 0.25}
    assert olivine_indices(strong, post_orbit_7768=False) == pytest.approx(
        (0.24 / (0.3 * 0.24 + 0.7 * 0.195), 0.24 / (0.55 * 0.24 + 0.45 * 0.195)))
    assert olivine_indices(strong, post_orbit_7768=True) == pytest.approx(
        (0.24 / (0.1 * 0.30 + 0.2 * 0.24 + 0.7 * 0.195),
         0.24 / (0.05 * 0.30 + 0.05 * 0.24 + 0.45 * 0.195 + 0.45 * 0.25)))
    assert olivine_indices(BASE_SPECTRUM, post_orbit_7768=True) is None
    assert olivine_indices(BASE_SPECTRUM | {1360: float("nan")}, post_orbit_7768=False) is None


def test_olivine_area_weights_detection_and_rejects_overlap():
    window = Window.from_geometry(rectangle(358, -1, 3, 1))
    a, = surface_parts(rectangle(359, -0.5, 0, 0.5))
    b, = surface_parts(rectangle(0.25, -0.5, 1.25, 0.5))
    c, = surface_parts(rectangle(1.5, -0.5, 2.5, 0.5))
    positive = SpectralTile(a, (1.05, 1.0))
    threshold = SpectralTile(b, (1.04, 1.0))
    invalid = SpectralTile(c, None)
    result = olivine_cell(window, (positive, threshold, invalid))
    assert 0 < result["candidate_fraction_of_cell"] < result["valid_spectral_fraction"] < 1
    assert result["candidate_fraction_of_valid_spectra"] == pytest.approx(0.5)
    assert result["mean_osp1"] == pytest.approx(1.045)
    assert olivine_cell(window, (invalid,)) is None
    with pytest.raises(ValueError, match="overlap"):
        olivine_cell(window, (positive, positive))


def test_fixture_cannot_change_documentation_or_calculation_support():
    package = Package(schema_version=1, package_id="empty-control", version="1",
                      datasets=(), products=(), footprints=())
    engine = DocumentationEngine(package)
    cell_id = engine.grid.cell_at(DEMO_POINT).id
    baseline = engine.summarize(cell_id)
    request = CapabilityQuery.model_validate({
        "schema_version": 1, "geometry": {"type": "Point", "coordinates": DEMO_POINT},
        "requested": {"id": "map-olivine", "requirements": [{
            "variable": "olivine", "product_classes": ["spectral_index"],
        }]},
    })
    decision = engine.resolve(request)
    rows = list(synthetic_scene(engine))
    assert len(rows) == 28
    for key, (_, metric) in FIELDS.items():
        assert any(row["fields"][key] and row["fields"][key][metric] > 0 for row in rows)
    first = engine.synthetic_context(cell_id)
    assert first == engine.synthetic_context(cell_id)
    assert first["data_status"] == "synthetic"
    assert first["fields"]["deltas"]["feature_ids"] == ["synthetic-delta-01"]
    outside = engine.synthetic_context(engine.grid.cell_at((77.44, 18.45)).id)
    assert all(value is None for value in outside["fields"].values())
    assert baseline == engine.summarize(cell_id)
    assert not engine.resolve(request).requested.eligible
    assert decision == engine.resolve(request)
    assert not baseline.provenance


def test_cli_opt_in_preserves_source_backed_summary():
    command = [sys.executable, "-m", "marsdoc", str(ROOT / "evidence/jezero/jezero-evidence.json"),
               "--point", str(DEMO_POINT[0]), str(DEMO_POINT[1])]
    baseline = json.loads(subprocess.check_output(command))
    demo = json.loads(subprocess.check_output([*command, "--synthetic-context"]))
    assert demo["documentation"] == baseline
    assert demo["synthetic_science_context"]["cell_id"] == baseline["cell"]["id"]
    assert demo["synthetic_science_context"]["fields"]["crustal_magnetism"]["magnitude_nt"] > 0
