"""Measure synthetic Marswalk runtime with repeat updates and sparse closure edits."""
from argparse import ArgumentParser
from dataclasses import replace
import json
from time import perf_counter

import numpy as np

from .config import HumanProfile, MissionSnapshot, Task
from .plan import plan_marswalk
from .routing import SearchCache, available_backends
from .traversability import ScreenPolicy, TerrainSupport, build_baseline


def benchmark(side, backend, iterations):
    support = TerrainSupport.from_affine((side, side), (5, 0, 0, 0, -5, 5 * side), native_spacing_m=5,
                                         pack_id="benchmark", pack_version="1")
    baseline = build_baseline(support, np.zeros(support.shape), np.ones(support.shape, dtype=bool),
                              policy=ScreenPolicy(slope_limit_deg=15))
    home, current = (side // 2, side // 4), (side // 2, 3 * side // 4)
    state = MissionSnapshot(
        "benchmark", 1, "benchmark", "1", "scaling", current, home,
        (Task("survey", (side // 3, side // 2), 60, 1),), (), 40_000, 900,
        profile=HumanProfile(max_slope_deg=15),
    )
    results = []
    for scenario in ("uncached", "cached_moving_start", "cached_closure_edits"):
        cache = None if scenario == "uncached" else SearchCache(baseline)
        samples, runs = [], []
        for index in range(iterations):
            closures = ((f"edit-{index}", ((home[0], side // 2 + index % (side // 8)),)),) \
                if scenario == "cached_closure_edits" else ()
            snapshot = replace(state, revision=index + 1, closures=closures,
                               current_cell=(current[0] + index % (side // 12), current[1]))
            tick = perf_counter()
            plan = plan_marswalk(baseline, snapshot, backend=backend, search_cache=cache)
            samples.append((perf_counter() - tick) * 1000)
            runs.append(plan.dijkstra_runs)
            if plan.recommendation is None:
                raise RuntimeError("benchmark needs a feasible return")
        results.append({"scenario": scenario, "backend": backend, "cells": side**2, "samples": iterations,
                        "p50_ms": round(float(np.median(samples)), 1),
                        "p95_ms": round(float(np.percentile(samples, 95)), 1),
                        "dijkstra_runs": runs})
        del plan, cache
    return results


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=160, help="square side in cells, up to 1000")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--backend", choices=("python", "scipy"), default="python")
    args = parser.parse_args()
    if not (32 <= args.size <= 1000 and args.iterations >= 2):
        parser.error("size must be 32–1000 and iterations at least 2")
    if args.backend not in available_backends():
        parser.error(f"{args.backend} is unavailable in this environment")
    print(json.dumps(benchmark(args.size, args.backend, args.iterations), indent=2))


if __name__ == "__main__":
    main()
