"""Profile pinned ranking data without including installation or pack load."""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

import numpy as np

from ranking.engine import groups
from ranking.service import RankRequest, RankingService


def median_ms(function, repeats=7):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        function()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return round(statistics.median(samples), 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=Path("data/ranking-pack"))
    args = parser.parse_args()
    service = RankingService(args.pack)
    engine = service.engine
    pack = engine.pack
    rows = [engine.ids[name] for name in ("ice", "age-noachian")]
    support = pack["support"]
    weights = pack.manifest["w_int"]
    covered = [np.unpackbits(pack["covered"][j], count=196608).astype(bool) for j in rows]

    def score():
        values = np.zeros(196608, dtype=np.uint64)
        for j in rows:
            values += np.uint64(weights[j]) * support[j]
        return values

    def states():
        return covered[0] & covered[1] & (support[rows[0]] >= 128) & (support[rows[1]] >= 128)

    selected = states()
    scores = score()
    timings = {
        "parse": median_ms(lambda: engine.parser.parse("ancient ice")),
        "score": median_ms(score),
        "states": median_ms(states),
        "tiles": median_ms(lambda: scores.reshape(-1, 16).max(axis=1)),
        "group": median_ms(lambda: groups(selected, pack["neighbours"], scores, 500)),
    }
    print({"direct_cells": int(selected.sum()), "ancient_ice_stage_ms": timings})
    objectives = ("ancient ice", "water", "tectonic grabens", "ancient lakes shallow ice lava flow chlorides")
    for objective in objectives:
        query = RankRequest(schema_version=1, request_id="bench", objective=objective, limit=500)
        cold = median_ms(lambda: engine.rank(query))
        service.rank(query)
        cached = median_ms(lambda: service.rank(query))
        print({"objective": objective, "cold_ms": cold, "cached_ms": cached})
        timings[f"cold: {objective}"] = cold
        timings[f"cached: {objective}"] = cached
    budgets = {"parse": 1, "score": 2, "states": 2, "tiles": 2, "group": 20}
    budgets.update({f"cold: {x}": 50 for x in objectives})
    budgets.update({f"cached: {x}": 1 for x in objectives})
    over = [name for name, value in timings.items() if value >= budgets[name]]
    if over:
        print("Outside target:", ", ".join(over))
    failed = [name for name, value in timings.items() if value > budgets[name] * 2]
    if failed:
        raise SystemExit("More than twice budget: " + ", ".join(failed))


if __name__ == "__main__":
    main()
