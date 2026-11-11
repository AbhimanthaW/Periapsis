from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from pyproj import CRS, Transformer, network
from pyproj.exceptions import ProjError

from .errors import CoordinateError
from .models import MarsReference

network.set_network_enabled(False)


def normalize_longitude(longitude: float, direction: str = "east", domain: str = "-180_180") -> float:
    if not math.isfinite(longitude):
        raise CoordinateError("Longitude must be finite")
    if direction not in {"east", "west"} or domain not in {"0_360", "-180_180"}:
        raise CoordinateError("Unknown longitude convention")
    east = longitude if direction == "east" else -longitude
    return east % 360.0 if domain == "0_360" else (east + 180.0) % 360.0 - 180.0


def convert_latitude(latitude: float, source: str, target: str, reference: MarsReference) -> float:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise CoordinateError("Latitude must be finite and within [-90, 90]")
    if source not in {"planetocentric", "planetographic"} or target not in {"planetocentric", "planetographic"}:
        raise CoordinateError("Unknown latitude convention")
    if source == target:
        return latitude
    radians = math.radians(latitude)
    ratio = (reference.semi_minor_m / reference.semi_major_m) ** 2
    factor = ratio if source == "planetographic" else 1 / ratio
    return math.degrees(math.atan2(factor * math.sin(radians), math.cos(radians)))


def normalize_position(longitude: float, latitude: float, reference: MarsReference) -> tuple[float, float]:
    return (
        normalize_longitude(longitude, reference.longitude_direction, "-180_180"),
        convert_latitude(latitude, reference.latitude_type, "planetocentric", reference),
    )


def validate_crs(value: object, reference: MarsReference, *, require_metric: bool = False) -> CRS:
    try:
        crs = CRS.from_user_input(value)
    except (ProjError, TypeError, ValueError) as error:
        raise CoordinateError(f"Unreadable CRS: {error}") from error
    if crs.geodetic_crs is None:
        raise CoordinateError("CRS must have an inspectable geodetic reference")
    ellipsoid = crs.geodetic_crs.ellipsoid
    for found, declared in ((ellipsoid.semi_major_metre, reference.semi_major_m), (ellipsoid.semi_minor_metre, reference.semi_minor_m)):
        if not math.isclose(found, declared, rel_tol=1e-9, abs_tol=0.001):
            raise CoordinateError("CRS radii disagree with the declared Mars reference")
    if not (crs.is_geographic or crs.is_projected):
        raise CoordinateError("Only geographic and projected horizontal CRS are supported")
    if not math.isclose(crs.geodetic_crs.prime_meridian.longitude, 0, rel_tol=0, abs_tol=1e-12):
        raise CoordinateError("Only the Mars reference prime meridian at zero is supported")
    axes = crs.geodetic_crs.axis_info
    if (len(axes) != 2 or {axis.direction for axis in axes} != {"east", "north"}
            or any(not math.isclose(axis.unit_conversion_factor, math.pi / 180) for axis in axes)):
        raise CoordinateError("The CRS must use east-positive longitude and north-positive latitude in degrees")
    if require_metric:
        if not crs.is_projected or len(crs.axis_info) < 2 or any(not math.isclose(a.unit_conversion_factor, 1.0) for a in crs.axis_info[:2]):
            raise CoordinateError("A regional analysis grid requires projected metre axes")
    return crs


def transform_points(source: object, target: object, points: Iterable[tuple[float, float]], reference: MarsReference) -> list[tuple[float, float]]:
    source_crs, target_crs = validate_crs(source, reference), validate_crs(target, reference)
    if reference.latitude_type == "planetocentric" and not math.isclose(reference.semi_major_m, reference.semi_minor_m):
        raise CoordinateError("Non-spherical planetocentric CRS transformation needs an explicit validated operation; latitude conversion is available separately")
    source_geo, target_geo = source_crs.geodetic_crs, target_crs.geodetic_crs
    if (source_geo.datum.name != target_geo.datum.name
            or not source_geo.equals(target_geo, ignore_axis_order=True)):
        raise CoordinateError("Transform requires a shared geodetic datum; cross-frame operations are not qualified")
    points = list(points)
    if not points:
        return []
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise CoordinateError("Transform inputs must be finite x,y pairs")
    try:
        operation = Transformer.from_crs(source_crs, target_crs, always_xy=True, allow_ballpark=False, only_best=True)
        x, y = operation.transform(*zip(*points), errcheck=True)
    except ProjError as error:
        raise CoordinateError(f"Transformation failed: {error}") from error
    if not np.isfinite(np.array([x, y])).all():
        raise CoordinateError("Transformation produced nonfinite coordinates")
    return list(zip(map(float, x), map(float, y)))


def pixel_center(transform, row: int, col: int) -> tuple[float, float]:
    if type(row) is not int or type(col) is not int or min(row, col) < 0:
        raise CoordinateError("Pixel indices must be nonnegative integers")
    x, y = col + 0.5, row + 0.5
    return float(transform.a * x + transform.b * y + transform.c), float(transform.d * x + transform.e * y + transform.f)
