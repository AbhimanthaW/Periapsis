"""Adapt the validated atlas and captured catalogue footprints to marsdoc."""
import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
import multiprocessing as mp
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

import numpy as np
import rasterio
from marsdoc import DocumentationEngine, Grid, Package

from workspace import build_workspace

ROOT = build_workspace()
ATLAS = ROOT / "registry/mars-mola-meg004/0.1.0-rc.1/atlas"
COLLECTIONS = {
    "themis": ("thermal", "infrared_mosaic", "Mars Odyssey", "THEMIS", "image"),
    "hirise-dtm": ("stereo_topography", "stereo_dtm", "Mars Reconnaissance Orbiter", "HiRISE", "dtm"),
    "arcadia-ctx": ("stereo_topography", "stereo_dtm", "Mars Reconnaissance Orbiter", "CTX", "dtm"),
    "jezero-ctx": ("stereo_topography", "stereo_dtm", "Mars Reconnaissance Orbiter", "CTX", "dtm"),
    "arcadia-hirise": ("fine_imagery", "optical_image", "Mars Reconnaissance Orbiter", "HiRISE", "image"),
    "jezero-hirise": ("fine_imagery", "optical_image", "Mars Reconnaissance Orbiter", "HiRISE", "image"),
}
NSIDE = 128


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def compact(data):
    return json.dumps(data, separators=(",", ":"), allow_nan=False)


def evidence(repo, atlas_manifest):
    arcadia = load(repo / "pipeline/evidence/arcadia-planitia/evidence.json")
    jezero = load(repo / "evidence/jezero/jezero-evidence.json")
    mola = arcadia["products"][0]
    atlas_source = atlas_manifest["source"]
    assert mola["id"] == atlas_source["asset_id"] and mola["version"] == atlas_source["version"]
    assert atlas_manifest["coverage"]["valid_elevation_cells"] == 720 * 1440
    mola.update(
        observation_extent_complete=True,
        support_extent_complete=True,
        provenance=[
            f"MOLA archive bundle SHA-256: {atlas_source['bundle_sha256']}",
            f"Verified atlas manifest SHA-256: {digest(ATLAS / 'atlas-manifest.json')}",
            f"Verified elevation GeoTIFF SHA-256: {digest(ATLAS / 'elevation.tif')}",
            f"Verified observation counts GeoTIFF SHA-256: {digest(ATLAS / 'observation-counts.tif')}",
        ],
        limitations=[
            "Whole-planet gridded elevation context at 0.25-degree spacing, including interpolation.",
            "The observation-count layer measures direct sampling separately.",
            "Native spacing in metres is nominal at the equator. Effective feature scale is unset.",
            atlas_source["vertical_reference"],
        ],
    )
    data = {
        "schema_version": 1, "package_id": "mars-healpix-128", "version": "0.1.0",
        "datasets": arcadia["datasets"] + jezero["datasets"],
        "products": [mola] + jezero["products"],
        "footprints": [{
            "id": "mola-meg004-global-grid-support", "product_id": mola["id"],
            "source_url": mola["source_url"], "status": "canonical_verified",
            "coverage_kind": "usable_support", "geometry": {"type": "Global"},
            "transform": "Verified 720×1440 planetocentric east-positive atlas. Longitude reindexed without resampling.",
            "note": "Gridded elevation applicability, including interpolated locations.",
        }] + jezero["footprints"],
        "inventories": [],
    }
    reports = {}
    rejected = []
    collection_ids = set()
    seen = set()
    for name, (modality, product_class, mission, instrument, asset) in COLLECTIONS.items():
        directory = ROOT / "catalogues" / name
        snapshot = directory / "snapshot.json"
        if not snapshot.is_file():
            reports[name] = {"status": "capture_unavailable"}
            continue
        report = load(snapshot)
        collection = report["collection"]
        archive = f"https://stac.astrogeology.usgs.gov/api/collections/{collection}"
        if collection not in collection_ids:
            data["datasets"].append(dict(id=collection, mission=mission, instrument=instrument,
                modality=modality, product_class=product_class, archive_url=archive,
                version="snapshot-2026-11-14", catalogue_status="incomplete"))
            collection_ids.add(collection)
        report["pages_sha256"] = {}
        for page in sorted(directory.glob("[0-9][0-9][0-9].json")):
            page_hash = digest(page)
            report["pages_sha256"][page.name] = page_hash
            for item in load(page)["features"]:
                key = f"{collection}:{item['id']}"
                if key in seen:
                    continue
                seen.add(key)
                props = item["properties"]
                if props.get("ssys:targets") != ["Mars"] or not props.get("proj:wkt2"):
                    rejected.append(dict(code="missing_explicit_mars_crs", record_id=key,
                                         source_url=report["request_url"], page_sha256=page_hash))
                    continue
                # The public STAC geometry describes the catalogue outline. Its
                # data mask and measurement applicability have not been verified.
                source_url = item["assets"][asset]["href"]
                data["products"].append(dict(
                    id=key, dataset_id=collection, version=props.get("updated") or "snapshot-2026-11-14",
                    source_url=source_url, source_crs=dict(body="Mars", frame="STAC Mars source",
                    definition=props["proj:wkt2"]), processing_level="published_catalogue_product",
                    readiness="unknown", variables=("elevation",) if asset == "dtm" else (),
                    native_spacing_m=props.get("gsd"), observation_extent_complete=True,
                    provenance=[f"USGS STAC {name}/{page.name} SHA-256 {page_hash}", f"STAC item {item['id']}"],
                    limitations=["Catalogue outline only. Valid pixels, quality and effective scale are unverified."],
                ))
                data["footprints"].append(dict(
                    id=key, product_id=key, source_url=report["request_url"], coverage_kind="observation",
                    status="canonical_verified" if item["geometry"] else "unavailable",
                    geometry=item["geometry"], transform="USGS STAC Mars east-longitude/planetocentric geographic outline.",
                ))
        reports[name] = report
    return Package.model_validate(data), reports, rejected


