"""Profile the pinned pack; fail when a stage exceeds twice its stated budget."""
from __future__ import annotations

import statistics
import time
from pathlib import Path

import numpy as np

from ranking.engine import Engine, groups
from ranking.pack import Pack
from ranking.service import RankRequest


def median_ms(function, repeats=7):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        function()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return round(statistics.median(samples), 3)


def main():
    engine = Engine(Pack(Path("data/ranking-pack")))
    pack = engine.pack
    ids = engine.ids
    names = ("ice", "age-noachian")
    rows = [ids[name] for name in names]
    support = pack["support"]
    weights = pack.manifest["w_int"]
    covered = [np.unpackbits(pack["covered"][j], count=196608).astype(bool) for j in rows]

    def score():
        values = np.zeros(196608, dtype=np.uint64)
        for j in rows:
            values += np.uint64(weights[j]) * support[j].astype(np.uint64)
        return values

    def states():
        return covered[0] & covered[1] & (support[rows[0]] >= 128) & (support[rows[1]] >= 128)

    selected = states()
    timings = {
        "parse": median_ms(lambda: engine.parser.parse("ancient ice")),
        "score": median_ms(score),
        "states": median_ms(states),
        "tiles": median_ms(lambda: score().reshape(-1, 16).max(axis=1)),
        "group": median_ms(lambda: groups(selected, pack["neighbours"])),
        "total": median_ms(lambda: engine.rank(RankRequest(schema_version=1, request_id="bench",
                                                            objective="ancient ice", limit=20))),
    }
    print({"direct_cells": int(selected.sum()), "ms": timings})
    budgets = {"parse": 1, "score": 2, "states": 2, "tiles": 2, "group": 20, "total": 50}
    failed = [name for name, value in timings.items() if value > budgets[name] * 2]
    if failed:
        raise SystemExit("More than twice budget: " + ", ".join(failed))


if __name__ == "__main__":
    main()
