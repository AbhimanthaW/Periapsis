"""Build the Arcadia Planitia evidence handoff from reviewed MOLA source files."""
import argparse
from hashlib import sha256
import json
from math import pi
from pathlib import Path
import struct
import zlib

import numpy as np
import rasterio
from rasterio.windows import Window

from return_window_pipeline.atlas import validate_global_atlas
from return_window_pipeline.ingestion import ingest
from return_window_pipeline.models import SourceSpec


ARCHIVE = "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html"
CATALOG = "https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def ring(bounds):
    west, south, east, north = bounds
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def write_display_png(path, values):
    low, high = int(values.min()), int(values.max())
    pixels = np.round((values.astype(float) - low) * 255 / max(1, high - low)).astype(np.uint8)
    pixels = pixels.repeat(48, axis=0).repeat(48, axis=1)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    height, width = pixels.shape
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + row.tobytes() for row in pixels)))
        + chunk(b"IEND", b"")
    )


def query(bounds):
    return {
        "schema_version": 1,
        "geometry": {"type": "Polygon", "coordinates": [ring(bounds)]},
        "requested": {
            "id": "local_elevation_20m",
            "requirements": [{"variable": "elevation", "product_classes": ["stereo_dtm"],
                              "max_native_spacing_m": 20}],
        },
        "fallbacks": [{
            "id": "coarse_elevation_context",
            "requirements": [{"variable": "elevation", "product_classes": ["laser_altimetry_grid"],
                              "max_native_spacing_m": 15000}],
        }],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("atlas", "workspace", "source-config", "regions", "search", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    spec = SourceSpec.load(args.source_config)
    atlas_report = validate_global_atlas(spec, args.workspace, args.atlas, regions=args.regions)
    source_record, record_path, _ = ingest(spec, args.workspace, offline=True)
    atlas = json.loads((args.atlas / "atlas-manifest.json").read_bytes())
    catalog = json.loads(args.regions.read_bytes())
    region, = [entry for entry in catalog["regions"] if entry["id"] == "03"]
    search = json.loads((args.search / "searches.json").read_bytes())
    candidate, control = search
    center = region["geography"]["center"]
    if region["name"] != "Arcadia Planitia" or candidate["center_lon_lat_deg"] != center:
        raise ValueError("Search does not match Periapsis region 03")
    for comparison in search:
        response_path = args.search / comparison["response_path"]
        raw = json.loads(response_path.read_bytes())
        if (digest(response_path) != comparison["response_sha256"]
                or raw["numberMatched"] != comparison["number_matched"]
                or len(raw["features"]) != comparison["number_returned"]):
            raise ValueError("Catalog search response differs from the recorded comparison")
    if candidate["number_matched"] != 0 or candidate["has_next"] or control["number_matched"] <= 0:
        raise ValueError("Catalog comparison no longer supports this candidate finding")
    with rasterio.open(args.atlas / "elevation.tif") as elevation, rasterio.open(
        args.atlas / "observation-counts.tif"
    ) as counts:
        row, col = elevation.index(*center)
        window = Window(col - 5, row - 5, 11, 11)
        z = elevation.read(1, window=window, masked=True)
        observations = counts.read(1, window=window, masked=True)
        if z.shape != (11, 11) or z.mask.any() or observations.mask.any():
            raise ValueError("Display window requires completely valid raster values")
        display_bounds = list(elevation.window_bounds(window))
        transform = list(elevation.window_transform(window))[:6]
    member = next(entry for entry in atlas["source"]["members"] if entry["name"] == "megt90n000cb.img")
    native_wkt = source_record["raster"]["crs_wkt"]
    display_wkt = atlas["grid"]["crs_wkt"]
    native_spacing_m = spec.reference.semi_major_m * pi / 720
    candidate_dir = args.output
    candidate_dir.mkdir()
    display = candidate_dir / "arcadia-mola-context.png"
    write_display_png(display, z.data)
    physical_grid = candidate_dir / "arcadia-mola-elevation.i16le"
    physical_grid.write_bytes(z.data.astype("<i2").tobytes())
    write_json(
        candidate_dir / "evidence.json",
        {
            "schema_version": 1,
            "package_id": "arcadia-mola-context",
            "version": "0.1.0",
            "datasets": [{
                "id": "mgs-mola-megdr", "mission": "Mars Global Surveyor", "instrument": "MOLA",
                "modality": "baseline_topography", "product_class": "laser_altimetry_grid",
                "archive_url": ARCHIVE, "version": spec.source_version, "catalogue_status": "incomplete",
            }],
            "products": [{
                "id": spec.asset_id, "dataset_id": "mgs-mola-megdr", "version": spec.source_version,
                "source_url": member["uri"], "processing_level": "gridded_altimetry", "readiness": "usable",
                "source_crs": {"body": "Mars", "frame": spec.reference.frame, "definition": native_wkt,
                               "latitude_type": "planetocentric", "longitude_direction": "east",
                               "longitude_domain": "signed", "equatorial_radius_m": spec.reference.semi_major_m,
                               "polar_radius_m": spec.reference.semi_minor_m},
                "variables": ["elevation"], "native_spacing_m": native_spacing_m, "effective_scale_m": None,
                "provenance": [f"MOLA archive raster SHA-256: {member['sha256']}",
                               f"Source bundle SHA-256: {atlas['source']['bundle_sha256']}",
                               f"Verified source registry SHA-256: {digest(record_path)}",
                               f"Verified atlas elevation SHA-256: {atlas_report['verified_artifacts']['elevation']['sha256']}",
                               f"Exact local display grid SHA-256: {digest(physical_grid)}"],
                "limitations": [
                    "Native angular spacing is 0.25 degrees. The metre value is equatorial nominal posting.",
                    "Valid elevation can include interpolated cells. No effective feature scale is qualified.",
                    "The evidence covers regional elevation context only.",
                ],
            }],
            "footprints": [{
                "id": "arcadia-mola-local-elevation-support", "product_id": spec.asset_id,
                "source_url": member["uri"], "status": "canonical_verified", "coverage_kind": "usable_support",
                "geometry": {"type": "Polygon", "coordinates": [ring(candidate["bounds_wsen_deg"])]},
                "transform": "Canonical planetocentric/east-positive atlas grid. Window selected by the catalog point. "
                             "Every elevation cell covering the AOI was checked valid; the AOI is inside the display window.",
                "note": "Bounded claim for elevation context. Aggregate count values are retained separately.",
            }],
        },
    )
    aoi = candidate["bounds_wsen_deg"]
    if not (display_bounds[0] < aoi[0] < aoi[2] < display_bounds[2]
            and display_bounds[1] < aoi[1] < aoi[3] < display_bounds[3]):
        raise ValueError("Candidate AOI falls outside the verified display window")
    write_json(candidate_dir / "evidence-query.json", query(aoi))
    write_json(candidate_dir / "control-query.json", query(control["bounds_wsen_deg"]))
    write_json(candidate_dir / "source-manifest.json", {
        "schema_version": 1,
        "sources": [{
            "id": spec.asset_id, "version": spec.source_version, "kind": "source_backed",
            "recipe_id": "arcadia-mola-native-crop", "attribution": spec.attribution,
            "native_spacing_m": native_spacing_m, "effective_scale_m": None,
            "limitations": ["Regional topography context only. No independently qualified feature scale."],
            "url": member["uri"], "source_sha256": member["sha256"], "window_sha256": digest(physical_grid),
            "native_crs_wkt": native_wkt, "vertical_reference": spec.reference.vertical_reference,
            "transform_policy": "Reindex 0–360 degrees to signed longitude without interpolation, then select native cells.",
        }],
    })
    write_json(candidate_dir / "display-metadata.json", {
        "schema_version": 1, "region_id": region["id"], "name": region["name"], "center_lon_lat_deg": center,
        "aoi_bounds_wsen_deg": aoi, "display_bounds_wsen_deg": display_bounds, "native_crop_affine": transform,
        "crs_wkt": display_wkt, "native_shape": [11, 11], "raw_encoding": "little-endian int16, row major, metres",
        "mask": "all 121 elevation and observation-count cells are valid",
        "display_rule": "black to white over cropped elevation range, 48x nearest-neighbor enlargement for viewing",
        "display_range_m": [int(z.min()), int(z.max())], "center_elevation_m": int(z[5, 5]),
        "center_observation_count": int(observations[5, 5]), "attribution": spec.attribution,
    })
    search_dir = candidate_dir / "catalog-search"
    search_dir.mkdir()
    for name in ("searches.json", *(entry["response_path"] for entry in search)):
        (search_dir / name).write_bytes((args.search / name).read_bytes())
    (candidate_dir / "source-config.json").write_bytes(args.source_config.read_bytes())
    (candidate_dir / "source-record.json").write_bytes(record_path.read_bytes())


if __name__ == "__main__":
    main()
