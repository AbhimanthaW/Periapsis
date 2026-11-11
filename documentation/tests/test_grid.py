import math

import numpy as np
import pytest

from marsdoc import Grid, normalize
from marsdoc.contracts import MarsCRS


@pytest.mark.parametrize("nside,count", [(64, 49152), (128, 196608), (256, 786432)])
def test_grid_and_exact_cell_area(nside, count):
    grid = Grid(nside)
    assert grid.count == count
    assert grid.identifier(0) == f"HPX{nside}:0"
    assert grid.parse_id(grid.identifier(count - 1)) == count - 1
    assert grid.area_km2 * count == pytest.approx(4 * math.pi * 3389.5**2, rel=1e-15)
    indices = np.linspace(0, count - 1, 1024, dtype=np.int64)
    np.testing.assert_array_equal(grid.indices(grid.centroids(indices)), indices)


def test_stable_hierarchy_and_jezero_control():
    grid = Grid()
    assert grid.cell_at((77.44, 18.45)).id == "HPX128:96848"
    assert grid.parent(96848) == "HPX64:24212"
    assert Grid(64).children(24212) == tuple(f"HPX128:{i}" for i in range(96848, 96852))
    assert Grid(1).parent(0) is None
    with pytest.raises(ValueError):
        Grid(96)
    with pytest.raises(ValueError):
        grid.cell(-1)
    with pytest.raises(ValueError):
        grid.parse_id("HPX64:24212")


def test_normalization_and_poles():
    grid = Grid()
    assert tuple(normalize((-10, 20))) == (350, 20)
    assert tuple(normalize((720, -20))) == (0, -20)
    assert grid.cell_at((360, 4)) == grid.cell_at((0, 4))
    for pole in (-90, 90):
        assert grid.cell_at((235, pole)) == grid.cell_at((-179, pole))
    with pytest.raises(ValueError):
        normalize((0, 90.1))
    with pytest.raises(ValueError):
        normalize((math.nan, 0))


def test_native_latitude_and_longitude_conventions():
    crs = MarsCRS(body="Mars", frame="IAU_MARS", definition="fixture",
                  latitude_type="planetographic", longitude_direction="west", longitude_domain="unsigned",
                  equatorial_radius_m=3_396_190, polar_radius_m=3_376_200)
    lon, lat = normalize((15, 45), crs)
    assert lon == 345
    # Independent arctangent relation on the surface of the declared spheroid.
    assert lat == pytest.approx(math.degrees(math.atan((3_376_200 / 3_396_190)**2)))
    assert tuple(normalize((300, 90), crs)) == (0, 90)
    with pytest.raises(ValueError, match="domain"):
        normalize((-15, 45), crs)
    with pytest.raises(ValueError, match="radii"):
        normalize((15, 45), crs.model_copy(update={"polar_radius_m": None}))
    with pytest.raises(ValueError, match="frame"):
        normalize((15, 45), crs.model_copy(update={"frame": "unknown"}))
