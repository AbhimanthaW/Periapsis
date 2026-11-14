"""Measure the effect of draft ramp thresholds on the seven golden objectives."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import math

from ranking.build import compile_ranking
from ranking.inputs import inspect
from ranking.pack import Pack
from ranking.service import RankRequest
from ranking.engine import Engine


OBJECTIVES = (
    "ancient lakes",
    "shallow ice",
    "young volcanism and lava flows",
    "tectonic grabens",
    "chloride deposits in Noachian terrain",
    "cave candidates",
    "ancient water and delta deposits",
)
THRESHOLDS = {"ice_max": 0.5, "rocky_lo": 350, "rocky_hi": 500,
              "structure_max": 10, "bounds_max": 0.5}


def top_areas(engine):
    return {
        objective: [(area["tile"], tuple(area["cells"])) for area in engine.rank(RankRequest(
            schema_version=1, request_id="sensitivity", objective=objective, limit=20,
            include_demo=objective == OBJECTIVES[-1]))["areas"]]
        for objective in OBJECTIVES
    }


def evaluate(inputs, pack_dir, threshold, factor):
    value = THRESHOLDS[threshold] * factor
    arrays, metadata = compile_ranking(inputs, with_demo=True, **{threshold: value})
    pack = Pack(pack_dir)
    pack.arrays.update(arrays)
    pack.manifest.update(metadata)
    return threshold, factor, top_areas(Engine(pack))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("data/ranking-inputs"))
    parser.add_argument("--demo-pack", type=Path, default=Path("data/ranking-demo"))
    args = parser.parse_args()
    inspect(args.inputs)
    pack = Pack(args.demo_pack)
    if not pack.manifest["synthetic_layers"]:
        parser.error("a DEMO pack is required to exercise the last golden objective")
    baseline = top_areas(Engine(pack))
    short = {query: len(areas) for query, areas in baseline.items() if len(areas) < 20}
    for query, count in short.items():
        print(f"{query}: {count} baseline areas; top-20 qualification incomplete", flush=True)
    failed = bool(short)
    with ProcessPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(evaluate, args.inputs, args.demo_pack, name, factor)
                   for name in THRESHOLDS for factor in (0.8, 1.2)]
        for future in futures:
            name, factor, changed = future.result()
            overlaps = {query: len(set(areas).intersection(changed[query])) for query, areas in baseline.items()}
            failed |= any(count < math.ceil(0.8 * len(baseline[query])) for query, count in overlaps.items())
            changes = ", ".join(f"{query}={count}/{len(baseline[query])}" for query, count in overlaps.items()
                                if count != len(baseline[query]))
            print(f"{name} {factor:.0%}: {changes or 'all baseline areas retained'}", flush=True)
    if failed:
        raise SystemExit("Sensitivity gate failed: required 20 baseline and 16 identical areas per objective")


if __name__ == "__main__":
    main()
