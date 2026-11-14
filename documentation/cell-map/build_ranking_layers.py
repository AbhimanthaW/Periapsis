"""Join pinned source catalogues to the existing HEALPix export."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
import gzip
from hashlib import file_digest
from io import BytesIO, StringIO
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

from marsdoc import Grid
from marsdoc.grid import RADIUS_M
import numpy as np
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from shapely import STRtree, box, points

from workspace import build_workspace

LOCK = Path(__file__).with_name("receipts") / "ranking-sources.json"
GRID = Grid(128)
SUBGRID = Grid(1024)
CHILDREN = (SUBGRID.nside // GRID.nside) ** 2
SPHERE = Geod(a=RADIUS_M, f=0)
GAZETTEER_EXTENT_TYPES = {"CH", "CM", "FO", "LB", "UN"}
POINT_LAYERS = ("paleolakes", "chlorides", "gazetteer", "dunes", "cave_candidates", "marsquakes")


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify(path, receipt):
    if path.stat().st_size != receipt["bytes"] or digest(path) != receipt["sha256"]:
        raise ValueError(f"source snapshot does not match lock: {path.name}")


def verify_sources(directory, lock, fetch=False):
    directory.mkdir(parents=True, exist_ok=True)
    for dataset in lock["datasets"].values():
        for name, receipt in dataset["files"].items():
            path = directory / name
            if fetch and not path.exists():
                temp = path.with_suffix(path.suffix + ".part")
                try:
                    request = Request(receipt["url"], headers={"User-Agent": "ReturnWindow/1.0 (archive build)"})
                    with urlopen(request, timeout=120) as response:
                        payload = response.read(receipt["bytes"] + 1)
                    temp.write_bytes(payload)
                    verify(temp, receipt)
                    temp.replace(path)
                finally:
                    temp.unlink(missing_ok=True)
            verify(path, receipt)


def csv_rows(data, delimiter=","):
    return csv.DictReader(StringIO(data.decode("utf-8-sig"), newline=""), delimiter=delimiter)


def point(identifier, lon, lat, **fields):
    lon, lat = float(lon), float(lat)
    if not identifier or not (-180 <= lon <= 360 and -90 <= lat <= 90):
        raise ValueError(f"invalid source point {identifier!r}: {(lon, lat)}")
    return {"id": str(identifier), "lon_deg_east": lon % 360,
            "lat_deg_planetocentric": lat, **fields}


def lake_points(root):
    with ZipFile(root / "lakes.zip") as archive:
        for row in csv_rows(archive.read("Goudge_et_al_2016_Geology_CBL_OBL_Catalogue.csv")):
            basin = row["Basin Type"]
            if basin not in {"OBL", "CBL"}:
                raise ValueError(f"unrecognized paleolake type: {basin}")
            yield point(f"{basin}-{row['Basin #']}", row["Lon. (E)"], row["Lat. (N)"], basin_type=basin)


def chloride_points(root):
    for row in csv_rows((root / "chlorides.csv").read_bytes()):
        yield point(row["FID_OsterlooEtAl2010Set"], row["Lon2"], row["Lat2"], label=row["Label"])


def cave_points(root):
    with ZipFile(root / "caves.zip") as archive:
        name = "miscellaneous/Mars_Cave_Catalog_shapefile.csv"
        for row in csv_rows(archive.read(name)):
            yield point(row["Label:string"], row["longitude"], row["latitude"],
                        candidate_type=row["TypeCode:string"], priority=row["Priority:string"])


def quake_points(root):
    for row in csv_rows((root / "marsquakes.txt").read_bytes(), delimiter="|"):
        yield point(row["EventID"], row["Longitude"], row["Latitude"],
                    event_type=row["EventType"], utc=row["Time"],
                    magnitude=float(row["Magnitude"]) if row["Magnitude"] else None,
                    magnitude_type=row["MagType"] or None, contributor_id=row["ContributorID"])


def dune_points(root):
    from openpyxl import load_workbook

    with ZipFile(root / "dune.zip") as archive:
        for region in ("Equatorial", "SouthPolar"):
            name = f"ofr20181164_dunedatabase/MGD3_{region}_DuneDatabase.xlsx"
            workbook = load_workbook(BytesIO(archive.read(name)), read_only=True, data_only=True)
            try:
                rows = workbook["Stability Index"].values
                header = next(rows)
                columns = [header.index(key) for key in ("Dune_ID", "Longitude (°)", "Latitude (°)")]
                for row_number, row in enumerate(rows, start=2):
                    identifier, lon, lat = (row[column] for column in columns)
                    if identifier is None and lon is None and lat is None:
                        continue
                    if identifier is None:
                        raise ValueError(f"missing dune ID in {region} row {row_number}")
                    yield point(f"{region}:{row_number}", lon, lat, worksheet=region, dune_id=identifier)
            finally:
                workbook.close()


def named_points(root):
    import shapefile

    with ZipFile(root / "gazetteer.zip") as archive:
        with shapefile.Reader(dbf=BytesIO(archive.read("MARS_nomenclature_center_pts.dbf"))) as reader:
            seen = {}
            for row in reader.iterRecords():
                identifier = row["link"].rsplit("/", 1)[-1]
                bounds = [row[key] for key in ("min_lon", "min_lat", "max_lon", "max_lat")]
                feature = point(identifier, row["center_lon"], row["center_lat"],
                                name=row["name"], feature_type=row["type"], type_code=row["code"],
                                approval=row["approval"], diameter_km=row["diameter"],
                                published_bounds=bounds)
                if identifier in seen:
                    if feature != seen[identifier]:
                        raise ValueError(f"conflicting Gazetteer records for {identifier}")
                    continue
                seen[identifier] = feature
                yield feature


def bounds_boxes(feature):
    west, south, east, north = feature["published_bounds"]
    if any(value is None for value in (west, south, east, north)):
        return []
    span = (east - west) % 360
    offset = (feature["lon_deg_east"] - west) % 360
    if not (0 < span <= 180 and offset <= span + 1e-9
            and -90 <= south <= feature["lat_deg_planetocentric"] <= north <= 90
            and south < north):
        return []
    west %= 360
    east = west + span
    if east <= 360:
        return [box(west, south, east, north)]
    return [box(west, south, 360, north), box(0, south, east - 360, north)]


def add_named_extents(features, cells):
    boxes, identifiers = [], []
    for feature in features:
        if feature["type_code"] not in GAZETTEER_EXTENT_TYPES or feature["approval"] != "Adopted by IAU":
            continue
        parts = bounds_boxes(feature)
        boxes.extend(parts)
        identifiers.extend([feature["id"]] * len(parts))
    tree = STRtree(boxes)
    for start in range(0, SUBGRID.count, 262144):
        ids = np.arange(start, min(start + 262144, SUBGRID.count))
        coordinates = SUBGRID.centroids(ids)
        sample, part = tree.query(points(coordinates), predicate="intersects")
        counts = Counter(zip((sample + start) // CHILDREN, (identifiers[i] for i in part)))
        for (cell, identifier), count in sorted(counts.items()):
            cells[int(cell)].setdefault("gazetteer_approximate_bounds", {})[identifier] = count / CHILDREN
    return len(set(identifiers))


def segment_bins(path, inverse):
    """Bin Mars-sphere lengths of short line segments at their geodesic midpoints."""
    xy = np.asarray(path, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or len(xy) < 2:
        raise ValueError("invalid SIM 3292 line path")
    delta = np.diff(xy, axis=0)
    steps = np.maximum(1, np.ceil(np.linalg.norm(delta, axis=1) / 2000).astype(int))
    section = np.repeat(np.arange(len(steps)), steps)
    starts = np.repeat(np.cumsum(steps) - steps, steps)
    fraction = (np.arange(len(section)) - starts) / steps[section]
    dense = np.vstack((xy[section] + fraction[:, None] * delta[section], xy[-1]))
    lon, lat = inverse.transform(dense[:, 0], dense[:, 1], direction="INVERSE", errcheck=True)
    bearing, _, length = SPHERE.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    mid_lon, mid_lat, _ = SPHERE.fwd(lon[:-1], lat[:-1], bearing, length / 2)
    positive = length > 0
    ids = GRID.indices(np.column_stack((mid_lon[positive], mid_lat[positive])))
    return ids, length[positive]


def structure_lines(root, cells):
    info = json.loads((root / "sim-lines-2-layer.json").read_bytes())
    expected = json.loads((root / "sim-lines-2-count.json").read_bytes())["count"]
    wkt = info["extent"]["spatialReference"]["wkt"]
    native = CRS.from_wkt(wkt)
    if info["name"] != "Global_Structure" or native.ellipsoid.semi_major_metre != 3_396_190:
        raise ValueError("unexpected SIM 3292 layer or Mars CRS")
    inverse = Transformer.from_crs(native.geodetic_crs, native, always_xy=True)
    features = []
    quarantined = []
    seen = set()
    for name in ("sim-lines-2.json", "sim-lines-2-page2.json"):
        page = json.loads((root / name).read_bytes())
        if page["spatialReference"]["wkt"] != wkt or page["geometryType"] != "esriGeometryPolyline":
            raise ValueError("SIM 3292 geometry metadata changed")
        for row in page["features"]:
            attrs = row["attributes"]
            identifier = str(attrs["OBJECTID"])
            if identifier in seen:
                raise ValueError(f"duplicate SIM 3292 feature {identifier}")
            seen.add(identifier)
            lengths = defaultdict(float)
            try:
                for path in row["geometry"]["paths"]:
                    ids, meters = segment_bins(path, inverse)
                    for cell, length in zip(ids, meters, strict=True):
                        lengths[int(cell)] += float(length)
            except ProjError:
                quarantined.append(identifier)
                continue
            if not lengths:
                raise ValueError(f"empty SIM 3292 feature {identifier}")
            for cell, meters in sorted(lengths.items()):
                cells[cell].setdefault("structures", {})[identifier] = round(meters / 1000, 6)
            features.append({"id": identifier, "origin": attrs["Origin"],
                             "interpretation": attrs["Interpretation"], "morphology": attrs["Morphology"],
                             "mapped_length_km": attrs["SphLen_km"]})
    if len(seen) != expected:
        raise ValueError(f"expected {expected} SIM 3292 features, found {len(seen)}")
    return features, quarantined


@contextmanager
def gzip_output(path):
    temp = path.with_suffix(path.suffix + ".part")
    try:
        with temp.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as stream:
            yield stream
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def encode(value):
    return (json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n").encode()


def join_sources(root):
    cells = defaultdict(dict)
    catalogue = {}
    for key, load in zip(POINT_LAYERS, (lake_points, chloride_points, named_points,
                                       dune_points, cave_points, quake_points), strict=True):
        features = sorted(load(root), key=lambda item: item["id"])
        if not features or len({f["id"] for f in features}) != len(features):
            raise ValueError(f"empty catalogue or duplicate IDs: {key}")
        coordinates = [(f["lon_deg_east"], f["lat_deg_planetocentric"]) for f in features]
        for feature, index in zip(features, GRID.indices(coordinates), strict=True):
            cells[int(index)].setdefault(key, []).append(feature["id"])
        catalogue[key] = features
    extents = add_named_extents(catalogue["gazetteer"], cells)
    catalogue["structures"], quarantined = structure_lines(root, cells)
    return cells, catalogue, extents, quarantined


def merge_export(root, output_dir):
    baseline = root / "expansion/cells-enriched.ndjson.gz"
    receipt = json.loads((root / "expansion/enriched-manifest.json").read_bytes())
    if digest(baseline) != receipt["sha256"] or receipt["rows"] != GRID.count:
        raise ValueError("expanded cell export does not match its manifest")
    output = output_dir / "cells-enriched-sourced.ndjson.gz"
    supplement = output_dir / "cell-ranking.ndjson.gz"
    with (gzip.open(baseline, "rt") as base, gzip.open(supplement, "rt") as extra,
          gzip_output(output) as stream):
        count = 0
        for index, (left, right) in enumerate(zip(base, extra, strict=True)):
            original, joined = json.loads(left), json.loads(right)
            expected = GRID.identifier(index)
            if original["cell_id"] != expected or joined["cell_id"] != expected:
                raise ValueError(f"cell streams diverge at {expected}")
            original["sourced_catalogue_context"] = joined["evidence"]
            stream.write(encode(original))
            count += 1
        if count != GRID.count:
            raise ValueError(f"expected {GRID.count} merged cells, found {count}")
    return output, receipt["sha256"]


def build(root, fetch=False, merge=False):
    lock = json.loads(LOCK.read_bytes())
    inputs = root / "ranking-sources"
    verify_sources(inputs, lock, fetch)
    cells, catalogue, extents, quarantined = join_sources(inputs)
    output_dir = root / "ranking"
    output_dir.mkdir(parents=True, exist_ok=True)
    supplement = output_dir / "cell-ranking.ndjson.gz"
    totals = Counter()
    with gzip_output(supplement) as stream:
        for index in range(GRID.count):
            evidence = cells.get(index, {})
            totals.update(evidence.keys())
            stream.write(encode({"cell_id": GRID.identifier(index), "evidence": evidence}))
    features = output_dir / "ranking-features.json.gz"
    with gzip_output(features) as stream:
        stream.write(encode(catalogue))
    files = [supplement, features]
    manifest = {
        "version": "ranking-layers-v1", "rows": GRID.count, "grid": "HPX128 NESTED",
        "source_lock_sha256": digest(LOCK),
        "sources": lock["datasets"],
        "source_features": {key: len(records) for key, records in catalogue.items()},
        "gazetteer_features_with_eligible_bounds": extents,
        "gazetteer_extent_type_codes": sorted(GAZETTEER_EXTENT_TYPES),
        "quarantined_structure_ids": quarantined,
        "quarantined_structure_reason": "At least one line sample outside the published Mars Robinson domain.",
        "cells_with_evidence": dict(totals),
        "cells_with_any_evidence": len(cells),
        "missingness": "Omitted layer keys mean no imported evidence in this cell. Catalogue absence and survey coverage are unknown.",
    }
    if merge:
        merged, baseline_sha256 = merge_export(root, output_dir)
        files.append(merged)
        manifest["baseline_enriched_sha256"] = baseline_sha256
    manifest["files"] = {path.name: {"bytes": path.stat().st_size, "sha256": digest(path)} for path in files}
    (output_dir / "manifest.json").write_bytes(encode(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="download missing locked source snapshots")
    parser.add_argument("--merge", action="store_true", help="also join the existing verified enriched export")
    args = parser.parse_args()
    result = build(build_workspace(), fetch=args.fetch, merge=args.merge)
    print(json.dumps({key: result[key] for key in ("rows", "source_features", "cells_with_evidence",
                                                  "cells_with_any_evidence", "files")}, indent=2))
