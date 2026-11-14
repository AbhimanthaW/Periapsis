"""Cell metrics for prepared geomorphology, magnetism and reflectance inputs."""
from dataclasses import dataclass
from math import fsum, isfinite

import numpy as np
from shapely import LineString, union_all

from .contracts import Polygon
from .spatial import Cap, Part, Window, surface_parts, vectors

OLIVINE_THRESHOLD = 1.04


@dataclass(frozen=True)
class MappedArea:
    id: str
    kind: str
    part: Part

    @classmethod
    def prepare(cls, identifier: str, kind: str, geometry: Polygon):
        part, = surface_parts(geometry)
        return cls(identifier, kind, part)


@dataclass(frozen=True)
class MappedLine:
    id: str
    cap: Cap
    vertices: np.ndarray

    @classmethod
    def prepare(cls, identifier, coordinates):
        vertices = vectors(coordinates)
        if len(vertices) < 2 or np.any(np.linalg.norm(np.diff(vertices, axis=0), axis=1) < 1e-14):
            raise ValueError("mapped line needs distinct consecutive positions")
        return cls(identifier, Cap.enclosing(vertices, 25), vertices)


def mapped_areas(window: Window, features: tuple[MappedArea, ...], survey: Part):
    """Union overlap within each mapped class, with a separate survey denominator."""
    domain = window.clip_part(survey)
    survey_fraction = window.fraction(domain)
    if survey_fraction == 0:
        return None
    shapes = []
    identifiers = []
    for feature in features:
        intersection = domain.intersection(window.clip_part(feature.part))
        if window.chart.area(intersection) > 0:
            shapes.append(intersection)
            identifiers.append(feature.id)
    area = union_all(shapes)
    return {
        "surveyed_fraction": survey_fraction,
        "mapped_fraction": window.fraction(area),
        "mapped_area_km2": window.chart.area(area) / 1e6,
        "feature_ids": sorted(set(identifiers)),
    }


def mapped_valley_length(window: Window, features: tuple[MappedLine, ...], survey: Part):
    """Clip great-circle linework to the surveyed cell and union coincident segments."""
    domain = window.clip_part(survey)
    survey_fraction = window.fraction(domain)
    if survey_fraction == 0:
        return None
    lines = []
    identifiers = []
    for feature in features:
        if window.cap.intersects(feature.cap):
            line = LineString(window.chart.project(feature.vertices))
            clipped = domain.intersection(line)
            if window.chart.length(clipped) > 0:
                lines.append(clipped)
                identifiers.append(feature.id)
    length_km = window.chart.length(union_all(lines)) / 1000
    return {
        "surveyed_fraction": survey_fraction,
        "length_km": length_km,
        "length_per_surveyed_km2": length_km / (window.chart.area(domain) / 1e6),
        "feature_ids": sorted(set(identifiers)),
    }


@dataclass(frozen=True)
class MagneticDipole:
    position: tuple[float, float]
    depth_km: float
    axis_lon_lat: tuple[float, float]
    strength_nt_km3: float


def dipole_field(position, *, reference_radius_km, altitude_km, sources: tuple[MagneticDipole, ...]):
    """Sum internal equivalent dipoles in Cartesian Mars-fixed axes."""
    if (not isfinite(reference_radius_km) or reference_radius_km <= 0
            or not isfinite(altitude_km) or altitude_km < 0 or not sources):
        raise ValueError("dipole field needs sources, a positive radius and a nonnegative altitude")
    radial, = vectors([position])
    observer = (reference_radius_km + altitude_km) * radial
    contributions = []
    for source in sources:
        if (not 0 < source.depth_km <= reference_radius_km
                or not isfinite(source.strength_nt_km3) or source.strength_nt_km3 < 0):
            raise ValueError("dipole needs a positive depth and nonnegative finite strength")
        location, axis = vectors([source.position, source.axis_lon_lat])
        separation = observer - (reference_radius_km - source.depth_km) * location
        distance = np.linalg.norm(separation)
        direction = separation / distance
        scale = source.strength_nt_km3 / distance ** 3
        contributions.append(scale * (3 * np.dot(axis, direction) * direction - axis))
    vector = np.sum(contributions, axis=0)
    return {
        "altitude_above_reference_sphere_km": altitude_km,
        "reference_radius_km": reference_radius_km,
        "magnitude_nt": float(np.linalg.norm(vector)),
        "outward_nt": float(np.dot(vector, radial)),
        "mars_fixed_xyz_nt": vector.tolist(),
    }


def olivine_indices(reflectance, *, post_orbit_7768: bool):
    """Calculate OSP1 and OSP2 from prepared I/F divided by incidence cosine."""
    short, long = (1030, 1490) if post_orbit_7768 else (1010, 1500)
    bands = (short, 1210, 1360, long, 1540, 1560, 1690, 1700)
    values = [reflectance.get(band) for band in bands]
    if any(value is None or not np.isfinite(value) or value <= 0 for value in values):
        return None
    short_r, r1210, r1360, long_r, r1540, r1560, r1690, r1700 = values
    osp1 = (r1540 + r1560) / 2 / (0.1 * short_r + 0.2 * r1210 + 0.7 * r1360)
    osp2 = (r1690 + r1700) / 2 / (0.05 * short_r + 0.05 * r1210 + 0.45 * r1360 + 0.45 * long_r)
    return osp1, osp2


@dataclass(frozen=True)
class SpectralTile:
    part: Part
    indices: tuple[float, float] | None


def olivine_cell(window: Window, tiles: tuple[SpectralTile, ...]):
    """Area-weight the valid, non-overlapping spectral tiles in a cell."""
    valid = []
    detected = []
    weighted = []
    for tile in tiles:
        if tile.indices is None:
            continue
        clipped = window.clip_part(tile.part)
        area = window.chart.area(clipped)
        if area <= 0:
            continue
        valid.append(clipped)
        weighted.append((area, *tile.indices))
        if max(tile.indices) > OLIVINE_THRESHOLD:
            detected.append(clipped)
    if not valid:
        return None
    observed = union_all(valid)
    area = window.chart.area(observed)
    total = fsum(piece[0] for piece in weighted)
    if abs(total - area) > max(1e-3, total * 1e-9):
        raise ValueError("olivine tiles overlap; normalize the mosaic before area-weighting")
    positive = union_all(detected)
    return {
        "valid_spectral_fraction": window.fraction(observed),
        "candidate_fraction_of_cell": window.fraction(positive),
        "candidate_fraction_of_valid_spectra": window.chart.area(positive) / area,
        "mean_osp1": fsum(piece[0] * piece[1] for piece in weighted) / total,
        "mean_osp2": fsum(piece[0] * piece[2] for piece in weighted) / total,
        "candidate_threshold": OLIVINE_THRESHOLD,
    }
