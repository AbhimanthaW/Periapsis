"""Cross-check the existing Jezero window against a bounded USGS raster read."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
import rasterio
from rasterio.windows import Window

from marsdoc import Package
from marsdoc.contracts import Dataset, Footprint, MarsCRS, Polygon, Product

URL = ("https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/"
       "ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif")
CATALOG = "https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic"
PRODUCT_ID = "M20_JezeroCrater_CTXDEM_20m:window-r1978-c732"
VERSION = "window-v1"
SOURCE_SHA256 = "ba7f706ea1b5d63a562f28a7dcf7a7f3c79bce7f048e6974b57e8a33c30d1ba2"
WINDOW_SHA256 = "020df24a32a2ab472db7c9ddb2538073130916308edcfb6830fe22d08c3e8903"


def verify(data_dir: Path, source: Path | None = None, reconstruct=False):
    if reconstruct and source is None:
        raise ValueError("reconstruction requires the pinned local GeoTIFF")
    if source is not None:
        with source.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != SOURCE_SHA256:
                raise ValueError("archive checksum differs from the reviewed GeoTIFF")
    manifest_file = data_dir / "jezero.json"
    manifest_bytes = manifest_file.read_bytes()
    meta = json.loads(manifest_bytes)
    if (meta["source"]["url"] != URL or meta["width"] != 1024 or meta["height"] != 1024
            or meta["pixelSize"] != [20, 20]):
        raise ValueError("unexpected Jezero package identity, window shape or pixel size")

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with rasterio.open(source if source is not None else URL) as raster:
            x, y = meta["origin"]
            row, col = raster.index(x + 10, y - 10)
            if (row, col) != (1978, 732) or raster.res != (20, 20):
                raise ValueError("archive product grid or registration differs")
            window = Window(col, row, meta["width"], meta["height"])
            left, bottom, right, top = raster.window_bounds(window)
            if not np.allclose([left, top], [x, y], atol=1e-6, rtol=0):
                raise ValueError("prepared raster origin does not match the source window")
            values = raster.read(1, window=window, masked=True)
            native = CRS.from_wkt(raster.crs.to_wkt())
            geo = native.geodetic_crs
            if (geo.ellipsoid.semi_major_metre != 3_396_190 or geo.ellipsoid.inverse_flattening != 0
                    or geo.prime_meridian.longitude != 0 or "Mars" not in geo.name):
                raise ValueError("source does not declare the expected Mars 2000 reference")
            inverse = Transformer.from_crs(native, geo, always_xy=True)
            native_wkt = raster.crs.to_wkt()

    output = data_dir / "jezero-elevation.f32"
    source_bytes = values.data.astype("<f4", copy=False).tobytes()
    if (np.ma.getmaskarray(values).any() or not np.isfinite(values.data).all()
            or sha256(source_bytes).hexdigest() != WINDOW_SHA256):
        raise ValueError("source does not contain the pinned valid elevation window")
    if reconstruct:
        with output.open("xb") as stream:
            stream.write(source_bytes)
    elif output.read_bytes() != source_bytes:
        raise ValueError("prepared elevation differs from the valid source window")
    xmin, ymin, xmax, ymax = left + 20, bottom + 20, right - 20, top - 20
    # Keep one source posting of margin and densify native edges before inverse mapping.
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)]
    native_edges = np.concatenate([np.linspace(a, b, 16, endpoint=False)
                                   for a, b in zip(corners, corners[1:])] + [[corners[0]]])
    lons, lats = inverse.transform(*native_edges.T, errcheck=True)
    ring = tuple(zip(lons, lats))
    footprint = Footprint(
        id="jezero-ctx-window-support", product_id=PRODUCT_ID, source_url=URL,
        status="canonical_verified", coverage_kind="usable_support",
        geometry=Polygon(type="Polygon", coordinates=(ring,)),
        transform="USGS GeoTIFF WKT inverse to Mars 2000 spherical geographic lon/lat. "
                  "Native rectangle inset 20 m and densified before inverse transform.",
        note="Whole prepared window compared with the authoritative raster and mask. "
             "Polygon represents inset valid elevation support only.",
    )
    product = Product(
        id=PRODUCT_ID, dataset_id="usgs-jezero-ctx-dem", version=VERSION, source_url=URL,
        source_crs=MarsCRS(body="Mars", frame="Mars 2000", definition=native_wkt,
                           equatorial_radius_m=3_396_190, polar_radius_m=3_396_190),
        processing_level="derived_stereo_dem", readiness="usable", native_spacing_m=20,
        variables=("elevation",),
        # Complete for the declared inset support only. The original acquisition remains unclosed.
        support_extent_complete=True,
        provenance=(
            f"sha256 little-endian float32 source window: {sha256(source_bytes).hexdigest()}",
            f"sha256 prepared jezero.json: {sha256(manifest_bytes).hexdigest()}",
            "Verified source window [row 1978, col 732], 1024×1024, zero masked pixels.",
        ),
        limitations=("Verified native sampling only. Effective feature scale and tactical slope support are unset.",
                     "Subset of the Jezero DEM. Catalogue coverage beyond the verified window remains unknown."),
    )
    return Package(
        schema_version=1, package_id="jezero-ctx-usgs-archive-checked-window", version=VERSION,
        datasets=(Dataset(id="usgs-jezero-ctx-dem", mission="Mars Reconnaissance Orbiter",
                          instrument="Context Camera", modality="stereo_topography",
                          product_class="stereo_dtm", archive_url=CATALOG, version="2021-10-14",
                          catalogue_status="incomplete"),),
        products=(product,), footprints=(footprint,),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_data", type=Path)
    parser.add_argument("--source", type=Path, help="Local copy of the pinned public GeoTIFF")
    parser.add_argument("--reconstruct", action="store_true", help="Write a new pinned Float32 window")
    args = parser.parse_args()
    print(verify(args.prepared_data, args.source, args.reconstruct).model_dump_json(indent=2))
