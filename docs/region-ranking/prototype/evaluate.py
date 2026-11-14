#!/usr/bin/env python3
"""Determinism, parameter sensitivity and cell-scale timing for the ranking prototype.

    python3 -I evaluate.py REGIONS_JSON LEXICON_JSON

Sensitivity perturbs one parameter at a time by -20 % and +20 % and reports how
much of each benchmark objective's top five survives. The cell benchmark uses
synthetic sparse concept support for 196,608 HEALPix cells to measure scoring
cost only. Its values are not Mars data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rank_regions as rr  # noqa: E402

BENCHMARK = [
    "ancient water and delta deposits",
    "subsurface ice and glacial landforms",
    "young volcanism and lava flows",
    "clay and sulfate minerals from aqueous alteration",
    "tectonic faults and seismic activity",
    "habitability and biosignature preservation",
]


def top(out: dict, k: int = 5) -> list[str]:
    return [r["name"] for r in out["rows"] if r["rank"] is not None][:k]


def perturbations(raw: dict):
    yield "bm25.k1", lambda L, f: L["bm25"].__setitem__("k1", L["bm25"]["k1"] * f)
    for role in raw["field_roles"]:
        if raw["field_roles"][role] > 0:
            yield f"role.{role}", lambda L, f, r=role: L["field_roles"].__setitem__(r, min(1.0, L["field_roles"][r] * f))
    for rel in ("narrower_per_level", "broader", "related"):
        yield f"relation.{rel}", lambda L, f, r=rel: L["relation_weights"].__setitem__(r, min(1.0, L["relation_weights"][r] * f))
    yield "hedge_weight", lambda L, f: L.__setitem__("hedge_weight", min(1.0, L["hedge_weight"] * f))
    yield "cross_reference_weight", lambda L, f: L.__setitem__("cross_reference_weight", min(1.0, L["cross_reference_weight"] * f))
    yield "query_weight.age", lambda L, f: L["query_weights"].__setitem__("age", L["query_weights"]["age"] * f)


def main() -> None:
    regions = json.load(open(sys.argv[1], encoding="utf-8"))["regions"]
    raw = json.load(open(sys.argv[2], encoding="utf-8"))
    lex = rr.Lexicon(raw)

    # 1. Determinism: identical bytes on repeated runs and with shuffled input order.
    digests = set()
    for order in (regions, list(reversed(regions)), regions[1::2] + regions[0::2]):
        blob = json.dumps([rr.rank(order, lex, q, [], None) for q in BENCHMARK], sort_keys=True).encode()
        digests.add(hashlib.sha256(blob).hexdigest())
    print(f"determinism: {len(digests)} distinct digest(s) across 3 input orders")

    # 2. Baseline and sensitivity.
    t0 = time.perf_counter()
    index = rr.build_index(regions, lex)
    t1 = time.perf_counter()
    base = {q: top(rr.rank(regions, lex, q, [], None, index)) for q in BENCHMARK}
    t2 = time.perf_counter()
    print(f"index build {1000 * (t1 - t0):.0f} ms for {len(regions)} regions; "
          f"query {1000 * (t2 - t1) / len(BENCHMARK):.1f} ms mean (pure Python)")
    for q, names in base.items():
        print(f"baseline  {q!r}: {', '.join(names)}")
    worst = []
    for name, apply in perturbations(raw):
        for f in (0.8, 1.2):
            L = copy.deepcopy(raw)
            apply(L, f)
            lx = rr.Lexicon(L)
            ix = rr.build_index(regions, lx)
            runs = {q: top(rr.rank(regions, lx, q, [], None, ix)) for q in BENCHMARK}
            kept = [len(set(runs[q]) & set(base[q])) / len(base[q]) for q in BENCHMARK]
            first = sum(runs[q][:1] == base[q][:1] for q in BENCHMARK)
            worst.append((min(kept), sum(kept) / len(kept), first, name, f))
    worst.sort()
    print("\nsensitivity (one parameter x0.8 / x1.2): min top-5 overlap, mean overlap, unchanged #1 of 6")
    for mn, mean, first, name, f in worst:
        print(f"  {name:<34} x{f:<4} min {mn:.1f}  mean {mean:.2f}  #1 kept {first}/6")

    # 3. Cell-scale scoring cost with synthetic sparse support.
    try:
        import numpy as np
    except ImportError:
        print("numpy unavailable; skipping cell benchmark")
        return
    rng = np.random.default_rng(7)
    n_cells, n_concepts = 196_608, len(raw["concepts"])
    nnz_per_cell = 6
    rows = np.repeat(np.arange(n_cells, dtype=np.uint32), nnz_per_cell)
    cols = rng.integers(0, n_concepts, rows.size).astype(np.uint16)
    vals = rng.integers(1, 256, rows.size).astype(np.uint8)  # support quantised to 1/255
    order = np.lexsort((rows, cols))  # concept-major posting lists
    cols, rows, vals = cols[order], rows[order], vals[order]
    starts = np.searchsorted(cols, np.arange(n_concepts + 1))
    q = rng.choice(n_concepts, 3, replace=False)
    w = np.array([2.3, 0.25, 0.11], dtype=np.float32)
    t0 = time.perf_counter()
    for _ in range(50):
        score = np.zeros(n_cells, dtype=np.float32)
        for c, wc in zip(q, w):
            a, b = starts[c], starts[c + 1]
            np.add.at(score, rows[a:b], wc * vals[a:b].astype(np.float32) / 255)
        k = np.argpartition(-score, 100)[:100]
        k = k[np.lexsort((k, -score[k]))]  # stable: score then cell index
    dt = (time.perf_counter() - t0) / 50
    size = rows.nbytes + cols.nbytes + vals.nbytes
    print(f"\ncell benchmark: {n_cells:,} cells x {n_concepts} concepts, {rows.size:,} postings, "
          f"{size / 1e6:.1f} MB, 3-concept query + top-100 in {dt * 1000:.1f} ms")


if __name__ == "__main__":
    main()
