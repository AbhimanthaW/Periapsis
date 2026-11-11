"""Mars geographic coordinates and spherical NESTED HEALPix."""
import math
import re

from astropy import units as u
from astropy_healpix import HEALPix
import numpy as np

from .contracts import Cell, FRAME, MarsCRS, Position

RADIUS_M = 3_389_500.0
CANONICAL = MarsCRS(
    body="Mars", frame=FRAME, definition="Return Window Mars planetocentric/east degrees",
    latitude_type="planetocentric", longitude_direction="east",
)


def normalize(positions, crs: MarsCRS = CANONICAL) -> np.ndarray:
    """Normalize a position or (..., 2) array into canonical lon/lat degrees."""
    if crs.frame != FRAME or not crs.latitude_type or not crs.longitude_direction:
        raise ValueError("unresolved Mars geographic frame, latitude type or longitude direction")
    data = np.asarray(positions, dtype=np.float64)
    if data.ndim < 1 or data.shape[-1] != 2 or not np.isfinite(data).all():
        raise ValueError("expected finite longitude/latitude pairs")
    lon, lat = data[..., 0], data[..., 1]
    if np.any(np.abs(lat) > 90):
        raise ValueError("latitude outside [-90, 90]")
    if crs.longitude_domain == "signed" and np.any(np.abs(lon) > 180):
        raise ValueError("longitude outside declared signed domain")
    if crs.longitude_domain == "unsigned" and np.any((lon < 0) | (lon > 360)):
        raise ValueError("longitude outside declared unsigned domain")
    lon = np.remainder(lon if crs.longitude_direction == "east" else -lon, 360)
    lon = np.where((lon == 360) | (np.abs(lat) == 90), 0, lon)
    if crs.latitude_type == "planetographic":
        a, b = crs.equatorial_radius_m, crs.polar_radius_m
        if a is None or b is None or b > a:
            raise ValueError("planetographic latitude requires declared oblate Mars radii")
        angle = np.deg2rad(lat)
        lat = np.rad2deg(np.arctan2((b / a) ** 2 * np.sin(angle), np.cos(angle)))
    return np.stack((lon, lat), axis=-1)


class Grid:
    def __init__(self, nside: int = 128):
        if isinstance(nside, bool) or not isinstance(nside, int) or not 1 <= nside <= 2**29 or nside & (nside - 1):
            raise ValueError("Nside must be a positive power of two, at most 2**29")
        self.nside = nside
        self.healpix = HEALPix(nside=nside, order="nested")
        self.count = 12 * nside**2
        self.area_km2 = 4 * math.pi * (RADIUS_M / 1000)**2 / self.count

    def indices(self, positions, crs: MarsCRS = CANONICAL) -> np.ndarray:
        coords = normalize(positions, crs)
        return self.healpix.lonlat_to_healpix(coords[..., 0] * u.deg, coords[..., 1] * u.deg)

    def cell_at(self, position: Position, crs: MarsCRS = CANONICAL) -> Cell:
        return self.cell(int(self.indices(position, crs)))

    def identifier(self, index: int) -> str:
        self._check(index)
        return f"HPX{self.nside}:{index}"

    def parse_id(self, identifier: str) -> int:
        match = re.fullmatch(r"HPX([1-9][0-9]*):(0|[1-9][0-9]*)", identifier)
        if not match or int(match[1]) != self.nside:
            raise ValueError("cell ID does not match the grid")
        index = int(match[2])
        self._check(index)
        return index

    def cell(self, index: int) -> Cell:
        lon, lat = self.centroids(index)
        return Cell(id=self.identifier(index), nside=self.nside, nested_index=index,
                    centroid=(float(lon), float(lat)), area_km2=self.area_km2)

    def centroids(self, indices) -> np.ndarray:
        self._check(indices)
        lon, lat = self.healpix.healpix_to_lonlat(indices)
        return normalize(np.stack((lon.to_value(u.deg), lat.to_value(u.deg)), axis=-1))

    def boundaries(self, indices, step: int = 16) -> np.ndarray:
        """Sample 4*step true boundary points per cell, without closing the ring."""
        self._check(indices)
        if isinstance(step, bool) or not isinstance(step, int) or step < 1:
            raise ValueError("boundary step must be a positive integer")
        lon, lat = self.healpix.boundaries_lonlat(indices, step=step)
        return normalize(np.stack((lon.to_value(u.deg), lat.to_value(u.deg)), axis=-1))

    def parent(self, index: int) -> str | None:
        self._check(index)
        return f"HPX{self.nside // 2}:{index // 4}" if self.nside > 1 else None

    def children(self, index: int) -> tuple[str, ...]:
        self._check(index)
        if self.nside == 2**29:
            raise ValueError("children exceed the supported Nside")
        return tuple(f"HPX{self.nside * 2}:{index * 4 + child}" for child in range(4))

    def _check(self, indices) -> None:
        values = np.asarray(indices)
        if values.dtype.kind not in "iu" or np.any((values < 0) | (values >= self.count)):
            raise ValueError("nested index out of range or not an integer")
