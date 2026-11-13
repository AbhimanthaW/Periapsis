"""Build and verify whole-Mars MOLA elevation and observation-count layers."""

from hashlib import sha256 as hash_bytes
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from affine import Affine
import numpy as np
from pyproj import CRS
import rasterio
from rasterio.errors import RasterioError

from .coordinates import normalize_longitude
from .errors import ConfigurationError, IntegrityError
from .ingestion import ingest, sha256, write_json
from .models import SourceSpec, canonical, safe_name, text
from .mola import COUNTS, TOPOGRAPHY


MANIFEST = "atlas-manifest.json"
REGION_INDEX = "region-index.json"
LAYERS = {"elevation": ("elevation.tif", "m"), "observation_counts": ("observation-counts.tif", "count")}
GRID = Affine(0.25, 0, -180, 0, -0.25, 90)
SHAPE = (720, 1440)
BOUNDS = (-180, -90, 180, 90)
# Bundle identity from the reviewed Stage 1 source record in evidence/mola.
MEG004_BUNDLE_SHA256 = "a845aec8791ba95375d1cecec5b8f6de9f07e2c227bdaf2aec66c8bbf29b9136"


def _load_global_source(spec: SourceSpec, workspace: Path):
    if (spec.expected_lid != TOPOGRAPHY or spec.support_expected_lid != COUNTS
            or not spec.pds4_label or not spec.support_entrypoint
            or not all(member.expected_sha256 for member in spec.members)):
        raise ConfigurationError("The whole-Mars atlas requires the pinned MOLA MEG004 topography and counts pair")
    record, _, _ = ingest(spec, workspace, offline=True)
    if record["bundle_sha256"] != MEG004_BUNDLE_SHA256:
        raise IntegrityError("Source does not match the reviewed MOLA MEG004 bundle")
    bundle = workspace.resolve() / "cache" / "bundles" / record["bundle_sha256"]
    crs = CRS.from_wkt(record["raster"]["crs_wkt"]).geodetic_crs

    arrays = {}
    for role, label in zip(LAYERS, (spec.entrypoint, spec.support_entrypoint), strict=True):
        with rasterio.open(bundle / label) as dataset:
            native = dataset.read(1)
            # The source starts at 0°E. Start at 180°E instead, without resampling.
            arrays[role] = np.roll(native, -SHAPE[1] // 2, axis=1)
    counts = arrays["observation_counts"]
    observed = int(np.count_nonzero(counts))
    metadata = {
        "schema_version": 1,
        "atlas_id": "mars-mola-meg004",
        "capabilities": ["global_elevation_context", "observation_count_context"],
        "grid": {
            "shape": list(SHAPE),
            "affine": list(GRID)[:6],
            "bounds_deg": list(BOUNDS),
            "crs_wkt": crs.to_wkt(),
            "longitude": "east-positive, [-180, 180)",
            "latitude": "planetocentric, north to south",
            "pixel_reference": "area; sample coordinates are cell centres",
            "native_pixels_per_degree": 4,
        },
        "source": {
            "asset_id": spec.asset_id,
            "version": spec.source_version,
            "bundle_sha256": record["bundle_sha256"],
            "provider": spec.provider,
            "attribution": spec.attribution,
            "vertical_reference": spec.reference.vertical_reference,
            "members": [
                {key: member[key] for key in ("name", "uri", "sha256", "bytes")}
                for member in record["members"]
            ],
        },
        "coverage": {
            "total_cells": counts.size,
            "valid_elevation_cells": record["raster"]["valid_pixels"],
            "cells_with_observations": observed,
            "zero_observation_cells": counts.size - observed,
            "missing_count_cells": record["observation_support"]["missing_count_cells"],
        },
        "limitations": [
            "Coarse elevation context for all Mars. Elevation includes interpolated cells.",
            "Observation counts describe sampling support. Fine terrain and routing are outside this atlas.",
        ],
    }
    return metadata, arrays, crs


def _region_index(catalog: Path, arrays: dict) -> dict:
    raw = catalog.read_bytes()
    try:
        document = json.loads(raw)
        regions = document["regions"]
        if not isinstance(regions, list) or not regions:
            raise ConfigurationError("Atlas region catalog must contain a nonempty regions array")
        entries = {}
        for region in regions:
            identifier = safe_name(region["id"], "region ID")
            if identifier in entries:
                raise ConfigurationError(f"Duplicate atlas region ID: {identifier}")
            geography = region["geography"]
            center = geography["center"]
            if (not isinstance(center, list) or len(center) != 2
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in center)
                    or not -180 <= center[0] <= 180 or not -90 <= center[1] <= 90):
                raise ConfigurationError(f"Invalid atlas center for region {identifier}")
            lon, lat = center
            col = int((normalize_longitude(lon) - GRID.c) / GRID.a) % SHAPE[1]
            row = min(int((lat - GRID.f) / GRID.e), SHAPE[0] - 1)
            entries[identifier] = {
                "region_id": identifier,
                "name": text(region["name"], "region name"),
                "geography_status": text(geography["status"], "geography status"),
                "center_lon_lat_deg": center,
                "cell_row_col": [row, col],
                "elevation_m": int(arrays["elevation"][row, col]),
                "observation_count": int(arrays["observation_counts"][row, col]),
            }
    except ConfigurationError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ConfigurationError(f"Malformed atlas region catalog: {error}") from error
    return {
        "schema_version": 1,
        "catalog_sha256": hash_bytes(raw).hexdigest(),
        "sample_scope": "MOLA grid cell containing the catalog point",
        "region_count": len(entries),
        "regions": list(entries.values()),
    }


