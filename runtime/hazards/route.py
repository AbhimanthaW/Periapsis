"""Time-aware routing on the live hazard map.

Plain Dijkstra assumes the map does not change during the walk. Hazards move, so
each candidate route is checked at the time the crew would actually reach each
square (arrival time from the plan's own edge times, plus dwell):

    1. close the squares blocked NOW (live closure, on a copy; terrain untouched)
    2. plan with Marswalk (Dijkstra out + Dijkstra home, all existing gates)
    3. walk the recommended route and the direct return along their arrival times;
       if any square is hazardous within +/- eta_buffer_s of arrival, close the
       hazard footprint for that time window and plan again
    4. after max_iterations, close every square hazardous at any time in the
       lookahead window (conservative) and plan once more
    5. no route home under the live closures -> EMERGENCY: move to the nearest
       square that stays clear for the whole lookahead and hold; alert base

The planner keeps both endpoint cells in its graph. The live route check
permits departure from a hazardous crew cell and refuses hazardous arrivals.

A radiation alert active now or during the planned trip means return now: science
is dropped and only the direct return is planned. A lost link (stale inputs) also
drops science, as in runtime.marswalk.weather with a required feed.
"""
from dataclasses import dataclass, field, replace
import math

import numpy as np

from runtime.marswalk import plan_marswalk
from runtime.marswalk.errors import OK

from .live import HazardTimeline, LivePolicy

LIVE_CLOSURE = "live-hazard"
GO, RETURN_NOW, EMERGENCY = "go", "return_now", "emergency"


def route_timeline(plan, router):
    """[(cell, seconds_from_now, event)] for every square a plan occupies, in order.
    event is None, or "dwell_end:<task>" when a dwell finishes at that square."""
    if not plan.legs or any(not leg.ok for _, leg in plan.legs):
        return []
    seconds = router.graph.times.seconds
    dwell = dict(plan.dwell)
    out, elapsed = [], 0.0
    for name, leg in plan.legs:
        cells = [tuple(c) for c in leg.cells]
        if not out:
            out.append((cells[0], 0.0, None))
        for cell, edge in zip(cells[1:], leg.edge_ids):
            elapsed += float(seconds[edge])
            out.append((cell, elapsed, None))
        if name in ("outbound", "transfer") and plan.task_ids:
            task = plan.task_ids[0] if name == "outbound" else plan.task_ids[1]
            elapsed += dwell[task]
            out.append((cells[-1], elapsed, f"dwell_end:{task}"))
    return out


@dataclass
class LivePlan:
    result: object                       # MarswalkPlan under the final live closures
    timeline: HazardTimeline
    status: str                          # go | return_now | emergency
    plan_id: str | None                  # plan the crew should follow
    route: list                          # [(cell, seconds_from_now, event)]
    live_closed: frozenset
    iterations: int
    messages: list = field(default_factory=list)
    hold_cell: tuple | None = None       # emergency: where to wait
    hold_eta_s: float | None = None
    return_reason: str | None = None

    @property
    def total_s(self):
        return self.route[-1][1] if self.route else None

    @property
    def margin_s(self):
        if self.plan_id is None:
            return None
        plan = self.result.plan(self.plan_id)
        return plan.ledger.margin

    def to_dict(self):
        state = self.timeline.current
        return {"status": self.status, "plan_id": self.plan_id, "planner_status": self.result.status,
                "route": [{"cell": list(c), "t_s": round(t, 1), "event": e} for c, t, e in self.route],
                "total_s": self.total_s, "margin_s": self.margin_s, "iterations": self.iterations,
                "return_reason": self.return_reason,
                "live_closed_squares": len(self.live_closed), "messages": self.messages,
                "hold": None if self.hold_cell is None else {"cell": list(self.hold_cell), "eta_s": self.hold_eta_s},
                "hazard_now": {"time_utc": state.time_utc, "blocked": int(state.blocked.sum()),
                               "caution": int(state.caution.sum()), "radiation_alert": state.radiation_alert,
                               "stale": list(state.stale), "reasons": list(state.reasons)}}


def _cells(mask):
    return {tuple(map(int, rc)) for rc in np.argwhere(mask)}


def route_hazards(route, timeline):
    """Blocked arrivals and dwell intervals, allowing the crew to leave its initial square."""
    for i, (cell, t, _) in enumerate(route):
        until = route[i + 1][1] if i + 1 < len(route) and route[i + 1][0] == cell else None
        if i == 0 and t == 0.0 and until is None and len(route) > 1:
            continue
        if timeline.hazardous(cell, t, until):
            yield cell, t


def _conflicts(route, timeline, protect):
    """Footprint squares around each conflicting arrival or occupancy interval."""
    close = set()
    for cell, t in route_hazards(route, timeline):
        if cell not in protect:
            close.add(cell)
            close |= _cells(timeline.footprint_around(t))
    return close - protect


def _plan(baseline, snapshot, closed, kwargs):
    closures = tuple(c for c in snapshot.closures if c[0] != LIVE_CLOSURE)
    if closed:
        closures += ((LIVE_CLOSURE, tuple(sorted(closed))),)
    return plan_marswalk(baseline, replace(snapshot, closures=closures), **kwargs)


