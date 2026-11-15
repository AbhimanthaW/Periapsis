"""Verify pinned cell-map releases before any ranking build reads them."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

N = 196_608
SHA256 = {
    "cells-enriched.ndjson.gz": "d5c0d6a7889cf5e1a28d026505271c5ccda8b7f89ca0aaacf6f62dfc2bd994df",
    "cell-ranking.ndjson.gz": "ca117ed3e8e2ad35fe3425c52567b082e5d6c9304f10a1c2120e277fc55f8ef2",
    "ranking-features.json.gz": "4dbea620c5f5398f39e32386f6827f9a13d4998df5c7248f1b32ac2e215e6491",
    "cells-enriched-sourced.ndjson.gz": "55bd23ed794940c352d59b7a6c12409180ae245676366e02334a6accd93ec1fb",
    "sourced-catalogue-manifest.json": "dffdd31c9ef80c814e5634f632c8308d7afbd2af3744de385b5ecbf8c4f927b9",
}


def verify_digest(path: Path, expected: str) -> None:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"{path.name}: SHA-256 mismatch: expected {expected}, actual {digest}")


def rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            row = json.loads(line)
            if row["cell_id"] != f"HPX128:{index}":
                raise ValueError(f"{path.name}: wrong cell ID at row {index}")
            if "nested_index" in row and row["nested_index"] != index:
                raise ValueError(f"{path.name}: wrong nested index at row {index}")
            yield row


def inspect(directory: Path) -> dict:
    for name, digest in SHA256.items():
        verify_digest(directory / name, digest)
    manifest = json.loads((directory / "sourced-catalogue-manifest.json").read_text())
    if manifest["baseline_enriched_sha256"] != SHA256["cells-enriched.ndjson.gz"]:
        raise ValueError("sourced manifest points to a different baseline")
    for name, receipt in manifest["files"].items():
        if receipt["sha256"] != SHA256.get(name):
            raise ValueError(f"sourced manifest points to a different {name}")

    counts = Counter()
    groups = Counter()
    unit_codes = set()
    for row in rows(directory / "cells-enriched.ndjson.gz"):
        counts["rows"] += 1
        science = row["science_at_centroid"]
        extra = row["additional_context_at_centroid"]
        units = science["geologic_units"]
        unit_codes.update(unit["code"] for unit in units)
        # The published group totals classify a cell by its first (primary) unit.
        # Four boundary cells contain two units; retain that fact separately.
        if units:
            groups[units[0]["group"]] += 1
        if not units:
            counts["no_unit"] += 1
        if len(units) == 2:
            counts["two_units"] += 1
        status = science["tes_night_sample_status"]
        measured = status == "archive_noninterpolated"
        counts[f"thermal_{status}"] += 1
        swim = extra["swim_ice_consistency"]
        ice_covered = any(value is not None for value in swim.values()) if swim else False
        counts["swim_covered"] += ice_covered
        counts["sparse"] += not units or (not measured and not ice_covered)
        counts["crism_cells"] += bool(science["crism_mtrdr_product_ids"])
        counts["hirise_cells"] += bool(extra["hirise_projected_centroid_records"])
        counts["dtm_cells"] += bool(extra["hirise_dtm_centroid_product_ids"])
        counts["targeted_product_cells"] += bool(
            science["crism_mtrdr_product_ids"] or extra["hirise_projected_centroid_records"]
            or extra["hirise_dtm_centroid_product_ids"]
        )
        counts["missing_elevation"] += row["mola_elevation_m"] is None
        counts["missing_albedo"] += extra["tes_lambert_albedo"] is None
    if counts["rows"] != N:
        raise ValueError(f"baseline rows: expected {N}, actual {counts['rows']}")

    for row in rows(directory / "cell-ranking.ndjson.gz"):
        counts["ranking_rows"] += 1
        counts["catalogue_cells"] += bool(row["evidence"])
    if counts["ranking_rows"] != N:
        raise ValueError(f"ranking rows: expected {N}, actual {counts['ranking_rows']}")
    for _ in rows(directory / "cells-enriched-sourced.ndjson.gz"):
        counts["sourced_rows"] += 1
    if counts["sourced_rows"] != N:
        raise ValueError(f"sourced rows: expected {N}, actual {counts['sourced_rows']}")

    with gzip.open(directory / "ranking-features.json.gz", "rt", encoding="utf-8") as stream:
        features = json.load(stream)
    counts["distinct_unit_codes"] = len(unit_codes)
    return {"counts": dict(sorted(counts.items())), "groups": dict(sorted(groups.items())),
            "feature_counts": {key: len(value) for key, value in sorted(features.items())}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing the five pinned release assets")
    args = parser.parse_args()
    print(json.dumps(inspect(args.directory), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
