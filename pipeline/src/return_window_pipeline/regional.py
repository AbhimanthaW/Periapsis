"""Build and inspect the Stage 2 offline elevation-preview fixture."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256 as hash_bytes
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.errors import RasterioError

from .coordinates import validate_crs
from .errors import ConfigurationError, IntegrityError
from .ingestion import ingest, sha256, write_json
from .models import MarsReference, SourceSpec, keys, safe_name
from .terrain import MAX_NATIVE_CELLS, prepare_terrain


MANIFEST = "site.json"
ELEVATION_PREVIEW = "elevation-preview.tif"
PREVIEW_CAPABILITIES = {
    "mapping": True,
    "elevation_preview": True,
    "regional_analysis": False,
    "routing": False,
    "science_tasks": False,
}
PREVIEW_GATES = {f"G{i}": "Not evaluated" for i in range(1, 11)}


@dataclass(frozen=True)
class RegionalJob:
    region_id: str
    pack_id: str
    pack_version: str
    aoi_version: str
    bounds_m: tuple[float, ...]
    coarsening_factor: int
    source: SourceSpec
    config_sha256: str


def load_job(path: Path) -> RegionalJob:
    raw = path.read_bytes()
    job = keys(
        json.loads(raw),
        {"schema_version", "region_id", "pack_id", "pack_version", "capability",
         "source_config", "aoi", "coarsening_factor"},
        set(),
        "regional job",
    )
    if type(job["schema_version"]) is not int or job["schema_version"] != 1:
        raise ConfigurationError("Unsupported regional job schema")
    if job["capability"] != "elevation_preview":
        raise ConfigurationError("This producer supports elevation_preview jobs")
    aoi = keys(job["aoi"], {"version", "crs", "bounds_m"}, set(), "regional AOI")
    if aoi["crs"] != "source_native":
        raise ConfigurationError("This preview requires AOI bounds in the pinned raster's native CRS")
    bounds = aoi["bounds_m"]
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in bounds)
            or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
        raise ConfigurationError("AOI bounds must be [west, south, east, north] in native projected metres")
    if type(job["coarsening_factor"]) is not int or job["coarsening_factor"] < 1:
        raise ConfigurationError("coarsening_factor must be a positive integer")
    if not isinstance(job["source_config"], str) or not job["source_config"].strip():
        raise ConfigurationError("source_config must name a Stage 1 source configuration")
    source = SourceSpec.load(path.parent / job["source_config"])
    if source.role != "elevation" or not all(member.expected_sha256 for member in source.members):
        raise ConfigurationError("Regional preview requires a checksum-pinned elevation source")
    return RegionalJob(
        region_id=safe_name(job["region_id"], "region_id"),
        pack_id=safe_name(job["pack_id"], "pack_id"),
        pack_version=safe_name(job["pack_version"], "pack_version"),
        aoi_version=safe_name(aoi["version"], "aoi.version"),
        bounds_m=tuple(bounds),
        coarsening_factor=job["coarsening_factor"],
        source=source,
        config_sha256=hash_bytes(raw).hexdigest(),
    )


def _bounds(transform, height: int, width: int) -> list[float]:
    return [
        transform.c, transform.f + transform.e * height,
        transform.c + transform.a * width, transform.f,
    ]


def build_preview(job: RegionalJob, workspace: Path, output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise ConfigurationError(f"Preview destination already exists: {output}")
    record, record_path, _ = ingest(job.source, workspace, offline=True)
    source_path = workspace.resolve() / "cache" / "bundles" / record["bundle_sha256"] / job.source.entrypoint
    with rasterio.open(source_path) as dataset:
        terrain = prepare_terrain(
            dataset, band=job.source.band, reference=job.source.reference,
            bounds_m=job.bounds_m, factor=job.coarsening_factor,
        )

    transform = terrain.transform
    height, width = terrain.elevation_m.shape
    bounds = _bounds(transform, height, width)
    wkt = terrain.crs.to_wkt()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(output.name + ".building")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ConfigurationError(f"Another preview build owns {lock.name}") from error
    try:
        with TemporaryDirectory(prefix=".preview-", dir=output.parent) as temp:
            staging = Path(temp) / "pack"
            staging.mkdir()
            preview = staging / ELEVATION_PREVIEW
            with rasterio.open(
                preview, "w", driver="GTiff", width=width, height=height, count=1,
                dtype="float32", crs=wkt, transform=transform, nodata=float("nan"),
                compress="deflate", predictor=3,
            ) as dataset:
                dataset.write(terrain.elevation_m, 1)
                dataset.set_band_unit(1, "m")
            asset = {"path": ELEVATION_PREVIEW, "bytes": preview.stat().st_size, "sha256": sha256(preview)}
            manifest = {
                "schema_version": 1,
                "status": "integration_fixture",
                "region_id": job.region_id,
                "pack_id": job.pack_id,
                "pack_version": job.pack_version,
                "processing_date": datetime.now(timezone.utc).isoformat(),
                "processing_config_sha256": job.config_sha256,
                "aoi": {"version": job.aoi_version, "requested_bounds_m": job.bounds_m, "crs_wkt": wkt},
                "shape": [height, width],
                "affine": list(transform)[:6],
                "affine_order": ["a", "b", "c", "d", "e", "f"],
                "bounds_m": bounds,
                "coordinate_order": ["easting_m", "northing_m"],
                "index_order": ["row", "col"],
                "pixel_reference": "outer affine edges; sample positions are pixel centres",
                "source_crs_wkt": wkt,
                "local_crs_wkt": wkt,
                "source_reference": asdict(job.source.reference),
                "vertical_reference": job.source.reference.vertical_reference,
                "vertical_unit": "m",
                "native_posting_m": list(terrain.native_posting_m),
                "output_posting_m": [transform.a, -transform.e],
                "effective_terrain_scale_m": None,
                "source": {
                    "asset_id": record["asset_id"], "version": record["source_version"],
                    "provider": job.source.provider, "attribution": job.source.attribution,
                    "access_rights": job.source.access_rights,
                    "members": [
                        {key: member[key] for key in ("name", "uri", "sha256", "bytes")}
                        for member in record["members"]
                    ],
                    "bundle_sha256": record["bundle_sha256"],
                    "record_file_sha256": sha256(record_path),
                    "record_schema_version": record["source_record_schema_version"],
                    "reference_evidence": record["diagnostics"]["reference_evidence"],
                    "limitations": job.source.limitations,
                },
                "processing": {
                    "horizontal_operation": "retain the pinned source's native north-up metre projection",
                    "vertical_operation": "apply source band scale and offset and convert configured units to metres",
                    "source_window_col_row_width_height": list(terrain.source_window.flatten()),
                    "buffered_window_col_row_width_height": list(terrain.buffered_window.flatten()),
                    "coarsening_factor": job.coarsening_factor,
                    "elevation_aggregation": "mean of aligned native pixels, with complete elevation support",
                    "gradient": "four cardinal neighbours plus valid centre, using geodesic east/north displacements",
                    "slope_aggregation": "maximum native slope, requiring complete gradient support",
                    "aspect": "downslope bearing clockwise from true north at the steepest supported sample; flat undefined",
                    "invalid_elevation": "NaN with GeoTIFF nodata",
                },
                "coverage": {
                    "total_cells": height * width,
                    "valid_elevation_cells": int(terrain.elevation_valid.sum()),
                    "full_gradient_support_cells": int(terrain.gradient_valid.sum()),
                },
                "capabilities": PREVIEW_CAPABILITIES,
                "gate_results": PREVIEW_GATES,
                "layers": {
                    "elevation_preview": {"available": True, "bounds_m": bounds, "asset": asset,
                                          "attribution": job.source.attribution},
                    "analytical_terrain": {"available": False, "reason": "Elevation preview capability only."},
                    "optical": {"available": False, "reason": "No separately pinned optical layer in this fixture."},
                    "geology": {"available": False, "reason": "No registered geology layer in this fixture."},
                    "science_evidence": {"available": False, "reason": "Evidence sidecar awaits consumer integration."},
                    "stations": {"available": False, "reason": "No reviewed stations or tasks in this fixture."},
                },
            }
            write_json(staging / MANIFEST, manifest)
            verify_preview(staging)
            if output.exists():
                raise ConfigurationError(f"Preview destination already exists: {output}")
            staging.rename(output)
    finally:
        lock.rmdir()
    return manifest


def verify_preview(directory: Path) -> dict:
    """Check the producer fixture independently of the planned mission loader."""
    try:
        manifest = json.loads((directory / MANIFEST).read_bytes())
        capabilities = manifest["capabilities"]
        if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
                or manifest["status"] != "integration_fixture"
                or capabilities.keys() != PREVIEW_CAPABILITIES.keys()
                or any(capabilities[key] is not value for key, value in PREVIEW_CAPABILITIES.items())):
            raise IntegrityError("Preview fixture has an invalid schema, status or capability")
        if manifest["gate_results"] != PREVIEW_GATES:
            raise IntegrityError("Preview fixture cannot claim regional release gates")
        if {entry.name for entry in directory.iterdir()} != {MANIFEST, ELEVATION_PREVIEW}:
            raise IntegrityError("Preview pack file inventory differs from the producer contract")
        layer = manifest["layers"]["elevation_preview"]
        asset = layer["asset"]
        preview = directory / ELEVATION_PREVIEW
        if (layer["available"] is not True
                or manifest["layers"]["analytical_terrain"]["available"] is not False
                or asset["path"] != ELEVATION_PREVIEW or preview.is_symlink()
                or preview.stat().st_size != asset["bytes"] or sha256(preview) != asset["sha256"]):
            raise IntegrityError("Preview layer or file checksum mismatch")
        if (manifest["coordinate_order"] != ["easting_m", "northing_m"]
                or manifest["index_order"] != ["row", "col"]
                or manifest["affine_order"] != ["a", "b", "c", "d", "e", "f"]):
            raise IntegrityError("Preview grid conventions do not match the producer contract")
        reference = MarsReference.parse(manifest["source_reference"])
        declared_crs = validate_crs(manifest["local_crs_wkt"], reference, require_metric=True)
        with rasterio.open(preview) as dataset:
            actual_crs = validate_crs(dataset.crs.to_wkt(), reference, require_metric=True)
            transform = dataset.transform
            bounds = _bounds(transform, dataset.height, dataset.width)
            if (
                dataset.driver != "GTiff" or dataset.count != 1 or dataset.dtypes != ("float32",)
                or dataset.units != ("m",) or dataset.nodata is None or not math.isnan(dataset.nodata)
                or not actual_crs.equals(declared_crs)
                or list(dataset.shape) != manifest["shape"]
                or list(transform)[:6] != manifest["affine"]
                or bounds != manifest["bounds_m"] or bounds != layer["bounds_m"]
                or transform.a <= 0 or transform.e >= 0 or transform.b != 0 or transform.d != 0
                or dataset.width * dataset.height > MAX_NATIVE_CELLS
            ):
                raise IntegrityError("Preview raster disagrees with the declared grid or encoding")
            elevation = dataset.read(1)
            valid = dataset.read_masks(1) > 0
            coverage = manifest["coverage"]
            if (not np.array_equal(np.isfinite(elevation), valid)
                    or not 0 < int(valid.sum()) == coverage["valid_elevation_cells"]
                    or elevation.size != coverage["total_cells"]
                    or not 0 <= coverage["full_gradient_support_cells"] <= coverage["valid_elevation_cells"]):
                raise IntegrityError("Preview raster disagrees with the declared coverage")
    except (AttributeError, KeyError, OSError, TypeError, ValueError, RasterioError) as error:
        raise IntegrityError(f"Unreadable or malformed preview fixture: {error}") from error
    return {"pack_id": manifest["pack_id"], "verified_artifacts": 1, "coverage": coverage}
