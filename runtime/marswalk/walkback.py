"""Mode B · Rover walkback check and breakdown replan.

When the crew drives, the rover can fail anywhere on the route. The crew must
then walk home with no rescue. This module prices every cell's walk home with
the human walking rules and checks the whole rover route against it:

    for every cell x the rover reaches, at elapsed time t(x):
        t(x) + T_walk_home[x] <= B - R

T_walk_home comes from ONE extra Dijkstra run from the shelter on the
transposed walking graph (the third run for rover missions).

Walking speed is the Apollo planners' average for walkbacks of more than an
hour after a rover failure, 2.7 km/h (0.75 m/s), with carried loads abandoned.
It is a planning assumption, not a measured Mars pace. Walking is limited to
15 degrees on edges and cells, the same policy as Mode A.
"""
from dataclasses import dataclass, replace
from datetime import timedelta
import math

import numpy as np

from .config import HumanProfile
from .environment import parse_utc
from .errors import FAIL, MarswalkError, PASS, UNKNOWN
from .mobility import pace_for
from .routing import Router, TerrainGraph

WALKBACK_SPEED_MPS = 0.75
WALKBACK_SLOPE_LIMIT_DEG = 15.0
WALKBACK_SOURCE = ("Apollo planners' 2.7 km/h average for walkbacks over an hour after a rover failure, "
                   "loads abandoned (NASA ALSJ, Lunar Gaits)")


@dataclass(frozen=True)
class WalkbackPolicy:
    speed_mps: float = WALKBACK_SPEED_MPS
    slope_limit_deg: float = WALKBACK_SLOPE_LIMIT_DEG
    source: str = WALKBACK_SOURCE
    provenance: str = "assumed"

    def __post_init__(self):
        self.walking_profile()          # validates speed (walk-to-run limit) and slope limit

    def walking_profile(self):
        return HumanProfile(profile_id="walkback-after-rover-failure", v_flat_mps=self.speed_mps,
                            max_slope_deg=self.slope_limit_deg, provenance=self.provenance)

    def to_dict(self):
        return dict(self.__dict__)


def walkback_router(baseline, closure_cells=(), *, policy=WalkbackPolicy(), backend="auto"):
    """Request graph for walking home after a rover failure (same closures)."""
    profile = policy.walking_profile()
    graph = TerrainGraph(baseline, pace_for(profile), neighbours=profile.neighbours)
    return Router(graph, closure_cells, backend=backend)


def _timeline(plan, rover_router):
    """Yield (cell, elapsed_s) for every cell the rover occupies, in order, with
    dwell time added at each task approach cell."""
    seconds = rover_router.graph.times.seconds
    dwell = dict(plan.dwell)
    elapsed = 0.0
    for name, leg in plan.legs:
        cells = list(leg.cells)
        yield cells[0], elapsed
        for cell, edge in zip(cells[1:], leg.edge_ids):
            elapsed += float(seconds[edge])
            yield cell, elapsed
        if name in ("outbound", "transfer") and plan.task_ids:
            target = plan.task_ids[0] if name == "outbound" else plan.task_ids[1]
            elapsed += dwell[target]
            yield cells[-1], elapsed


def walkback_rule(plan, snapshot, rover_router, walk_router):
    """(outcome, reason, detail) for one rover plan."""
    if any(not leg.ok for _, leg in plan.legs):
        return UNKNOWN, "route incomplete; walkback not evaluated", None
    budget = snapshot.remaining_s - snapshot.reserve_s
    walk_home = walk_router.time_to_home(snapshot.return_cell)
    worst = None
    for cell, elapsed in _timeline(plan, rover_router):
        walk_s = float(walk_home[tuple(cell)])
        if not math.isfinite(walk_s):
            detail = {"cell": list(cell), "elapsed_s": elapsed, "walk_home_s": None, "slack_s": None}
            return (FAIL, f"no walkable route home from {list(cell)} if the rover fails there "
                          f"(steeper than the walking limit, blocked or unverified)", detail)
        slack = budget - (elapsed + walk_s)
        if worst is None or slack < worst["slack_s"]:
            worst = {"cell": list(cell), "elapsed_s": elapsed, "walk_home_s": walk_s, "slack_s": slack}
    if worst["slack_s"] < 0:
        return (FAIL, f"if the rover fails at {worst['cell']} after {worst['elapsed_s'] / 60:.1f} min, walking home "
                      f"takes {worst['walk_home_s'] / 60:.1f} min: {-worst['slack_s'] / 60:.1f} min beyond B - R", worst)
    return (PASS, f"walk home possible from every route cell; tightest {worst['cell']} with "
                  f"{worst['slack_s'] / 60:.1f} min spare", worst)


def walk_home_field(walk_router, home):
    """Seconds to walk home from every cell (inf where no walking route)."""
    return np.asarray(walk_router.time_to_home(home))


def breakdown_snapshot(snapshot, cell, elapsed_s, *, policy=WalkbackPolicy()):
    """Switch to Mode A after a rover failure at `cell`, `elapsed_s` into the plan.

    Science is dropped, the vehicle power scenario no longer applies, and the
    crew walks at the walkback pace under the walking slope limit."""
    if elapsed_s < 0 or not math.isfinite(elapsed_s):
        raise MarswalkError("INVALID_SNAPSHOT", "elapsed time must be finite and non-negative")
    remaining = snapshot.remaining_s - int(math.ceil(elapsed_s))
    if remaining < 0:
        raise MarswalkError("INVALID_SNAPSHOT", "the failure happened after the remaining time ran out")
    when = None
    if snapshot.time_utc is not None:
        when = (parse_utc(snapshot.time_utc) + timedelta(seconds=elapsed_s)).isoformat()
    completed = tuple(replace(task, prerequisites=()) for task in snapshot.tasks
                      if task.id in snapshot.completed_task_ids)
    return replace(snapshot, revision=snapshot.revision + 1, current_cell=tuple(cell),
                   remaining_s=remaining, time_utc=when, profile=policy.walking_profile(), tasks=completed,
                   power=None, provenance=snapshot.provenance + (("rover_failure", "simulated"),))
