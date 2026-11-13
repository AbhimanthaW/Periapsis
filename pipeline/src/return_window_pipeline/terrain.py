"""Prepare regional elevation and terrain derivatives on an aligned Mars grid."""

from __future__ import annotations

from dataclasses import dataclass
import math

from affine import Affine
import numpy as np
from pyproj import CRS, Transformer
from rasterio.windows import Window

from .coordinates import validate_crs
from .errors import IntegrityError
from .models import MarsReference


MAX_NATIVE_CELLS = 1_000_000


@dataclass(frozen=True)
class RegionalTerrain:
    elevation_m: np.ndarray
    elevation_valid: np.ndarray
    max_slope_deg: np.ndarray
    steepest_aspect_deg: np.ndarray
    gradient_valid: np.ndarray
    transform: Affine
    crs: CRS
    native_posting_m: tuple[float, float]
    source_window: Window
    buffered_window: Window


def aligned_window(transform: Affine, bounds: tuple[float, ...], width: int, height: int) -> Window:
    if not all(math.isfinite(value) for value in transform):
        raise IntegrityError("Native raster affine must be finite")
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise IntegrityError("Regional processing requires a north-up native grid")
    west, south, east, north = bounds
    edges = (
        (west - transform.c) / transform.a, (north - transform.f) / transform.e,
        (east - transform.c) / transform.a, (south - transform.f) / transform.e,
    )
    col, row, right, bottom = (round(value) for value in edges)
    if any(abs(exact - rounded) > 1e-6 for exact, rounded in zip(edges, (col, row, right, bottom))):
        raise IntegrityError("AOI bounds must align with native pixel edges")
    if not (0 <= col < right <= width and 0 <= row < bottom <= height):
        raise IntegrityError("AOI must fit inside the native raster")
    return Window(col, row, right - col, bottom - row)


def window_transform(transform: Affine, window: Window, factor: int = 1) -> Affine:
    return Affine(
        factor * transform.a, 0, transform.c + window.col_off * transform.a,
        0, factor * transform.e, transform.f + window.row_off * transform.e,
    )


