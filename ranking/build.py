"""Compile pinned Return Window cell records into a deterministic ranking pack."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sqlite3
import zlib
from pathlib import Path

import numpy as np

from .inputs import N, SHA256, inspect
from .layers import compile_layers
from .pack import save


def propagate(concepts, support, covered):
    ids = {item["id"]: i for i, item in enumerate(concepts)}
    # All edges point from a concrete child toward its broader concept.
    # Repeated relaxation covers multi-level chains without query-time walks.
    for _ in range(len(ids)):
        changed = False
        for child, item in enumerate(concepts):
            for parent_id in item["broader"]:
                parent = ids[parent_id]
                candidate = np.rint(support[child].astype(np.float32) * 0.8).astype(np.uint8)
                if parent_id == "ice":
                    # Ice evaluation is confined to SWIM. Polar-cap and apron
                    # units are separately queryable geological evidence.
                    candidate[~covered[parent]] = 0
                larger = candidate > support[parent]
                if np.any(larger):
                    support[parent] = np.maximum(support[parent], candidate)
                    changed = True
                if parent_id != "ice":
                    covered[parent] |= covered[child] & (support[child] > 0)
        if not changed:
            break
    else:
        raise ValueError("concept hierarchy did not converge")
    lake, delta, fan, polar = (ids[x] for x in ("lake", "delta", "alluvial-fan", "polar-deposits"))
    sedimentary = ids["sedimentary"]
    support[sedimentary] = np.maximum.reduce((support[sedimentary], support[lake], support[delta],
        support[fan], np.rint(support[polar].astype(np.float32) * 0.6).astype(np.uint8)))
    covered[sedimentary] |= covered[lake] | covered[delta] | covered[fan] | covered[polar]
    age = np.maximum(support[ids["age-noachian"]], support[ids["age-hesperian"]])
    water = np.maximum.reduce((support[delta], support[lake], support[ids["aqueous-alteration"]]))
    habit = ids["habitability"]
    support[habit] = np.minimum(water, age)
    covered[habit] = (covered[delta] | covered[lake] | covered[ids["aqueous-alteration"]]) & (
        covered[ids["age-noachian"]] | covered[ids["age-hesperian"]])


def detail_store(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE cells (nested_index INTEGER PRIMARY KEY, record BLOB NOT NULL)")
        with gzip.open(source, "rt", encoding="utf-8") as stream:
            batch = []
            for index, line in enumerate(stream):
                batch.append((index, zlib.compress(line.rstrip("\n").encode(), level=6)))
                if len(batch) == 1000:
                    connection.executemany("INSERT INTO cells VALUES (?,?)", batch)
                    batch.clear()
            if batch:
                connection.executemany("INSERT INTO cells VALUES (?,?)", batch)


def build(inputs: Path, output: Path, *, with_demo=False, release=False):
    if release and with_demo:
        raise ValueError("release pack cannot contain synthetic layers")
    observed = inspect(inputs)
    concepts, real, covered, reported, demo, demo_covered, filters, records, features, demo_receipt = compile_layers(inputs, with_demo)
    real_covered = covered.copy()
    propagate(concepts, real, real_covered)
    if with_demo:
        combined = np.maximum(real, demo)
        combined_covered = real_covered | demo_covered
        propagate(concepts, combined, combined_covered)
    else:
        combined = real
        combined_covered = real_covered
    from marsdoc.grid import Grid
    neighbours = np.asarray(Grid(128).healpix.neighbours(np.arange(N)), dtype=np.int32).T.copy()
    if neighbours.shape != (N, 8):
        raise ValueError(f"unexpected neighbour shape {neighbours.shape}")
    arrays = {"support": real, "covered": np.packbits(real_covered, axis=1),
              "reported": np.packbits(reported, axis=1), "filters": np.packbits(
                  np.stack([filters[x] for x in sorted(filters)]), axis=1),
              "records": records, "neighbours": neighbours}
    if with_demo:
        arrays["support_demo"] = combined
        arrays["covered_demo"] = np.packbits(combined_covered, axis=1)
    for scale, width in ((64, 4), (32, 16), (16, 64)):
        arrays[f"pyramid_{scale}"] = combined.reshape(len(concepts), -1, width).max(axis=2)
    counts = (real >= 128).sum(axis=1)
    idf = np.log1p((N - counts + 0.5) / (counts + 0.5))
    weights = np.rint(idf * np.array([0.35 if item["facet"] == "age" else 1.0 for item in concepts]) * 65536).astype(np.uint32)
    demo_counts = (combined >= 128).sum(axis=1)
    demo_idf = np.log1p((N - demo_counts + 0.5) / (demo_counts + 0.5))
    demo_weights = np.rint(demo_idf * np.array([0.35 if item["facet"] == "age" else 1.0 for item in concepts]) * 65536).astype(np.uint32)
    manifest = save(output, arrays, {"version": "cell-ranking-v1", "release": release,
        "synthetic_layers": ([{**demo_receipt, "concepts": [x["id"] for x in concepts if x["status"] == "demo"]}]
                             if with_demo else []),
        "input_sha256": SHA256, "input_counts": observed, "concept_order": [x["id"] for x in concepts],
        "n": counts.tolist(), "idf": idf.tolist(), "w_int": weights.tolist(),
        "n_demo": demo_counts.tolist(), "idf_demo": demo_idf.tolist(), "w_int_demo": demo_weights.tolist(),
        "filter_order": sorted(filters)}, {"ranking-features.json.gz": inputs / "ranking-features.json.gz"})
    detail_store(inputs / "cells-enriched-sourced.ndjson.gz", output / "cells.sqlite")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("data/ranking-inputs"))
    parser.add_argument("--output", type=Path, default=Path("data/ranking-pack"))
    parser.add_argument("--with-demo", action="store_true")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    result = build(args.inputs, args.output, with_demo=args.with_demo, release=args.release)
    print(json.dumps({"version": result["version"], "release": result["release"],
                      "synthetic_layers": result["synthetic_layers"], "concepts": len(result["concept_order"])}, sort_keys=True))


if __name__ == "__main__":
    main()
