"""Read Mars Dust Activity Database (MDAD) v1.1 storm masks.

Source: Battalio et al., MDAD v1.1, Zenodo, DOI 10.5281/zenodo.7480334 (MRO MARCI era, MY 28-32).
Each Mars-year NetCDF file holds an ``MDAD`` uint8 mask on a 0.1 degree grid with these values:

* 0        valid pixel, no mapped dust storm
* 1-133    dust storm member ID (MDAD v1.0)
* 134-250  splitting storm member (member ID = value - 133)
* 255      missing pixel in the Mars Daily Global Map

The record page does not state the mask's longitude direction, longitude origin or latitude order.
This module therefore never assumes them. ``calibrate_convention`` scores every candidate convention
against the storm-outline CSV files shipped in the same bundle (east longitude, latitude) and accepts
a convention only when it clearly wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from ..errors import PipelineError

MISSING = 255
STORM_MIN, STORM_MAX = 1, 250
SPLIT_OFFSET = 133
DOI = "10.5281/zenodo.7480334"
DATASET_VERSION = "MDAD v1.1"
YEAR_PATTERN = re.compile(r"MY\s*_?(\d{2})", re.IGNORECASE)
CSV_PATTERN = re.compile(r"(?P<sub>[A-Za-z0-9]+)_day(?P<day>\d+)_MEM_(?P<mem>\d+)(?P<split>b?)\.csv$", re.IGNORECASE)


class DustDataError(PipelineError):
    """The MDAD input does not match the documented layout."""


def storm_mask(values: np.ndarray) -> np.ndarray:
    return (values >= STORM_MIN) & (values <= STORM_MAX)


def valid_mask(values: np.ndarray) -> np.ndarray:
    return values != MISSING


@dataclass(frozen=True)
class GridConvention:
    """How mask indices map to planetocentric latitude and east longitude (node-registered grid)."""

    name: str
    lon_direction: str  # "east" or "west": positive direction of increasing longitude index
    lon_origin_deg: float  # longitude of index 0, measured in lon_direction
    lat_ascending: bool  # True when index 0 is -90 degrees

    def lon_index(self, lon_east: np.ndarray, nlon: int) -> np.ndarray:
        step = 360.0 / nlon
        value = np.asarray(lon_east, dtype=float) if self.lon_direction == "east" else -np.asarray(lon_east, dtype=float)
        return (np.rint(((value - self.lon_origin_deg) % 360.0) / step).astype(np.int64)) % nlon

    def lat_index(self, lat: np.ndarray, nlat: int) -> np.ndarray:
        step = 180.0 / (nlat - 1)
        lat = np.asarray(lat, dtype=float)
        index = np.rint(((lat + 90.0) if self.lat_ascending else (90.0 - lat)) / step).astype(np.int64)
        return np.clip(index, 0, nlat - 1)

    def lon_east_of_index(self, nlon: int) -> np.ndarray:
        value = self.lon_origin_deg + np.arange(nlon) * (360.0 / nlon)
        east = value if self.lon_direction == "east" else -value
        return (east + 180.0) % 360.0 - 180.0

    def lat_of_index(self, nlat: int) -> np.ndarray:
        step = 180.0 / (nlat - 1)
        return -90.0 + np.arange(nlat) * step if self.lat_ascending else 90.0 - np.arange(nlat) * step

    def as_dict(self) -> dict:
        return {"name": self.name, "lon_direction": self.lon_direction, "lon_origin_deg": self.lon_origin_deg,
                "lat_ascending": self.lat_ascending, "registration": "node"}


CANDIDATES = tuple(
    GridConvention(f"{direction}{origin:+.0f}_{'south_up' if ascending else 'north_down'}", direction, origin, ascending)
    for direction, origin in (("east", 0.0), ("east", -180.0), ("west", 0.0))
    for ascending in (True, False)
)


def convention_by_name(name: str) -> GridConvention:
    for candidate in CANDIDATES:
        if candidate.name == name:
            return candidate
    raise DustDataError(f"Unknown grid convention {name!r}; choose one of {[c.name for c in CANDIDATES]}")


def year_of(path: Path) -> int:
    for part in reversed(path.parts):
        match = YEAR_PATTERN.search(part)
        if match:
            return int(match.group(1))
    raise DustDataError(f"Cannot find a Mars year (MYxx) in {path}")


def _decode_names(raw) -> list[str]:
    array = np.asarray(raw)
    if array.dtype.kind in ("S", "U") and array.ndim == 2 and array.dtype.itemsize == 1:
        return ["".join(c.decode() if isinstance(c, bytes) else c for c in row).strip("\x00 ") for row in array]
    if array.dtype.kind == "S":
        return [value.decode(errors="replace").strip("\x00 ") for value in array.ravel()]
    return [str(value).strip("\x00 ") for value in array.ravel()]


class MaskYear:
    """One MDAD Mars-year NetCDF file. ``read`` returns uint8 blocks ordered (time, lon, lat)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.year = year_of(self.path)
        self._close = None
        try:
            import netCDF4  # type: ignore

            dataset = netCDF4.Dataset(str(self.path))
            dataset.set_auto_mask(False)
            dataset.set_auto_scale(False)
            self._close = dataset.close
            variables = dataset.variables
        except ImportError:
            try:
                from scipy.io import netcdf_file
            except ImportError as error:  # pragma: no cover - environment guard
                raise DustDataError("Install netCDF4 (pip install netCDF4) to read MDAD files") from error
            try:
                dataset = netcdf_file(str(self.path), "r", mmap=False)
            except (TypeError, ValueError) as error:
                raise DustDataError(f"{self.path.name} is not NetCDF3; install netCDF4 to read NetCDF4/HDF5 files") from error
            self._close = dataset.close
            variables = dataset.variables
        except OSError as error:
            raise DustDataError(f"Cannot open {self.path}: {error}") from error
        for name in ("MDAD", "timeList"):
            if name not in variables:
                raise DustDataError(f"{self.path.name} has no {name!r} variable; found {sorted(variables)}")
        self._mask = variables["MDAD"]
        shape = tuple(int(n) for n in self._mask.shape)
        if len(shape) != 3:
            raise DustDataError(f"MDAD must be 3-D, got shape {shape}")
        self.time_axis, self.lon_axis, self.lat_axis = self._axes(shape)
        self.ntime, self.nlon, self.nlat = shape[self.time_axis], shape[self.lon_axis], shape[self.lat_axis]
        times = np.asarray(variables["timeList"][:], dtype=float)
        if times.ndim != 2 or 8 not in times.shape:
            raise DustDataError(f"timeList must be 2-D with 8 fields, got {times.shape}")
        if times.shape[0] == 8 and times.shape[1] == self.ntime:
            times = times.T
        if times.shape != (self.ntime, 8):
            raise DustDataError(f"timeList shape {times.shape} does not match {self.ntime} mask records")
        self.times = times  # start soy, end soy, mean soy, median soy, start Ls, end Ls, mean Ls, median Ls
        self.day_names = _decode_names(variables["dayList"][:]) if "dayList" in variables else [""] * self.ntime

    @staticmethod
    def _axes(shape: tuple[int, int, int]) -> tuple[int, int, int]:
        for lon_axis in range(3):
            for lat_axis in range(3):
                if lon_axis != lat_axis and shape[lon_axis] == 2 * (shape[lat_axis] - 1):
                    time_axis = 3 - lon_axis - lat_axis
                    return time_axis, lon_axis, lat_axis
        raise DustDataError(f"Cannot identify lon (2*(nlat-1)) and lat axes in MDAD shape {shape}")

    @property
    def mean_soy(self) -> np.ndarray:
        return self.times[:, 2]

    @property
    def mean_ls(self) -> np.ndarray:
        return self.times[:, 6]

    def read(self, start: int, stop: int) -> np.ndarray:
        index = [slice(None)] * 3
        index[self.time_axis] = slice(start, stop)
        block = np.asarray(self._mask[tuple(index)], dtype=np.uint8)
        return np.ascontiguousarray(np.moveaxis(block, (self.time_axis, self.lon_axis, self.lat_axis), (0, 1, 2)))

    def header(self) -> dict:
        return {"file": self.path.name, "mars_year": self.year, "records": self.ntime, "nlon": self.nlon,
                "nlat": self.nlat,
                "axis_order": [name for _, name in sorted(((self.time_axis, "time"), (self.lon_axis, "lon"),
                                                           (self.lat_axis, "lat")))],
                "soy_range": [float(np.nanmin(self.mean_soy)), float(np.nanmax(self.mean_soy))],
                "ls_range": [float(np.nanmin(self.mean_ls)), float(np.nanmax(self.mean_ls))],
                "day_name_examples": self.day_names[:3]}

    def close(self) -> None:
        if self._close:
            self._close()
            self._close = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _read_outline(path: Path) -> np.ndarray:
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        parts = re.split(r"[,\s]+", line.strip())
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue
    return np.asarray(rows, dtype=float).reshape(-1, 2)