def native_gradients(
    elevation: np.ndarray, valid: np.ndarray, transform: Affine, crs: CRS,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate downhill slope and aspect using four valid cardinal neighbours."""
    slope = np.full(elevation.shape, np.nan)
    aspect = np.full(elevation.shape, np.nan)
    if min(elevation.shape) < 3:
        return slope, aspect

    rows, cols = np.indices(elevation.shape, dtype=np.float64)
    to_geographic = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
    lon, lat = to_geographic.transform(
        transform.c + (cols + 0.5) * transform.a,
        transform.f + (rows + 0.5) * transform.e,
        errcheck=True,
    )
    center = np.s_[1:-1, 1:-1]
    left, right = np.s_[1:-1, :-2], np.s_[1:-1, 2:]
    up, down = np.s_[:-2, 1:-1], np.s_[2:, 1:-1]
    geod = crs.get_geod()

    def displacement(neighbour):
        azimuth, _, distance = geod.inv(lon[center], lat[center], lon[neighbour], lat[neighbour])
        bearing = np.deg2rad(azimuth)
        return distance * np.sin(bearing), distance * np.cos(bearing)

    left_e, left_n = displacement(left)
    right_e, right_n = displacement(right)
    up_e, up_n = displacement(up)
    down_e, down_n = displacement(down)
    across_e, across_n = right_e - left_e, right_n - left_n
    along_e, along_n = down_e - up_e, down_n - up_n
    across_z, along_z = elevation[right] - elevation[left], elevation[down] - elevation[up]
    determinant = across_e * along_n - across_n * along_e
    supported = (
        valid[center] & valid[left] & valid[right] & valid[up] & valid[down]
        & np.isfinite(determinant) & (np.abs(determinant) > 1e-8)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        east_gradient = (across_z * along_n - along_z * across_n) / determinant
        north_gradient = (across_e * along_z - along_e * across_z) / determinant
    magnitude = np.hypot(east_gradient, north_gradient)
    supported &= np.isfinite(magnitude)
    slope[center] = np.where(supported, np.rad2deg(np.arctan(magnitude)), np.nan)
    downhill = np.mod(np.rad2deg(np.arctan2(-east_gradient, -north_gradient)), 360.0)
    aspect[center] = np.where(supported & (magnitude > 0), downhill, np.nan)
    return slope, aspect


def _blocks(values: np.ndarray, factor: int) -> np.ndarray:
    height, width = values.shape
    return values.reshape(height // factor, factor, width // factor, factor).transpose(0, 2, 1, 3).reshape(
        height // factor, width // factor, factor * factor
    )


def prepare_terrain(
    dataset, *, band: int, reference: MarsReference, bounds_m: tuple[float, ...], factor: int,
) -> RegionalTerrain:
    """Read a buffered crop and calculate derivatives before integer coarsening."""
    if type(factor) is not int or factor < 1:
        raise IntegrityError("Coarsening factor must be a positive integer")
    if dataset.crs is None or not 1 <= band <= dataset.count:
        raise IntegrityError("Regional raster must have a CRS and the requested elevation band")
    if reference.vertical_unit not in {"m", "km"}:
        raise IntegrityError("Regional elevation requires metre or kilometre source units")
    if reference.longitude_direction != "east" or (
        reference.latitude_type == "planetocentric" and reference.semi_major_m != reference.semi_minor_m
    ):
        raise IntegrityError("Native gradient requires a supported east-positive Mars geodetic CRS")
    crs = validate_crs(dataset.crs.to_wkt(), reference, require_metric=True)
    window = aligned_window(dataset.transform, bounds_m, dataset.width, dataset.height)
    if window.width % factor or window.height % factor:
        raise IntegrityError("AOI width and height must be multiples of the coarsening factor")
    col = max(0, window.col_off - 1)
    row = max(0, window.row_off - 1)
    right = min(dataset.width, window.col_off + window.width + 1)
    bottom = min(dataset.height, window.row_off + window.height + 1)
    buffered = Window(col, row, right - col, bottom - row)
    if buffered.width * buffered.height > MAX_NATIVE_CELLS:
        raise IntegrityError(f"Buffered AOI exceeds the {MAX_NATIVE_CELLS:,} native-cell processing limit")

    raw = dataset.read(band, window=buffered, masked=True)
    units_to_m = 1_000 if reference.vertical_unit == "km" else 1
    with np.errstate(over="ignore", invalid="ignore"):
        elevation = (raw.data.astype(np.float64) * dataset.scales[band - 1] + dataset.offsets[band - 1]) * units_to_m
    valid = ~np.ma.getmaskarray(raw) & np.isfinite(elevation) & (np.abs(elevation) <= np.finfo(np.float32).max)
    elevation[~valid] = np.nan
    slope, aspect = native_gradients(elevation, valid, window_transform(dataset.transform, buffered), crs)

    first_row, first_col = window.row_off - row, window.col_off - col
    crop = np.s_[first_row:first_row + window.height, first_col:first_col + window.width]
    elevation_blocks = _blocks(elevation[crop], factor)
    elevation_valid = _blocks(valid[crop], factor).all(axis=2)
    output_elevation = elevation_blocks.mean(axis=2).astype(np.float32)
    if not elevation_valid.any():
        raise IntegrityError("AOI has no output cells with complete elevation support")

    slope_blocks = _blocks(slope[crop], factor)
    gradient_valid = np.isfinite(slope_blocks).all(axis=2)
    output_slope = slope_blocks.max(axis=2).astype(np.float32)
    steepest = np.argmax(np.where(np.isfinite(slope_blocks), slope_blocks, -np.inf), axis=2)
    selected_aspect = np.take_along_axis(_blocks(aspect[crop], factor), steepest[..., None], axis=2)[..., 0]
    output_aspect = np.remainder(np.where(gradient_valid, selected_aspect, np.nan).astype(np.float32), 360)

    return RegionalTerrain(
        elevation_m=output_elevation,
        elevation_valid=elevation_valid,
        max_slope_deg=output_slope,
        steepest_aspect_deg=output_aspect,
        gradient_valid=gradient_valid,
        transform=window_transform(dataset.transform, window, factor),
        crs=crs,
        native_posting_m=(dataset.transform.a, -dataset.transform.e),
        source_window=window,
        buffered_window=buffered,
    )
