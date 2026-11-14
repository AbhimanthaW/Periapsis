"""Verify science row identities, coverage counters and source receipts."""
from collections import Counter
import gzip
from hashlib import file_digest
import json
from pathlib import Path

from workspace import build_workspace

root = build_workspace()
def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()

manifest = json.loads((root / "science/manifest.json").read_bytes())
for name, expected in manifest["source_files_sha256"].items():
    assert digest(root / "science-sources" / name) == expected
target = root / "science/cell-science.ndjson.gz"
assert digest(target) == manifest["output_sha256"]
coverage = Counter()
count = 0
with gzip.open(target, "rt") as stream:
    for i, line in enumerate(stream):
        row = json.loads(line)
        assert row["cell_id"] == f"HPX128:{i}"
        coverage["geology_centroids_matched"] += bool(row["geologic_units"])
        coverage["geology_centroids_multiple_matches"] += len(row["geologic_units"]) > 1
        status, value = row["tes_night_sample_status"], row["tes_night_thermal_inertia"]
        assert (value is None) == (status == "no_positive_sample")
        coverage[status] += 1
        if "crism_mtrdr_product_ids" in row:
            coverage["crism_centroids_matched"] += bool(row["crism_mtrdr_product_ids"])
            assert row["crism_mtrdr_product_ids"] == sorted(set(row["crism_mtrdr_product_ids"]))
        count += 1
assert count == manifest["cell_count"] == 196608
assert coverage == manifest["coverage"]
print(dict(coverage))
