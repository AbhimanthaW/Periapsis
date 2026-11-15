"""Extract per-region, per-sol dust-storm coverage from MDAD masks.

For every region the extractor builds two footprints on the mask grid:

* core: pixels within ``core_radius_km`` of the region point (great-circle distance)
* ring: pixels between ``core_radius_km`` and ``ring_radius_km`` (storms approaching the region)

For each Mars sol it records how many footprint pixels were valid (not 255) and how many carried a
storm value (1-250). Records sharing a sol are combined as pixel unions, so a
pixel observed or flagged in any record counts once in that sol. Output is a compact NPZ plus a JSON manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .mdad import DATASET_VERSION, DOI, DustDataError, GridConvention, MaskYear, storm_mask, valid_mask, year_of

MARS_RADIUS_KM = 3389.5
SERIES_FIELDS = ("core_valid", "core_storm", "ring_valid", "ring_storm")


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    lon_east: float
    lat: float


def load_regions(path: Path) -> tuple[list[Region], str]:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    entries = data["regions"] if isinstance(data, dict) else data
    regions = []
    for entry in entries:
        lon, lat = entry["geography"]["center"]
        if not (-90 <= lat <= 90):
            raise DustDataError(f"Region {entry['id']} latitude {lat} is out of range")
        regions.append(Region(str(entry["id"]), entry["name"], (float(lon) + 180.0) % 360.0 - 180.0, float(lat)))
    ids = [region.id for region in regions]
    if len(set(ids)) != len(ids):
        raise DustDataError("Region IDs must be unique")
    return regions, hashlib.sha256(raw).hexdigest()


def great_circle_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * MARS_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def footprints(region: Region, convention: GridConvention, nlon: int, nlat: int,
               core_km: float, ring_km: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    if not 0 < core_km < ring_km:
        raise DustDataError("Radii must satisfy 0 < core < ring")
    lats = convention.lat_of_index(nlat)
    band_deg = np.degrees(ring_km / MARS_RADIUS_KM) + 180.0 / (nlat - 1)
    rows = np.nonzero(np.abs(lats - region.lat) <= band_deg)[0]
    lons = convention.lon_east_of_index(nlon)
    lon_grid, row_grid = np.meshgrid(np.arange(nlon), rows, indexing="ij")
    distance = great_circle_km(region.lon_east, region.lat, lons[lon_grid], lats[row_grid])
    core = distance <= core_km
    ring = (distance > core_km) & (distance <= ring_km)
    result = {"core": (lon_grid[core], row_grid[core]), "ring": (lon_grid[ring], row_grid[ring])}
    if len(result["core"][0]) == 0:
        raise DustDataError(f"Region {region.id} core footprint is empty; increase core radius")
    return result


def extract_year(year: MaskYear, regions: list[Region], convention: GridConvention, *, core_km: float,
                 ring_km: float, chunk: int = 16) -> dict:
    prints = [footprints(r, convention, year.nlon, year.nlat, core_km, ring_km) for r in regions]
    counts = np.zeros((year.ntime, len(regions), 4), dtype=np.int32)
    for start in range(0, year.ntime, chunk):
        block = year.read(start, min(start + chunk, year.ntime))
        for r, footprint in enumerate(prints):
            for k, part in enumerate(("core", "ring")):
                values = block[:, footprint[part][0], footprint[part][1]]
                counts[start:start + len(block), r, 2 * k] = valid_mask(values).sum(axis=1)
                counts[start:start + len(block), r, 2 * k + 1] = storm_mask(values).sum(axis=1)
    soy = year.mean_soy
    usable = np.isfinite(soy) & np.isfinite(year.mean_ls)
    sols = np.rint(soy[usable]).astype(np.int32)
    unique = np.unique(sols)
    merged = np.zeros((len(unique), len(regions), 4), dtype=np.int32)
    position = np.searchsorted(unique, sols)
    np.maximum.at(merged, position, counts[usable])
    source_rows = np.flatnonzero(usable)
    for sol_index in np.flatnonzero(np.bincount(position, minlength=len(unique)) > 1):
        rows = source_rows[position == sol_index]
        valid = np.zeros((year.nlon, year.nlat), dtype=bool)
        storm = np.zeros_like(valid)
        for row in rows:
            values = year.read(int(row), int(row) + 1)[0]
            valid |= valid_mask(values)
            storm |= storm_mask(values)
        for r, footprint in enumerate(prints):
            for k, part in enumerate(("core", "ring")):
                pixels = footprint[part]
                merged[sol_index, r, 2 * k] = valid[pixels].sum()
                merged[sol_index, r, 2 * k + 1] = storm[pixels].sum()
    angles = np.radians(year.mean_ls[usable])
    ls = (np.degrees(np.arctan2(np.bincount(position, np.sin(angles)), np.bincount(position, np.cos(angles)))) + 360) % 360
    return {"sol": unique, "ls": ls, "counts": merged, "records": int(year.ntime), "duplicate_sols": int(len(sols) - len(unique)),
            "core_total": np.array([len(p["core"][0]) for p in prints], dtype=np.int32),
            "ring_total": np.array([len(p["ring"][0]) for p in prints], dtype=np.int32)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_series(output: Path, regions: list[Region], regions_sha: str, years: dict[int, dict],
                 convention: GridConvention, calibration: list[dict], inputs: list[Path], *,
                 core_km: float, ring_km: float) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    first = next(iter(years.values()))
    arrays = {"region_ids": np.array([r.id for r in regions]), "core_total": first["core_total"],
              "ring_total": first["ring_total"]}
    for my, result in sorted(years.items()):
        if not (np.array_equal(result["core_total"], first["core_total"]) and np.array_equal(result["ring_total"], first["ring_total"])):
            raise DustDataError("Footprints differ between years; grids must match")
        arrays[f"my{my}_sol"] = result["sol"]
        arrays[f"my{my}_ls"] = result["ls"]
        arrays[f"my{my}_counts"] = result["counts"]
    series = output / "dust-series.npz"
    np.savez_compressed(series, **arrays)
    manifest = {
        "schema_version": 1, "kind": "mdad_region_series",
        "source": {"doi": DOI, "dataset_version": DATASET_VERSION,
                   "files": [{"name": p.name, "mars_year": y, "sha256": sha256_file(p)} for p, y in
                             sorted(((p, year_of(p)) for p in inputs), key=lambda item: item[1])]},
        "regions": {"count": len(regions), "catalog_sha256": regions_sha},
        "grid": {"convention": convention.as_dict(), "calibration": calibration},
        "method": {"core_radius_km": core_km, "ring_radius_km": ring_km, "mars_radius_km": MARS_RADIUS_KM,
                   "count_fields": list(SERIES_FIELDS), "storm_values": "1-250", "missing_value": 255,
                   "same_sol_merge": "pixel union of valid and storm observations across records of one sol"},
        "years": {str(my): {"records": r["records"], "sols": int(len(r["sol"])), "duplicate_sols": r["duplicate_sols"],
                            "ls_first": round(float(r["ls"][0]), 2), "ls_last": round(float(r["ls"][-1]), 2)}
                  for my, r in sorted(years.items())},
        "series_sha256": sha256_file(series),
    }
    (output / "dust-series-manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest


def load_series(directory: Path) -> dict:
    with np.load(Path(directory) / "dust-series.npz", allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    manifest = json.loads((Path(directory) / "dust-series-manifest.json").read_text())
    if manifest.get("series_sha256") != sha256_file(Path(directory) / "dust-series.npz"):
        raise DustDataError("dust-series.npz does not match its manifest digest")
    years = sorted(int(key[2:4]) for key in arrays if key.endswith("_sol"))
    return {"manifest": manifest, "region_ids": [str(x) for x in arrays["region_ids"]],
            "core_total": arrays["core_total"], "ring_total": arrays["ring_total"],
            "years": {my: {"sol": arrays[f"my{my}_sol"], "ls": arrays[f"my{my}_ls"], "counts": arrays[f"my{my}_counts"]}
                      for my in years}}
