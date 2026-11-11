from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import RasterioError

from .coordinates import pixel_center, validate_crs
from .errors import IntegrityError
from .models import MarsReference, SourceSpec
from . import mola


def unit_name(value: str | None) -> str | None:
    return {"meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km", "counts": "count"}.get(value.lower(), value.lower()) if value else None


def inspect_raster(path: Path, spec: SourceSpec, label: dict | None) -> dict:
    try:
        with rasterio.open(path) as dataset:
            if spec.band > dataset.count or dataset.crs is None:
                raise IntegrityError("Selected band or georeferencing is missing")
            if np.dtype(dataset.dtypes[spec.band - 1]).kind not in "iuf":
                raise IntegrityError("Only real integer and floating-point raster values are supported")
            crs = validate_crs(dataset.crs.to_wkt(), spec.reference)
            transform = dataset.transform
            if not all(math.isfinite(v) for v in transform) or abs(transform.determinant) == 0:
                raise IntegrityError("Invalid raster affine transform")
            if label:
                mola.validate_product(label, spec.reference)
                mola.validate_grid(dataset, crs, spec.reference)
            elif dataset.driver != "GTiff":
                raise IntegrityError("An unlabeled input must be a GeoTIFF with explicitly configured reference metadata")
            elif spec.reference.longitude_direction != "east":
                raise IntegrityError("GeoTIFF CRS adapter requires east-positive longitude")
            elif crs.is_geographic:
                west, east = (0, 360) if spec.reference.longitude_domain == "0_360" else (-180, 180)
                bounds = dataset.bounds
                if not (west <= bounds.left <= bounds.right <= east and -90 <= bounds.bottom <= bounds.top <= 90):
                    raise IntegrityError("Geographic raster extent conflicts with the declared longitude domain or latitude limits")
            declared_unit = unit_name(label["value_unit"] if label else None)
            stored_unit = unit_name(dataset.units[spec.band - 1])
            for found in (declared_unit, stored_unit):
                if found and found != spec.reference.vertical_unit:
                    raise IntegrityError(f"Raster value unit {found!r} disagrees with declared unit")
            valid_count, low, high = 0, None, None
            for _, window in dataset.block_windows(spec.band):
                values = dataset.read(spec.band, window=window)
                valid = (dataset.read_masks(spec.band, window=window) > 0) & np.isfinite(values)
                selected = values[valid]
                if selected.size:
                    valid_count += int(selected.size)
                    lo, hi = float(selected.min()), float(selected.max())
                    low, high = lo if low is None else min(low, lo), hi if high is None else max(high, hi)
            scale, offset = dataset.scales[spec.band - 1], dataset.offsets[spec.band - 1]
            if not all(math.isfinite(v) for v in (scale, offset)) or not valid_count:
                raise IntegrityError("Raster has no finite valid pixels or an invalid value scale/offset")
            scaled_range = sorted([low * scale + offset, high * scale + offset])
            if not all(math.isfinite(value) for value in scaled_range):
                raise IntegrityError("Nonfinite physical values after raster scaling")
            nodata = dataset.nodatavals[spec.band - 1]
            return {
                "driver": dataset.driver, "band": spec.band,
                "shape": [dataset.height, dataset.width], "dtype": dataset.dtypes[spec.band - 1],
                "crs_wkt": crs.to_wkt(), "affine": list(transform)[:6],
                "bounds_native": list(dataset.bounds), "native_pixel_size": list(dataset.res),
                "horizontal_unit": crs.axis_info[0].unit_name,
                "pixel_center_0_0": list(pixel_center(transform, 0, 0)),
                "row_direction": "rotated" if transform.b or transform.d else ("decreasing_y" if transform.e < 0 else "increasing_y"),
                "valid_pixels": valid_count, "total_pixels": dataset.height * dataset.width,
                "valid_fraction": valid_count / (dataset.height * dataset.width),
                "raw_value_range": [low, high], "scale": scale, "offset": offset,
                "scaled_value_range": scaled_range,
                "value_unit": spec.reference.vertical_unit,
                "value_unit_evidence": "label_or_raster" if declared_unit or stored_unit else "configuration",
                "nodata": str(nodata) if nodata is not None and not math.isfinite(nodata) else nodata,
                "mask_flags": [flag.name for flag in dataset.mask_flag_enums[spec.band - 1]],
                "validity_meaning": "Finite pixels allowed by the source band mask; this does not prove direct observation or routing suitability",
            }
    except RasterioError as error:
        raise IntegrityError(f"Raster cannot be read: {error}") from error


def inspect_observation_support(path: Path, elevation: dict, reference: MarsReference, *, label: dict | None = None) -> dict:
    try:
        with rasterio.open(path) as dataset:
            crs = validate_crs(dataset.crs.to_wkt(), reference)
            if [dataset.height, dataset.width] != elevation["shape"] or not crs.equals(validate_crs(elevation["crs_wkt"], reference)) or not np.allclose(list(dataset.transform)[:6], elevation["affine"], rtol=0, atol=1e-6):
                raise IntegrityError("Observation counts do not align with the elevation grid")
            if label is not None:
                mola.validate_product(label, reference, counts=True)
                mola.validate_grid(dataset, crs, reference)
            elif dataset.driver != "GTiff":
                raise IntegrityError("Unlabeled count checks support GeoTIFF only")
            nodata = dataset.nodata
            if (dataset.count != 1 or np.dtype(dataset.dtypes[0]).kind not in "iu"
                    or unit_name(dataset.units[0]) not in {None, "count", "dimensionless", "1"}
                    or dataset.scales != (1.0,) or dataset.offsets != (0.0,)
                    or (nodata is not None and (not math.isfinite(nodata) or nodata >= 0))):
                raise IntegrityError("Count products require unscaled integer counts, count units and no nonnegative nodata")
            observed, valid_count = 0, 0
            for _, window in dataset.block_windows(1):
                counts = dataset.read(1, window=window)
                valid = (dataset.read_masks(1, window=window) > 0) & np.isfinite(counts)
                if np.any(counts[valid] < 0):
                    raise IntegrityError("Observation counts must be nonnegative integers")
                valid_count += int(valid.sum())
                observed += int((valid & (counts > 0)).sum())
            total = dataset.width * dataset.height
            return {"valid_count_cells": valid_count, "cells_with_observations": observed,
                    "zero_count_cells": valid_count - observed, "missing_count_cells": total - valid_count,
                    "zero_or_missing_count_cells": total - observed,
                    "meaning": "Counts distinguish direct observational support from supplied/interpolated topography; they do not establish terrain accuracy or routing readiness"}
    except (RasterioError, AttributeError) as error:
        raise IntegrityError(f"Observation-count raster cannot be inspected: {error}") from error
