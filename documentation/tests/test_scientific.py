"""Numerical controls with analytic geometry and independent refinements."""
import math

import pytest

from marsdoc import DocumentationEngine, Grid
from marsdoc.contracts import Polygon
from marsdoc.engine import default_policy
from marsdoc.grid import RADIUS_M
from marsdoc.spatial import Window
from conftest import box, dataset, footprint, inventory, package, product
from test_engine import query, stereo


def test_spherical_polar_triangle_area_analytic():
    # Two meridians at 90° meet at the pole. Equal 10° sides from the pole.
    angle = math.radians(10)
    # L'Huilier's formula with sides a=b=10°, c=acos(cos(a)cos(b)).
    c = math.acos(math.cos(angle)**2)
    half = (2 * angle + c) / 2
    tangent_product = math.tan(half / 2) * math.tan((half - angle) / 2)**2 * math.tan((half - c) / 2)
    expected = 4 * math.atan(math.sqrt(tangent_product)) * RADIUS_M**2
    triangle = Polygon(type="Polygon", coordinates=(((0, 90), (0, 80), (90, 80), (0, 90)),))
    assert Window.from_geometry(triangle).size == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("nside", [64, 128])
@pytest.mark.parametrize("location", [(0, 0), (180, 42), (77.44, 18.45), (359.98, 87.4), (0, 90), (0, -90)])
def test_boundary_refinement_for_area_and_intersection(nside, location):
    grid = Grid(nside)
    cell = grid.cell_at(location)
    lon, lat = cell.centroid
    # Through the middle of the cell, including polar/seam cells.
    footprint_box = box(lon - 2, lat - .4, lon + .02, min(90, lat + .4))
    data = package((dataset(),), (product(),), (footprint(shape=footprint_box),), (inventory(),))
    policy = default_policy()
    default = DocumentationEngine(data, nside=nside, policy=policy).summarize(cell.id)
    fine_policy = policy.model_copy(update={"boundary_step": 256, "version": "boundary-control"})
    fine = DocumentationEngine(data, nside=nside, policy=fine_policy).summarize(cell.id)
    assert abs(default.boundary_area_relative_error) < 5e-4
    assert abs(fine.boundary_area_relative_error) < 3e-6
    assert abs(stereo(default).usable_fraction - stereo(fine).usable_fraction) < 5e-4


def test_overlapping_oblique_route_intervals_do_not_inflate_length():
    geometry = {"type": "LineString", "coordinates": [[-.7, -.63], [.7, .81]]}
    first = footprint(shape=box(-1, -1, -.15, 1))
    second = footprint("b", box(-.8, -.8, -.15, 1))
    original = DocumentationEngine(package((dataset(),), (product(),), (first,)))
    duplicated = DocumentationEngine(package((dataset(),), (product(), product("b")), (first, second)))
    a = original.resolve(query(geometry)).requested.variables[0].qualified_fraction
    b = duplicated.resolve(query(geometry)).requested.variables[0].qualified_fraction
    assert 0 < a < .5
    assert b == pytest.approx(a, abs=1e-10)


def test_polar_triangle_partial_coverage_has_exact_half_by_symmetry():
    apex = (0, 90)
    middle_lat = math.degrees(math.atan2(math.sqrt(2) * math.sin(math.radians(80)),
                                        math.cos(math.radians(80))))
    full = Polygon(type="Polygon", coordinates=((apex, (0, 80), (90, 80), apex),))
    half = Polygon(type="Polygon", coordinates=((apex, (0, 80), (45, middle_lat), apex),))
    e = DocumentationEngine(package((dataset(),), (product(),), (footprint(shape=half),)))
    result = e.resolve(query(full.model_dump())).requested
    assert result.variables[0].qualified_fraction == pytest.approx(.5, abs=1e-12)
    assert not result.eligible