def calibrate_convention(year: MaskYear, csv_files: list[Path], *, max_outlines: int = 150,
                         min_score: float = 0.7, min_margin: float = 0.2) -> dict:
    """Pick the grid convention whose pixels carry the outline's member ID next to its boundary points."""
    lookup: dict[str, int] = {}
    for index, name in enumerate(year.day_names):
        lookup.setdefault(_normalise(name), index)
    matched: dict[int, list[tuple[np.ndarray, int]]] = {}
    unmatched = 0
    for path in sorted(csv_files):
        found = CSV_PATTERN.search(path.name)
        if not found:
            continue
        key = _normalise(f"{found['sub']}_day{int(found['day']):02d}")
        index = lookup.get(key)
        if index is None:
            index = next((i for name, i in lookup.items() if key in name), None)
        if index is None:
            unmatched += 1
            continue
        member = int(found["mem"]) + (SPLIT_OFFSET if found["split"] else 0)
        outline = _read_outline(path)
        if len(outline):
            matched.setdefault(index, []).append((outline, member))
    outlines = [(t, o, m) for t, items in sorted(matched.items()) for o, m in items]
    if not outlines:
        raise DustDataError(
            f"No outline CSV in MY{year.year} matched a dayList entry ({unmatched} unmatched). "
            f"Example day names: {year.day_names[:3]}. Pass --convention after checking MDAD_read_masks.ipynb.")
    stride = max(1, len(outlines) // max_outlines)
    outlines = outlines[::stride][:max_outlines]
    hits = {candidate.name: 0 for candidate in CANDIDATES}
    total = 0
    for t in sorted({t for t, _, _ in outlines}):
        frame = year.read(t, t + 1)[0]
        for _, outline, member in (item for item in outlines if item[0] == t):
            total += len(outline)
            for candidate in CANDIDATES:
                li = candidate.lon_index(outline[:, 0], year.nlon)
                ai = candidate.lat_index(outline[:, 1], year.nlat)
                near = np.zeros(len(outline), dtype=bool)
                for dl in (-1, 0, 1):
                    for da in (-1, 0, 1):
                        near |= frame[(li + dl) % year.nlon, np.clip(ai + da, 0, year.nlat - 1)] == member
                hits[candidate.name] += int(near.sum())
    scores = {name: hits[name] / total for name in hits}
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    (best, best_score), (_, second) = ranked[0], ranked[1]
    accepted = best_score >= min_score and best_score - second >= min_margin
    return {"mars_year": year.year, "outlines": len(outlines), "points": total, "scores": scores,
            "best": best, "accepted": accepted, "min_score": min_score, "min_margin": min_margin}
