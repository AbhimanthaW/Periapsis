"""Validate the expansion and write a single joined HEALPix export."""
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import file_digest
import json
from pathlib import Path

from workspace import build_workspace

root = build_workspace()

def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()

base, science, expansion = [json.loads((root / d / "manifest.json").read_bytes())
                            for d in ("map", "science", "expansion")]
paths = [root / name for name in ("map/cells.ndjson.gz", "science/cell-science.ndjson.gz",
                                   "expansion/cell-expansion.ndjson.gz")]
assert [digest(p) for p in paths] == [
    base["files"]["cells.ndjson.gz"]["sha256"], science["output_sha256"], expansion["output_sha256"]]
for source in expansion["sources"].values():
    for filename, receipt in source["files"].items():
        path = root / "expansion-sources" / filename
        assert path.stat().st_size == receipt["bytes"] and digest(path) == receipt["sha256"]

result = root / "expansion/cells-enriched.ndjson.gz"
temp = result.with_suffix(".part")
totals = Counter()
with ExitStack() as stack:
    streams = [stack.enter_context(gzip.open(p, "rt")) for p in paths]
    raw = stack.enter_context(temp.open("wb"))
    output = stack.enter_context(gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename=""))
    total = 0
    for i, lines in enumerate(zip(*streams, strict=True)):
        original, scientific, extra = [json.loads(line) for line in lines]
        assert original["nested_index"] == i
        assert original["cell_id"] == scientific.pop("cell_id") == extra.pop("cell_id") == f"HPX128:{i}"
        assert extra["hirise_projected_centroid_records"] == (
            extra["hirise_rdr4_centroid_records"] + extra["hirise_rdrv11_centroid_records"])
        totals["ctx"] += extra["ctx_edr_centroid_records"] > 0
        totals["hirise_rdr4"] += extra["hirise_rdr4_centroid_records"] > 0
        totals["hirise_rdrv11"] += extra["hirise_rdrv11_centroid_records"] > 0
        totals["hirise_combined"] += extra["hirise_projected_centroid_records"] > 0
        totals["hirise_dtm"] += bool(extra["hirise_dtm_centroid_product_ids"])
        totals["tes_dust"] += extra["tes_dust_my25_sol001"]["opacity"] is not None
        for depth, value in extra["swim_ice_consistency"].items():
            assert value is None or (-1 <= value <= 1 and abs(original["latitude_deg_planetocentric"]) < 60.05)
            totals["swim_" + depth] += value is not None
        if "tes_lambert_albedo" in extra:
            value = extra["tes_lambert_albedo"]
            assert value is None or 0 < value <= 1
            totals["tes_albedo"] += value is not None
        original["science_at_centroid"] = scientific
        original["additional_context_at_centroid"] = extra
        output.write((json.dumps(original, separators=(",", ":"), allow_nan=False) + "\n").encode())
        total += 1
assert total == 196608
for key, source in expansion["sources"].items():
    assert totals[key] == source["cells_with_data"], key
assert totals["hirise_combined"] == expansion["hirise_combined_cells"]
temp.replace(result)
manifest = {
    "rows": total, "baseline_git_commit": base["git_commit"], "output": result.name,
    "sha256": digest(result), "expansion_coverage": dict(totals),
    "inputs": {str(p.relative_to(root)): digest(p) for p in paths},
    "source_manifests": ["map/manifest.json", "science/manifest.json", "expansion/manifest.json"],
    "scope": "The merged file preserves documentation scores and separately adds centroid observations and source-derived context."
}
(root / "expansion/enriched-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
