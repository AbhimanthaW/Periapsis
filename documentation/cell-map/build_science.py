"""Join published geology polygons and TES samples to existing HEALPix centroids."""
from collections import Counter
import gzip
from io import BytesIO
from zipfile import ZipFile
import shapefile
from hashlib import file_digest
import json
from pathlib import Path
import sqlite3

import numpy as np
from pyproj import CRS, Transformer
from shapely import Polygon, STRtree, make_valid, points
from shapely.geometry import shape

from workspace import build_workspace

ROOT = build_workspace()
SOURCE = ROOT / "science-sources"
OUTPUT = ROOT / "science"
GEOLOGY = "https://pubs.usgs.gov/sim/3292/"
TES = "https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html"


def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def geology(longitude, latitude):
    layer = json.loads((SOURCE / "sim3292-layer.json").read_bytes())
    wkt = layer["extent"]["spatialReference"]["wkt"]
    crs = CRS.from_wkt(wkt)
    assert crs.ellipsoid.semi_major_metre == 3396190 and crs.prime_meridian.longitude == 0
    assert "Robinson_clon0_Mars_2000_Sphere" == crs.name
    files = sorted(SOURCE.glob("sim3292-[0-9]*.json"))
    features = []
    for file in files:
        document = json.loads(file.read_bytes())
        assert document["spatialReference"]["wkt"] == wkt
        features.extend(document["features"])
    assert len(features) == len({f["attributes"]["OBJECTID"] for f in features}) == 1311
    x, y = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform(longitude, latitude, errcheck=True)

    shapes, attributes = [], []
    repaired = 0
    for feature in features:
        # ArcGIS polygons use clockwise exterior rings and counterclockwise holes.
        shells, holes = [], []
        for ring in feature["geometry"]["rings"]:
            p = Polygon(ring)
            (holes if p.exterior.is_ccw else shells).append(p)
        grouped = [[] for _ in shells]
        for hole in holes:
            containers = [i for i, shell in enumerate(shells) if shell.covers(hole.representative_point())]
            if not containers:
                raise ValueError(f"Unassigned geology hole in {feature['attributes']['OBJECTID']}")
            grouped[min(containers, key=lambda i: shells[i].area)].append(hole.exterior.coords)
        for shell, nested in zip(shells, grouped, strict=True):
            shape = Polygon(shell.exterior.coords, nested)
            if not shape.is_valid:
                repaired += 1
                shape = make_valid(shape)
            shapes.append(shape)
            attributes.append(feature["attributes"])

    result = [[] for _ in longitude]
    for cell, shape in STRtree(shapes).query(points(x, y), predicate="covered_by").T:
        result[cell].append(attributes[shape])
    for i, matches in enumerate(result):
        result[i] = sorted({a["OBJECTID"]: a for a in matches}.values(), key=lambda a: a["OBJECTID"])
    return result, files, repaired


def thermal(longitude, latitude):
    root = SOURCE / "global_ti_night_2007"
    msk = SOURCE / "global_ti_msk_night_2007"
    files = [p.with_suffix(suffix) for p in (root, msk) for suffix in (".lbl", ".img")]
    for label, bits in ((files[0], 16), (files[2], 8)):
        data = dict((key.strip(), value.strip()) for line in label.read_text().splitlines()
                    if "=" in line for key, value in [line.split("=", 1)])
        for k, v in {"SAMPLE_BITS": str(bits), "LINES": "3600", "LINE_SAMPLES": "7200",
                     "TARGET_NAME": '"MARS"', "SAMPLE_TYPE": "MSB_INTEGER",
                     "POSITIVE_LONGITUDE_DIRECTION": '"EAST"', "MAP_RESOLUTION": "20.0 <pix/deg>",
                     "LINE_PROJECTION_OFFSET": "1800.5", "SAMPLE_PROJECTION_OFFSET": "3600.5",
                     "COORDINATE_SYSTEM_NAME": '"PLANETOCENTRIC"'}.items():
            assert data[k] == v, (label, k)
    shape = (3600, 7200)
    assert files[1].stat().st_size == 51840000 and files[3].stat().st_size == 25920000
    grid = np.memmap(files[1], mode="r", dtype=">i2", shape=shape)
    mask = np.memmap(files[3], mode="r", dtype="i1", shape=shape)
    assert set(np.unique(mask)) == {0, 1}
    row = np.floor((90 - latitude) * 20).astype(int)
    col = np.floor((180 + longitude) * 20).astype(int)
    assert np.all((0 <= row) & (row < 3600) & (0 <= col) & (col < 7200))
    return grid[row, col], mask[row, col], files


