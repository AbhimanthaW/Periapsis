"""Verify the cell export and its catalogue receipts without archive access."""
from collections import Counter
import gzip
from hashlib import file_digest
import json
from pathlib import Path
import sqlite3

from workspace import build_workspace

ROOT = build_workspace()
EXPORT = ROOT / "map"

def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()

def load(path):
    return json.loads(path.read_text())

def main():
    manifest = load(EXPORT / "manifest.json")
    for name, receipt in manifest["files"].items():
        path = EXPORT / name
        assert (path.stat().st_size, digest(path)) == (receipt["bytes"], receipt["sha256"]), name
    for name, snapshot in load(EXPORT / "catalogue-snapshots.json").items():
        for page, expected in snapshot["pages_sha256"].items():
            assert digest(ROOT / "catalogues" / name / page) == expected, (name, page)

    package = load(EXPORT / "evidence-package.json")
    products = {product["id"] for product in package["products"]}
    assert len(products) == len(package["products"])
    observed, usable, tiers = Counter(), Counter(), Counter()
    names, zero_counts, total = set(), 0, 0
    columns = ("nested_index", "cell_id", "longitude_deg_east", "latitude_deg_planetocentric",
               "area_km2", "mola_elevation_m", "mola_observation_count")
    with sqlite3.connect(f"file:{EXPORT / 'cells.sqlite'}?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        rows = db.execute("SELECT " + ", ".join(columns) + ", metadata_json FROM cells ORDER BY nested_index")
        with gzip.open(EXPORT / "cells.ndjson.gz", "rt") as stream:
            for index, (row, line) in enumerate(zip(rows, stream, strict=True)):
                record = json.loads(line)
                assert record["nested_index"] == index
                assert record["cell_id"] == f"HPX128:{index}"
                assert tuple(record.pop(column) for column in columns) == row[:-1]
                assert json.loads(row[-1]) == record
                for name, metric in record["modalities"].items():
                    assert products.issuperset(metric["product_ids"])
                    assert 0 <= metric["usable_fraction"] <= metric["observed_fraction"] + 1e-12
                    for bounds in (metric["observed_bounds"], metric["evidence_bounds"]):
                        assert 0 <= bounds["lower"] <= bounds["upper"] <= 1
                    observed[name] += metric["observed_fraction"] > 0
                    usable[name] += metric["usable_fraction"] > 0
                for item in record["named_feature_anchors"]:
                    assert item["id"] not in names
                    names.add(item["id"])
                zero_counts += row[6] == 0
                tiers[record["terrain"]["tier"]] += 1
                total += 1
    assert total == manifest["cell_count"] == 196608
    assert len(names) == manifest["named_feature_anchor_count"]
    assert zero_counts == manifest["mola_zero_observation_samples"]
    assert dict(observed) == manifest["cells_with_catalogued_coverage"]
    assert dict(usable) == manifest["cells_with_verified_usable_support"]
    assert dict(tiers) == manifest["terrain_tiers"]
    print(f"Verified {total:,} rows in both formats, {len(products):,} product references, and {len(names)} anchors.")

if __name__ == "__main__":
    main()