def _hold(baseline, result, snapshot, timeline, closed, kwargs):
    """Find a reachable hold square and a timed path that stays clear."""
    budget = min(snapshot.remaining_s, timeline.policy.lookahead_s)
    while True:
        router = result.router
        dist, _ = router.outbound_field(snapshot.current_cell)
        clear = ~timeline.blocked.any(axis=0) & result.baseline.routable
        times = np.where(clear.ravel() & (dist <= budget), dist, np.inf)
        best = int(np.argmin(times))
        if not math.isfinite(times[best]):
            return None, []
        cell = router.cell(best)
        leg = router.leg_outbound(snapshot.current_cell, cell)
        route = [(tuple(leg.cells[0]), 0.0, None)]
        elapsed = 0.0
        for step, edge in zip(leg.cells[1:], leg.edge_ids):
            elapsed += float(router.graph.times.seconds[edge])
            route.append((tuple(step), elapsed, None))
        bad = {step for step, _ in route_hazards(route, timeline)} - closed
        if not bad:
            return cell, route
        if snapshot.return_cell in bad:
            # Marswalk requires its return cell to remain open. A different route cannot
            # be evaluated through this endpoint, so use no movement recommendation.
            return None, []
        closed = closed | bad
        result = _plan(baseline, snapshot, closed, kwargs)


def plan_live(baseline, snapshot, feed, now_utc, policy=LivePolicy(), *, max_iterations=8, **plan_kwargs):
    """Plan on terrain + live hazards with arrival-time checks. Deterministic."""
    return _plan_live(baseline, snapshot, feed, now_utc, policy, max_iterations, plan_kwargs, None)


def _plan_live(baseline, snapshot, feed, now_utc, policy, max_iterations, plan_kwargs, forced):
    timeline = HazardTimeline(feed, baseline.support, now_utc, policy)
    state = timeline.current
    protect = {tuple(snapshot.current_cell), tuple(snapshot.return_cell)}
    messages = list(state.reasons)
    snapshot = replace(snapshot, time_utc=now_utc)
    if forced:
        science_off = forced
        return_reason = "radiation"
    elif state.radiation_alert:
        science_off = "radiation alert active: return now"
        return_reason = "radiation"
    elif state.link_lost:
        science_off = f"hazard data stale ({', '.join(state.stale)}): science stops, last closures held"
        return_reason = "link_lost"
    else:
        science_off = None
        return_reason = None
    planned = replace(snapshot, tasks=(), completed_task_ids=()) if science_off else snapshot
    if science_off:
        messages.append(science_off)
    for cell in protect:
        if state.blocked[cell]:
            messages.append(f"square {list(cell)} is inside an active hazard now")

    closed = _cells(state.blocked) - protect
    iterations = 0
    while True:
        result = _plan(baseline, planned, closed, plan_kwargs)
        follow = result.recommendation if result.status == OK else None
        checks = [p for p in {follow, "direct_return"} if p is not None]
        new = set()
        for plan_id in checks:
            add = _conflicts(route_timeline(result.plan(plan_id), result.router), timeline, protect)
            new |= add - closed
        if not new or iterations >= max_iterations:
            break
        closed |= new
        iterations += 1
    if new:                                    # did not settle: close everything hazardous in the window
        closed |= _cells(timeline.blocked.any(axis=0)) - protect
        result = _plan(baseline, planned, closed, plan_kwargs)
        follow = result.recommendation if result.status == OK else None
        messages.append("arrival-time checks did not settle; all squares hazardous in the lookahead are closed")
    checks = (follow, "direct_return") if follow and follow != "direct_return" else ("direct_return",)
    routes = {plan_id: route_timeline(result.plan(plan_id), result.router) for plan_id in checks}
    outside_horizon = {plan_id: bool(route and route[-1][1] + timeline.buffer_s(route[-1][1]) > policy.lookahead_s)
                       for plan_id, route in routes.items()}
    blocked = {plan_id: bool(outside_horizon[plan_id] or list(route_hazards(route, timeline)))
               for plan_id, route in routes.items()}
    if follow and follow != "direct_return" and blocked[follow] and not blocked["direct_return"]:
        follow = "direct_return"
        messages.append("science route cannot be verified within hazard limits; use direct return")
    if result.status != OK or follow is None or blocked[follow] or blocked["direct_return"]:
        if any(outside_horizon.values()):
            messages.append("the route extends beyond the assessed hazard horizon")
        hold, hold_route = _hold(baseline, result, planned, timeline, closed, plan_kwargs)
        eta = hold_route[-1][1] if hold_route else None
        messages.append("no verified route home under live hazards: EMERGENCY, alert base")
        if hold is not None:
            messages.append(f"move to {list(hold)} ({eta / 60:.1f} min) and hold; it stays clear for "
                            f"{policy.lookahead_s / 60:.0f} min")
        return LivePlan(result, timeline, EMERGENCY, None, hold_route, frozenset(closed), iterations,
                        messages, hold, eta, return_reason)

    route = routes[follow]
    if not science_off and timeline.radiation_alert_within(0, route[-1][1]):
        return _plan_live(baseline, snapshot, feed, now_utc, policy, max_iterations, plan_kwargs,
                          "radiation alert starts during this trip: return now")
    status = RETURN_NOW if science_off else GO
    return LivePlan(result, timeline, status, follow, route, frozenset(closed), iterations, messages,
                    return_reason=return_reason)
