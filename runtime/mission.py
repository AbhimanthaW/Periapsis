"""Local mission pack consumer and deterministic fixture simulation."""
import argparse
from heapq import heappop, heappush
import json
from math import inf
from pathlib import Path
import sys

from contracts.pack import PackError, check_pack


def load_pack(directory, *, simulation=False, site_sha256=None):
    capability = "routing_simulation" if simulation else "elevation_preview"
    return check_pack(directory, capability=capability, site_sha256=site_sha256)


def _shortest_route(start, goal, allowed, elevation, spacing):
    if not allowed[start] or not allowed[goal]:
        return None
    queue = [(0.0, start)]
    costs = {start: 0.0}
    parents = {}
    rows, cols = allowed.shape
    while queue:
        travel, node = heappop(queue)
        if travel != costs[node]:
            continue
        if node == goal:
            path = [node]
            while node != start:
                node = parents[node]
                path.append(node)
            return {"seconds": travel, "cells": tuple(reversed(path))}
        row, col = node
        for dr, dc in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            edge = (row + dr, col + dc)
            if not (0 <= edge[0] < rows and 0 <= edge[1] < cols and allowed[edge]):
                continue
            length = spacing[0] if dc else spacing[1]
            uphill = max(0.0, float(elevation[edge]) - float(elevation[node]))
            cost = travel + length + 2.0 * uphill
            if cost < costs.get(edge, inf):
                costs[edge] = cost
                parents[edge] = node
                heappush(queue, (cost, edge))
    return None


def simulate(pack, *, closures=(), remaining_s=None):
    if pack.scenario is None or pack.site["build_id"] != "synthetic-fixture-v1":
        raise PackError("CAPABILITY_UNAVAILABLE", "only the synthetic v1 fixture scenario is supported")
    scenario = pack.scenario
    named = {closure["id"]: closure["cells"] for closure in scenario["closures"]}
    if len(set(closures)) != len(closures) or set(closures) - named.keys():
        raise PackError("INVALID_SCENARIO", "unknown or duplicate closure")
    remaining = scenario["remaining_s"] if remaining_s is None else remaining_s
    if type(remaining) is not int or not 0 <= remaining <= 86_400:
        raise PackError("INVALID_SCENARIO", "remaining time must be an integer from 0 to 86400 seconds")
    allowed = pack.terrain["valid_mask"] & ~pack.terrain["screen_excluded_mask"]
    for key in closures:
        for cell in named[key]:
            allowed[cell] = False
    a, _, _, _, e, _ = pack.site["grid"]["affine"]
    checkpoint = scenario["checkpoint"]["cell"]
    home = scenario["shelter"]["cell"]

    def route(start, goal):
        return _shortest_route(start, goal, allowed, pack.elevations, (a, -e))

    direct = route(checkpoint, home)
    reverse = route(home, checkpoint)
    reserve = scenario["reserve_s"]
    budget = remaining - reserve
    margin = None if direct is None else budget - direct["seconds"]
    result = dict(pack_id=pack.site["pack_id"], pack_version=pack.site["pack_version"],
                  scenario_id=scenario["scenario_id"], classification="synthetic", closure_ids=list(closures),
                  remaining_s=remaining, reserve_s=reserve, direct_return=direct, reverse_control=reverse,
                  return_margin_s=margin, completed_task_ids=list(scenario["completed_task_ids"]),
                  science=[], recommendation=None)
    if direct is None:
        return dict(result, status="NO_RETURN_ROUTE")
    if margin < 0:
        return dict(result, status="RETURN_OVER_RESERVE")

    feasible = []
    for task in pack.stations:
        if task["id"] in scenario["completed_task_ids"]:
            continue
        approach = task["approach_cell"]
        outbound = route(checkpoint, approach)
        inbound = route(approach, home)
        seconds = None if outbound is None or inbound is None else (
            outbound["seconds"] + task["dwell_s"] + inbound["seconds"]
        )
        task_margin = None if seconds is None else budget - seconds
        eligible = task_margin is not None and task_margin >= 0
        result["science"].append(dict(id=task["id"], seconds=seconds, margin_s=task_margin, feasible=eligible))
        if eligible:
            feasible.append((-task["priority"], -task_margin, task["id"]))
    return dict(result, status="OK", recommendation=min(feasible)[2] if feasible else "direct_return")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "simulate"))
    parser.add_argument("pack", type=Path)
    parser.add_argument("--site-sha256")
    parser.add_argument("--closure", action="append", default=[])
    parser.add_argument("--remaining-s", type=int)
    args = parser.parse_args()
    simulation = args.mode == "simulate"
    if not simulation and (args.closure or args.remaining_s is not None):
        parser.error("closure and remaining time require simulation")
    try:
        pack = load_pack(args.pack, simulation=simulation, site_sha256=args.site_sha256)
        if simulation:
            result = simulate(pack, closures=args.closure, remaining_s=args.remaining_s)
        else:
            result = {key: pack.site[key] for key in ("pack_id", "pack_version", "region_id", "classification", "capabilities")}
            result["shape"] = pack.elevations.shape
        print(json.dumps(result, allow_nan=False))
    except PackError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