def spectral(longitude, latitude):
    path = SOURCE / "crism.zip"
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        def member(ext):
            return archive.read(next(name for name in archive.namelist() if name.endswith("." + ext)))
        prj = CRS.from_wkt(member("prj").decode())
        metadata = member("shp.xml").decode()
        assert prj.ellipsoid.semi_major_metre == 3396190 and prj.prime_meridian.longitude == 0
        assert "All latitudes are planetocentric" in metadata and "positive east, -180 to 180" in metadata
        records = shapefile.Reader(**{ext: BytesIO(member(ext)) for ext in ("shp", "shx", "dbf")})
        shapes, ids = [], []
        rejected = 0
        for item in records.iterShapeRecords():
            props = item.record.as_dict()
            geometry = shape(item.shape.__geo_interface__)
            if (not geometry.is_valid or geometry.is_empty or geometry.bounds[0] < -180
                    or geometry.bounds[2] > 180 or any(part.bounds[2] - part.bounds[0] > 180
                    for part in getattr(geometry, "geoms", (geometry,)))):
                rejected += 1
                continue
            shapes.append(geometry)
            ids.append(props["ProductLid"].strip() + "::" + props["ProdVer"].strip())
        assert len(records) == len(shapes) + rejected == 10495
    matches = [set() for _ in longitude]
    for cell, footprint in STRtree(shapes).query(points(longitude, latitude), predicate="covered_by").T:
        matches[cell].add(ids[footprint])
    return matches, path, rejected


def main():
    with sqlite3.connect(f"file:{ROOT / 'map/cells.sqlite'}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT nested_index, longitude_deg_east, latitude_deg_planetocentric "
                          "FROM cells ORDER BY nested_index").fetchall()
    assert len(rows) == 196608 and all(row[0] == i for i, row in enumerate(rows))
    angles = np.asarray(rows)[:, 1:]
    lon, lat = (angles[:, 0] + 180) % 360 - 180, angles[:, 1]
    geologic, geology_files, repaired = geology(lon, lat)
    print(f"Geology mapped {sum(bool(x) for x in geologic):,} cell centroids", flush=True)
    ti, mask, thermal_files = thermal(lon, lat)
    spectra, crism_file, crism_rejected = spectral(lon, lat)
    stats = Counter()
    OUTPUT.mkdir(exist_ok=True)
    target = OUTPUT / "cell-science.ndjson.gz"
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
        for i, (matches, value, verified, crism_ids) in enumerate(zip(geologic, ti, mask, spectra, strict=True)):
            status = "archive_noninterpolated" if verified else "archive_interpolated"
            if value <= 0:
                status = "no_positive_sample"
            stats[status] += 1
            stats["geology_centroids_matched"] += bool(matches)
            stats["geology_centroids_multiple_matches"] += len(matches) > 1
            stats["crism_centroids_matched"] += bool(crism_ids)
            record = {
                "cell_id": f"HPX128:{i}",
                "geologic_units": [{"feature_id": a["OBJECTID"], "code": a["Unit"],
                                    "name": a["UnitDesc"], "group": a["UnitGroup"]} for a in matches],
                "crism_mtrdr_product_ids": sorted(crism_ids),
                "tes_night_thermal_inertia": int(value) if value > 0 else None,
                "tes_night_sample_status": status,
            }
            stream.write((json.dumps(record, separators=(",", ":")) + "\n").encode())
    manifest = {
        "cell_count": len(rows), "coverage": dict(stats), "geology_feature_count": 1311,
        "geology_repaired_projected_parts": repaired,
        "crism_catalogue_records": 10495,
        "crism_rejected_footprints": crism_rejected,
        "crism_method": "Centroid containment in the published ODE c0a shapefile. Planar longitude/latitude containment for catalogue discovery only.",
        "source_urls": {"geology": GEOLOGY, "tes_night": TES, "crism": "https://ode.rsl.wustl.edu/mars/datafile/derived_products/coverageshapefiles/mars/mro/crism/mtrdr/mars_mro_crism_mtrdr_c0a.zip"},
        "geology_method": "Centroid covered by USGS SIM 3292 geometry in native Mars Robinson. Service generalization tolerance 100 m. Map scale 1:20,000,000.",
        "tes_method": "Containing native 20 ppd nighttime TES raster pixel, unit J m^-2 K^-1 s^-1/2. PDS interpolation mask preserved.",
        "source_files_sha256": {f.name: digest(f) for f in geology_files + thermal_files + [SOURCE / "sim3292-layer.json", SOURCE / "datainfo.txt", crism_file]},
        "output_sha256": digest(target),
        "limitations": ["Centroid samples only. No full-cell area fractions or change to documentation scoring.",
                        "TES thermal inertia describes surface thermophysical properties. No time-specific temperature or weather is inferred."],
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