def build_global_atlas(spec: SourceSpec, workspace: Path, output: Path, *, regions: Path) -> dict:
    """Write an immutable atlas directory from a verified offline source cache."""
    if output.exists() or output.is_symlink():
        raise ConfigurationError(f"Atlas destination already exists: {output}")
    metadata, arrays, crs = _load_global_source(spec, workspace)
    region_index = _region_index(regions, arrays)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".mars-atlas-", dir=output.parent) as scratch:
        staging = Path(scratch) / "atlas"
        staging.mkdir()
        assets = {}
        for role, (name, unit) in LAYERS.items():
            path = staging / name
            with rasterio.open(
                path, "w", driver="GTiff", height=SHAPE[0], width=SHAPE[1], count=1,
                dtype="int16", transform=GRID, crs=crs.to_wkt(), compress="deflate",
            ) as dataset:
                dataset.write(arrays[role], 1)
                dataset.set_band_unit(1, unit)
                dataset.update_tags(AREA_OR_POINT="Area")
            assets[role] = {"path": name, "unit": unit, "bytes": path.stat().st_size, "sha256": sha256(path)}
        index_path = staging / REGION_INDEX
        write_json(index_path, region_index)
        index_asset = _region_asset(index_path, region_index)
        write_json(staging / MANIFEST, {**metadata, "layers": assets, "region_index": index_asset})
        report = _validate_atlas(staging, metadata, arrays, crs, region_index)
        if output.exists() or output.is_symlink():
            raise ConfigurationError(f"Atlas destination already exists: {output}")
        staging.rename(output)
    return report


def _region_asset(path: Path, index: dict) -> dict:
    return {
        "path": REGION_INDEX, "bytes": path.stat().st_size, "sha256": sha256(path),
        "region_count": index["region_count"], "catalog_sha256": index["catalog_sha256"],
    }


def validate_global_atlas(spec: SourceSpec, workspace: Path, directory: Path, *, regions: Path) -> dict:
    """Compare the global layers and catalog point samples using only local files."""
    metadata, arrays, crs = _load_global_source(spec, workspace)
    return _validate_atlas(directory, metadata, arrays, crs, _region_index(regions, arrays))


def _validate_atlas(directory: Path, metadata: dict, arrays: dict, crs: CRS, region_index: dict) -> dict:
    names = {MANIFEST, REGION_INDEX, *(name for name, _ in LAYERS.values())}
    if {path.name for path in directory.iterdir()} != names:
        raise IntegrityError("Atlas inventory differs from the required manifest, region index and two global layers")
    for name in names:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise IntegrityError(f"Atlas entry must be an ordinary file: {name}")
    try:
        manifest = json.loads((directory / MANIFEST).read_bytes())
        assets = manifest.pop("layers")
        index_asset = manifest.pop("region_index")
        index_path = directory / REGION_INDEX
        if canonical(index_asset) != canonical(_region_asset(index_path, region_index)):
            raise IntegrityError("Region index checksum or catalog identity mismatch")
        if canonical(json.loads(index_path.read_bytes())) != canonical(region_index):
            raise IntegrityError("Region index entries differ from the catalog and pinned MOLA data")
        if canonical(manifest) != canonical(metadata) or set(assets) != set(LAYERS):
            raise IntegrityError("Atlas metadata differs from the verified global source")
        for role, (name, unit) in LAYERS.items():
            path = directory / name
            expected = {"path": name, "unit": unit, "bytes": path.stat().st_size, "sha256": sha256(path)}
            if canonical(assets[role]) != canonical(expected):
                raise IntegrityError(f"Atlas checksum or layer metadata mismatch: {role}")
            with rasterio.open(path) as dataset:
                if (
                    dataset.driver != "GTiff" or dataset.count != 1 or dataset.shape != SHAPE
                    or dataset.transform != GRID or tuple(dataset.bounds) != BOUNDS
                    or dataset.crs is None or not crs.equals(CRS.from_wkt(dataset.crs.to_wkt()), ignore_axis_order=True)
                    or dataset.dtypes != ("int16",) or dataset.units != (unit,) or dataset.nodata is not None
                    or dataset.scales != (1.0,) or dataset.offsets != (0.0,)
                    or dataset.tags().get("AREA_OR_POINT") != "Area"
                ):
                    raise IntegrityError(f"Atlas grid or encoding mismatch: {role}")
                if not np.all(dataset.read_masks(1) == 255):
                    raise IntegrityError(f"Atlas layer contains missing cells: {role}")
                if not np.array_equal(dataset.read(1), arrays[role]):
                    raise IntegrityError(f"Atlas cells differ from the pinned source: {role}")
    except IntegrityError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, RasterioError) as error:
        raise IntegrityError(f"Malformed atlas: {error}") from error
    return {
        "atlas_id": metadata["atlas_id"],
        "bounds_deg": metadata["grid"]["bounds_deg"],
        "shape": metadata["grid"]["shape"],
        "coverage": metadata["coverage"],
        "verified_artifacts": assets,
        "region_index": index_asset,
        "validation_scope": "Offline global MOLA source, geographic grid, raster values and catalog point samples",
    }
