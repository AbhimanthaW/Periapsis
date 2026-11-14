"""Explicitly synthetic input scene and reproducible documentation context."""
import math

from astropy import units as u
import numpy as np

from .contracts import Point, Polygon
from .grid import RADIUS_M
from .science_context import (
    MagneticDipole, MappedArea, MappedLine, SpectralTile, dipole_field, mapped_areas, mapped_valley_length,
    olivine_cell, olivine_indices,
)
from .spatial import Window, surface_parts

RECIPE = "synthetic-science-v1"
DEMO_POINT = (359.55, 36.1)
PREVIEW_BOUNDS = (-1.6, 34.9, 1.4, 37.25)
MAGNETIC_ALTITUDE_KM = 150.0
FIELDS = {
    "deltas": ("Synthetic putative deltas", "mapped_fraction"),
    "alluvial_fans": ("Synthetic alluvial fans", "mapped_fraction"),
    "valley_networks": ("Synthetic valley networks", "length_km"),
    "glacial_landforms": ("Synthetic glacial landforms", "mapped_fraction"),
    "crustal_magnetism": (f"Synthetic crustal field · {MAGNETIC_ALTITUDE_KM:g} km altitude", "magnitude_nt"),
    "olivine": ("Synthetic olivine spectral candidates", "candidate_fraction_of_cell"),
}
METHODS = {
    "deltas": "mapped-polygon-union-v1",
    "alluvial_fans": "mapped-polygon-union-v1",
    "valley_networks": "survey-clipped-geodesic-line-union-v1",
    "glacial_landforms": "mapped-polygon-union-v1",
    "crustal_magnetism": "internal-equivalent-source-dipoles-v1",
    "olivine": "ody-osp1-osp2-area-weighted-v1",
}


def rectangle(west, south, east, north):
    return polygon((west, south), (east, south), (east, north), (west, north))


def polygon(*outline):
    return Polygon(type="Polygon", coordinates=(outline + (outline[0],),))


SURVEY = rectangle(358.8, 35.25, 1.0, 36.9)
SURVEY_PART, = surface_parts(SURVEY)

# Invented outlines deliberately span multiple cells, with one overlapping pair.
DEPOSITS = (
    MappedArea.prepare("synthetic-delta-01", "scarp_fronted_deposit",
                       polygon((359.38, 36.08), (359.72, 35.93), (359.91, 36.22), (359.70, 36.33))),
    MappedArea.prepare("synthetic-fan-01", "alluvial_fan",
                       polygon((359.80, 35.68), (0.25, 35.52), (0.32, 35.80))),
    MappedArea.prepare("synthetic-fan-02", "alluvial_fan",
                       polygon((0.00, 35.62), (0.39, 35.54), (0.35, 35.86))),
    MappedArea.prepare("synthetic-apron-01", "lobate_debris_apron",
                       polygon((358.98, 36.30), (359.52, 36.36), (359.65, 36.60), (359.29, 36.73))),
    MappedArea.prepare("synthetic-fill-01", "lineated_valley_fill",
                       polygon((0.40, 36.33), (0.67, 36.34), (0.78, 36.63), (0.62, 36.67))),
    MappedArea.prepare("synthetic-crater-fill-01", "concentric_crater_fill",
                       polygon((359.03, 35.44), (359.27, 35.40), (359.36, 35.53), (359.22, 35.66))),
)
VALLEYS = (
    MappedLine.prepare("synthetic-valley-main", ((359.22, 36.65), (359.50, 36.33),
                                               (359.70, 36.20), (0.03, 35.92), (0.64, 35.66))),
    MappedLine.prepare("synthetic-valley-tributary", ((359.82, 36.68), (359.61, 36.46), (359.50, 36.33))),
)

MAGNETIC_SOURCES = (
    MagneticDipole((359.4, 36.0), 20.0, (350.0, 65.0), 1.4e9),
    MagneticDipole((0.5, 36.6), 20.0, (150.0, -20.0), 1.1e9),
)

BASE_SPECTRUM = dict.fromkeys((1010, 1210, 1360, 1500, 1540, 1560, 1690, 1700), 0.24)


def spectral_tile(bounds, spectrum):
    part, = surface_parts(rectangle(*bounds))
    return SpectralTile(part, olivine_indices(spectrum, post_orbit_7768=False))


SPECTRAL_TILES = (
    spectral_tile((358.95, 35.36, 359.51, 36.17), BASE_SPECTRUM),
    spectral_tile((359.60, 35.42, 0.10, 36.36), BASE_SPECTRUM | {1360: 0.195}),
    spectral_tile((0.15, 35.55, 0.62, 36.50), BASE_SPECTRUM | {1360: None}),
)


def evaluate_synthetic_science(cell_id: str, centroid, window: Window):
    """Return demonstration values without adding products to the evidence index."""
    fields = dict.fromkeys(FIELDS)
    if window.fraction(window.clip_part(SURVEY_PART)) > 0:
        areas = {
            "deltas": tuple(feature for feature in DEPOSITS if feature.kind == "scarp_fronted_deposit"),
            "alluvial_fans": tuple(feature for feature in DEPOSITS if feature.kind == "alluvial_fan"),
            "glacial_landforms": tuple(feature for feature in DEPOSITS if feature.kind in {
                "lobate_debris_apron", "lineated_valley_fill", "concentric_crater_fill",
            }),
        }
        for key, features in areas.items():
            fields[key] = mapped_areas(window, features, SURVEY_PART)
        glacial = areas["glacial_landforms"]
        kinds = {feature.id: feature.kind for feature in glacial}
        fields["glacial_landforms"]["feature_types"] = {
            identifier: kinds[identifier] for identifier in fields["glacial_landforms"]["feature_ids"]
        }
        fields["valley_networks"] = mapped_valley_length(window, VALLEYS, SURVEY_PART)
        center = Window.from_geometry(Point(type="Point", coordinates=centroid))
        if not center.clip_part(SURVEY_PART).is_empty:
            fields["crustal_magnetism"] = dipole_field(
                centroid, reference_radius_km=RADIUS_M / 1000, altitude_km=MAGNETIC_ALTITUDE_KM,
                sources=MAGNETIC_SOURCES,
            )
        fields["olivine"] = olivine_cell(window, SPECTRAL_TILES)
    return {
        "cell_id": cell_id,
        "data_status": "synthetic",
        "recipe_id": RECIPE,
        "methods": dict(METHODS),
        "fixture": "Invented seam-crossing scene, no observational inputs.",
        "fields": fields,
    }



def synthetic_scene(engine):
    """Yield all fixture cells in NESTED order using the scene's enclosing cap."""
    cap = SURVEY_PART.cap
    x, y, z = cap.center
    lon = math.atan2(y, x)
    lat = math.atan2(z, math.hypot(x, y))
    radius = 2 * math.asin(cap.chord / 2)
    candidates = engine.grid.healpix.cone_search_lonlat(lon * u.rad, lat * u.rad, radius * u.rad)
    for index in np.sort(candidates):
        result = engine.synthetic_context(engine.grid.identifier(int(index)))
        if any(value is not None for value in result["fields"].values()):
            yield result
