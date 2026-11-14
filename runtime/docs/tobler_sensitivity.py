"""Pace and reserve sensitivity for the Mars Tobler proposal (runtime/docs/mars-tobler-pace.md).

Runs the synthetic Marswalk demo terrain through the real TerrainGraph, Router and
Dijkstra fields. It varies flat outbound pace, the return-pace factor, the reserve and
the remaining time, then reports which next action each setting recommends.

The outbound field is priced with v_flat. The home field is priced with v_flat x
return_factor. Selection follows the single-stop runtime rule: a direct-return gate,
then science plans that fit B - R, chosen by priority, then margin, then id.
At the current pace the result is checked against plan_marswalk across the study grid.

    python runtime/docs/tobler_sensitivity.py      (from the repository root)
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.marswalk import plan_marswalk
from runtime.marswalk.demo import demo_inputs
from runtime.marswalk.mobility import ToblerScaled
from runtime.marswalk.routing import Router, TerrainGraph

PACES = (0.40, 0.50, 0.60, 0.75)          # flat outbound speed, m/s
RETURN_FACTORS = (1.0, 0.7)              # home pace = v_flat x factor
RESERVES_MIN = (10, 15, 20, 30)
REMAINING_MIN = (45, 60, 75, 90)
CLOSED = (False, True)
BASELINE = (0.50, 1.0, 15)               # current code: 0.5 m/s, symmetric, 15 min reserve


def _routers(baseline, closures, v_flat, factor, cache):
    def router(v):
        key = (round(v, 6), closures)
        if key not in cache:
            graph = TerrainGraph(baseline, ToblerScaled(v_flat_mps=v))
            cache[key] = Router(graph, closures)
        return cache[key]
    return router(v_flat), router(v_flat * factor)


def recommend(baseline, snapshot, v_flat, factor, cache):
    closures = tuple(cell for _, cells in snapshot.closures for cell in cells)
    out, home = _routers(baseline, closures, v_flat, factor, cache)
    budget = snapshot.remaining_s - snapshot.reserve_s
    direct = home.leg_return(snapshot.current_cell, snapshot.return_cell)
    if not direct.ok:
        return "NO_RETURN_ROUTE", None
    if direct.seconds > budget:
        return "RETURN_OVER_RESERVE", budget - direct.seconds
    feasible = []
    for task in snapshot.tasks:
        if task.id in snapshot.completed_task_ids:
            continue
        leg_out = out.leg_outbound(snapshot.current_cell, task.approach_cell)
        leg_home = home.leg_return(task.approach_cell, snapshot.return_cell)
        if not (leg_out.ok and leg_home.ok):
            continue
        margin = budget - (leg_out.seconds + task.dwell_s + leg_home.seconds)
        if margin >= 0:
            feasible.append((-task.priority, -margin, task.id))
    if not feasible:
        return "direct_return", budget - direct.seconds
    best = min(feasible)
    return f"science:{best[2]}", -best[1]


def _check_against_runtime(cache):
    """Symmetric pace must reproduce plan_marswalk at the current default."""
    for closed, remaining in product(CLOSED, REMAINING_MIN):
        baseline, snapshot = demo_inputs(closed=closed, remaining_s=remaining * 60, with_time=False)
        for reserve in RESERVES_MIN:
            scenario = replace(snapshot, reserve_s=reserve * 60)
            runtime = plan_marswalk(baseline, scenario)
            expected = runtime.recommendation or runtime.status
            action, _ = recommend(baseline, scenario, *BASELINE[:2], cache)
            if action != expected:
                raise ValueError(f"Runtime parity failed for {(closed, remaining, reserve)}: "
                                 f"{action} != {expected}")


def main():
    cache = {}
    _check_against_runtime(cache)
    rows = []
    for closed, remaining, reserve, pace, factor in product(CLOSED, REMAINING_MIN, RESERVES_MIN, PACES, RETURN_FACTORS):
        baseline, snapshot = demo_inputs(closed=closed, remaining_s=remaining * 60, with_time=False)
        snapshot = replace(snapshot, reserve_s=reserve * 60)
        action, margin = recommend(baseline, snapshot, pace, factor, cache)
        rows.append((closed, remaining, reserve, pace, factor, action, margin))

    base = {r[:3]: r[5] for r in rows if r[3:5] == BASELINE[:2]}
    print("Recommendation by setting (synthetic demo terrain)")
    for closed, remaining in product(CLOSED, REMAINING_MIN):
        print(f"\n{'north ramp CLOSED' if closed else 'all open'} · B = {remaining} min")
        header = "  reserve  " + "  ".join(f"{p:.2f}{'' if f == 1 else '/x' + str(f)}".rjust(14)
                                          for p, f in product(PACES, RETURN_FACTORS))
        print(header)
        for reserve in RESERVES_MIN:
            cells = []
            for pace, factor in product(PACES, RETURN_FACTORS):
                action = next(r[5] for r in rows if r[:5] == (closed, remaining, reserve, pace, factor))
                short = {"science:transect": "transect", "science:photo-set": "photo-set",
                         "direct_return": "direct", "RETURN_OVER_RESERVE": "OVER_RES",
                         "NO_RETURN_ROUTE": "NO_ROUTE"}[action]
                marker = "*" if action != base[(closed, remaining, reserve)] else " "
                cells.append(f"{short}{marker}".rjust(14))
            print(f"  {reserve:>3} min  " + "  ".join(cells))

    print("\nChanges from 0.50 m/s symmetric at the same reserve (marked *):")
    print("| Pace (m/s), home factor | Actions changed | Science instead of return | Return instead of science |")
    print("| --- | ---: | ---: | ---: |")
    for pace, factor in product(PACES, RETURN_FACTORS):
        changes = [(base[row[:3]], row[5]) for row in rows
                   if row[3:5] == (pace, factor) and row[5] != base[row[:3]]]
        more_science = sum(before == "direct_return" and after.startswith("science:") for before, after in changes)
        more_returns = sum(before.startswith("science:") and after == "direct_return" for before, after in changes)
        print(f"| {pace:.2f}, {factor:.1f} | {len(changes)} | {more_science} | {more_returns} |")

    print("\nChanges at 0.50 m/s symmetric from the 15-minute reserve:")
    for reserve in RESERVES_MIN:
        changes = sum(base[closed, remaining, reserve] != base[closed, remaining, BASELINE[2]]
                      for closed, remaining in product(CLOSED, REMAINING_MIN))
        print(f"  {reserve} min: {changes} of {len(CLOSED) * len(REMAINING_MIN)} situations")


if __name__ == "__main__":
    main()