def setup_worker(package_path):
    global ENGINE
    ENGINE = DocumentationEngine(Package.model_validate_json(Path(package_path).read_bytes()), nside=NSIDE)


def summarize_block(bounds):
    results = []
    for index in range(*bounds):
        result = ENGINE.summarize(ENGINE.grid.identifier(index))
        modalities = {}
        for item in result.modalities:
            modalities[item.modality] = {
                "status": item.coverage_state,
                "observed_fraction": item.observed_fraction,
                "observed_bounds": item.observed_bounds.model_dump(),
                "usable_fraction": item.usable_fraction,
                "evidence_bounds": item.evidence_bounds.model_dump(),
                "product_ids": item.product_ids,
            }
        results.append((result.terrain.model_dump(), result.science_environment.model_dump(),
                        modalities, result.boundary_area_relative_error))
    return results


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("repo", type=Path)
    args.add_argument("output", type=Path)
    args.add_argument("--workers", type=int, default=6)
    spec = args.parse_args()
    if spec.output.exists():
        raise ValueError("Choose a new output directory")
    repo = spec.repo.resolve()
    atlas = load(ATLAS / "atlas-manifest.json")
    package, reports, rejected = evidence(repo, atlas)
    preflight = DocumentationEngine(package)
    invalid = set()
    for entry in preflight.catalogue.entries.values():
        if entry.issues:
            invalid.add(entry.product.id)
            rejected.extend(issue.model_dump(mode="json") for issue in entry.issues)
    if any(p.id in invalid for p in package.products[:2]):
        raise ValueError("Required verified source rejected")
    # Invalid metadata remains in the quarantine log and catalogues remain open.
    package = package.model_copy(update={
        "products": tuple(p for p in package.products if p.id not in invalid),
        "footprints": tuple(f for f in package.footprints if f.product_id not in invalid),
    })
    engine = DocumentationEngine(package)
    print(f"Validated {len(package.products)} products; quarantined {len(rejected)} footprints", flush=True)
    grid = Grid(NSIDE)
    indices = np.arange(grid.count)
    points = grid.centroids(indices)
    np.testing.assert_array_equal(grid.indices(points), indices)
    names = defaultdict(list)
    for region in load(ATLAS / "region-index.json")["regions"]:
        index = int(grid.indices(region["center_lon_lat_deg"]))
        names[index].append({"id": region["region_id"], "name": region["name"]})

    signed_lon = (points[:, 0] + 180) % 360 - 180
    with rasterio.open(ATLAS / "elevation.tif") as z, rasterio.open(ATLAS / "observation-counts.tif") as n:
        if z.shape != (720, 1440) or z.transform != n.transform or z.crs != n.crs:
            raise ValueError("Unexpected verified atlas grid")
        cols, rows = ~z.transform * (signed_lon, points[:, 1])
        rows, cols = np.floor(rows).astype(int), np.floor(cols).astype(int)
        elevation = z.read(1, masked=True)[rows, cols]
        counts = n.read(1, masked=True)[rows, cols]
        if np.ma.getmaskarray(elevation).any() or np.ma.getmaskarray(counts).any():
            raise ValueError("Missing atlas sample under the global support assertion")
        if np.any(counts < 0):
            raise ValueError("Unexpected negative MOLA observation count")

    with tempfile.TemporaryDirectory(prefix=".cell-build-", dir=spec.output.parent) as temporary:
        stage = Path(temporary) / "export"
        stage.mkdir()
        sidecar = stage / "evidence-package.json"
        sidecar.write_text(package.model_dump_json(indent=2) + "\n")
        write(stage / "catalogue-snapshots.json", reports)
        write(stage / "quarantined-footprints.json", rejected)
        product_counts = Counter(item.dataset_id for item in package.products)
        totals = Counter()
        observed = Counter()
        usable = Counter()
        output = stage / "cells.sqlite"
        blocks = [(i, min(i + 512, grid.count)) for i in range(0, grid.count, 512)]
        with (sqlite3.connect(output) as db, (stage / "cells.ndjson.gz").open("wb") as raw,
              gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream,
              mp.get_context("spawn").Pool(spec.workers, setup_worker, (str(sidecar),)) as pool):
            db.execute("""CREATE TABLE cells (
                nested_index INTEGER PRIMARY KEY, cell_id TEXT UNIQUE NOT NULL, longitude_deg_east REAL NOT NULL,
                latitude_deg_planetocentric REAL NOT NULL, area_km2 REAL NOT NULL,
                mola_elevation_m INTEGER NOT NULL, mola_observation_count INTEGER NOT NULL, metadata_json TEXT NOT NULL
            )""")
            for block, results in zip(blocks, pool.imap(summarize_block, blocks), strict=True):
                db_rows = []
                for i, (terrain, science, modalities, error) in enumerate(results, start=block[0]):
                    for name, metric in modalities.items():
                        observed[name] += metric["observed_fraction"] > 0
                        usable[name] += metric["usable_fraction"] > 0
                    totals[terrain["tier"]] += 1
                    metadata = dict(
                        terrain=terrain, science_environment=science, modalities=modalities,
                        boundary_area_relative_error=error, named_feature_anchors=names.get(i, []),
                        mola_native_row=int(rows[i]), mola_native_col_signed_grid=int(cols[i]),
                    )
                    record = dict(cell_id=grid.identifier(i), nested_index=i,
                                  longitude_deg_east=float(points[i, 0]), latitude_deg_planetocentric=float(points[i, 1]),
                                  area_km2=grid.area_km2, mola_elevation_m=int(elevation[i]),
                                  mola_observation_count=int(counts[i]), **metadata)
                    stream.write((compact(record) + "\n").encode())
                    db_rows.append((i, record["cell_id"], *map(float, points[i]), grid.area_km2,
                                    int(elevation[i]), int(counts[i]), compact(metadata)))
                db.executemany("INSERT INTO cells VALUES (?, ?, ?, ?, ?, ?, ?, ?)", db_rows)
                if block[1] % 16384 == 0:
                    print(f"{block[1]:,}/{grid.count:,} cells", flush=True)
            db.commit()
            assert db.execute("SELECT count(*), min(nested_index), max(nested_index) FROM cells").fetchone() == (
                grid.count, 0, grid.count - 1)
            assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            for point in [(77.44, 18.45), (-171.85, 49.02), (359.98, 87.4), (0, -89.9)]:
                index = int(grid.indices(point))
                row = db.execute("SELECT metadata_json FROM cells WHERE nested_index = ?", (index,)).fetchone()
                expected = engine.summarize(grid.identifier(index))
                assert json.loads(row[0])["terrain"] == expected.terrain.model_dump()
            db.execute("CREATE INDEX cells_coordinates ON cells(latitude_deg_planetocentric, longitude_deg_east)")
        assert sum(totals.values()) == grid.count and usable["baseline_topography"] == grid.count
        assert 0 < usable["stereo_topography"] < grid.count
        assert sum(map(len, names.values())) == len(load(ATLAS / "region-index.json")["regions"])
        write(stage / "manifest.json", {
            "schema_version": 1, "dataset_version": package.version, "cell_count": grid.count, "nside": NSIDE,
            "ordering": "NESTED", "frame": "Mars planetocentric, east-positive [0, 360)",
            "git_commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
            "method_version": "marsdoc-spherical-v1", "policy_sha256": engine.policy_sha256,
            "scoring_policy": engine.policy.model_dump(),
            "atlas_manifest_sha256": digest(ATLAS / "atlas-manifest.json"),
            "products_by_dataset": dict(product_counts), "quarantined_footprints": len(rejected),
            "cells_with_catalogued_coverage": dict(observed), "cells_with_verified_usable_support": dict(usable),
            "terrain_tiers": dict(totals), "mola_zero_observation_samples": int(np.count_nonzero(counts == 0)),
            "named_feature_anchor_count": sum(map(len, names.values())),
            "limitations": [
                "MOLA values are centroid samples from the containing native raster pixel, not HEALPix area statistics.",
                "MOLA covers all cells as gridded context, including interpolated locations. Zero observations is a valid count.",
                "STAC footprints are catalogue outlines, with no independently verified masks or scale.",
                "Catalogue completeness remains open by modality. Unsearched areas are unknown.",
                "Named feature associations are anchor points only. This build supplies no region boundaries or narratives.",
            ],
            "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(stage.iterdir())},
        })
        shutil.move(stage, spec.output)


if __name__ == "__main__":
    main()
