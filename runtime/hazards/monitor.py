"""Background monitor: re-plan on the live hazard map every tick, warn, then reroute.

Each tick (default 60 s, and whenever new data arrives) the monitor re-plans from
the crew's CURRENT square with the time actually left, then compares the result
with the route the crew is following:

    radiation alert                     -> RETURN_NOW   (switch to the direct return)
    no safe route home                  -> EMERGENCY    (move to the hold square, alert base)
    hazard data stale                   -> LINK_LOST    (science stops, return; closures held)
    current route hazardous on arrival  -> REROUTE      (warn, then switch)
    caution squares on the current route -> CAUTION     (warn, keep the route)
    a safe route saves >= reroute_saving_s -> SUGGEST   (offer, do not switch)
    otherwise                           -> CONTINUE

Hysteresis: the crew only switches when the current route became unsafe (or a
return is forced). A merely faster alternative is offered, never imposed, so the
route does not flip back and forth between ticks.

`simulate` moves a crew along its route tick by tick against a live feed, as a
deterministic, offline rehearsal. It is a simulation, not telemetry.

    python -m runtime.hazards.monitor runtime/examples/live-hazards-dust-devil.json
    python -m runtime.hazards.monitor runtime/examples/live-hazards-dust-devil.json --platform rover
"""
from dataclasses import dataclass, field, replace
from datetime import timedelta
import json
from pathlib import Path
import sys

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import MarswalkError

from .live import LivePolicy, load_feed
from .route import EMERGENCY, RETURN_NOW, plan_live, route_hazards

CONTINUE, CAUTION, SUGGEST, REROUTE = "continue", "caution", "suggest", "reroute"
LINK_LOST, ARRIVED, START = "link_lost", "arrived", "start"
ACTION_RETURN_NOW, ACTION_EMERGENCY = "return_now", "emergency"


def _iso(when):
    return when.isoformat().replace("+00:00", "Z")


@dataclass
class Tick:
    time_utc: str
    elapsed_s: float
    crew_cell: tuple
    action: str
    message: str
    plan_id: str | None
    remaining_route_s: float | None
    margin_s: float | None
    hazard_blocked: int
    hazard_caution: int

    def to_dict(self):
        return {**self.__dict__, "crew_cell": list(self.crew_cell)}


@dataclass
class Monitor:
    baseline: object
    snapshot: object                    # the mission at the start (tasks, budget, reserve, profile)
    feed: object                        # LiveFeed; only messages received by each tick are used
    policy: LivePolicy = field(default_factory=LivePolicy)
    plan_kwargs: dict = field(default_factory=dict)

    def __post_init__(self):
        self.feed.validate(self.baseline.support)
        self.route = []                 # [(cell, seconds_since_adopted, event)]
        self.adopted_s = 0.0            # mission time at which the route was adopted
        self.plan_id = None
        self.completed = set(self.snapshot.completed_task_ids)
        self.crew_cell = self.snapshot.current_cell
        self.revision = self.snapshot.revision
        self.mode = "go"
        self.hold_cell = None

    # -- helpers
    def _position(self, elapsed_s):
        """Last square of the current route reached by mission time `elapsed_s`."""
        local = elapsed_s - self.adopted_s
        cell = self.route[0][0] if self.route else self.crew_cell
        for c, t, event in self.route:
            if t > local:
                break
            cell = c
            if event and event.startswith("dwell_end:"):
                self.completed.add(event.split(":", 1)[1])
        return tuple(cell)

    def _remaining(self, crew_cell, elapsed_s):
        """The rest of the current route, re-timed from now."""
        local = elapsed_s - self.adopted_s
        rest = [(c, t - local, e) for c, t, e in self.route if t >= local]
        if not rest or rest[0][1] > 0:
            rest = [(crew_cell, 0.0, None)] + rest
        return rest

    def _adopt(self, live, elapsed_s):
        self.route, self.adopted_s, self.plan_id = live.route, elapsed_s, live.plan_id

    def _snapshot(self, crew_cell, elapsed_s, *, science=True):
        tasks = tuple(t for t in self.snapshot.tasks if t.id not in self.completed) if science else ()
        return replace(self.snapshot, current_cell=tuple(crew_cell), remaining_s=max(0, int(self.snapshot.remaining_s - elapsed_s)),
                       tasks=tasks, completed_task_ids=(), revision=self.revision)

    def _tick(self, when, elapsed_s, crew_cell, action, message, live):
        state = live.timeline.current
        rest = self._remaining(crew_cell, elapsed_s) if self.route else []
        remaining_route_s = rest[-1][1] if rest else None
        margin_s = (self.snapshot.remaining_s - elapsed_s - self.snapshot.reserve_s - remaining_route_s
                    if self.plan_id is not None and remaining_route_s is not None else None)
        return Tick(_iso(when), elapsed_s, tuple(crew_cell), action, message, self.plan_id,
                    remaining_route_s, margin_s, int(state.blocked.sum()), int(state.caution.sum()))

    # -- the loop
    def start(self, start_utc):
        self.start_time = parse_utc(start_utc)
        live = plan_live(self.baseline, self.snapshot, self.feed, start_utc, self.policy, **self.plan_kwargs)
        if live.status == EMERGENCY:
            self.mode, self.hold_cell = "emergency", live.hold_cell
            self._adopt(live, 0.0)
            return self._tick(self.start_time, 0.0, self.snapshot.current_cell, ACTION_EMERGENCY,
                              "; ".join(live.messages[-2:]), live)
        self._adopt(live, 0.0)
        if live.status == RETURN_NOW:
            self.mode = "return"
            action = LINK_LOST if live.return_reason == "link_lost" else ACTION_RETURN_NOW
            return self._tick(self.start_time, 0.0, self.snapshot.current_cell, action,
                              "WARNING: " + live.messages[-1], live)
        return self._tick(self.start_time, 0.0, self.snapshot.current_cell, START,
                          f"GO: {live.plan_id}, {live.total_s / 60:.1f} min, margin {live.margin_s / 60:.1f} min"
                          + ("" if not live.messages else " | " + "; ".join(live.messages)), live)

    def tick(self, elapsed_s):
        self.revision += 1
        when = self.start_time + timedelta(seconds=elapsed_s)
        now = _iso(when)
        crew = self.crew_cell = self._position(elapsed_s)
        if self.mode == "emergency":
            live = plan_live(self.baseline, self._snapshot(crew, elapsed_s, science=False), self.feed, now, self.policy,
                             **self.plan_kwargs)
            if live.status == EMERGENCY:
                rest = self._remaining(crew, elapsed_s)
                if not self.route or self.hold_cell != live.hold_cell or any(route_hazards(rest, live.timeline)):
                    self.hold_cell = live.hold_cell
                    self._adopt(live, elapsed_s)
                message = "moving to the hold square" if self.hold_cell and crew != self.hold_cell else "holding"
                return self._tick(when, elapsed_s, crew, ACTION_EMERGENCY, message + "; no verified route home", live)
            self.mode = "return"
            self._adopt(live, elapsed_s)
            return self._tick(when, elapsed_s, crew, ACTION_RETURN_NOW, "a route home has opened: return now", live)

        if crew == tuple(self.snapshot.return_cell) and self.route and \
                elapsed_s - self.adopted_s >= self.route[-1][1]:
            live = plan_live(self.baseline, self._snapshot(crew, elapsed_s, science=False), self.feed, now,
                             self.policy, **self.plan_kwargs)
            return self._tick(when, elapsed_s, crew, ARRIVED, "at the shelter", live)

        science = self.mode == "go"
        live = plan_live(self.baseline, self._snapshot(crew, elapsed_s, science=science), self.feed, now,
                         self.policy, **self.plan_kwargs)
        timeline = live.timeline
        rest = self._remaining(crew, elapsed_s)
        unsafe = list(route_hazards(rest, timeline))
        caution = [c for c, _, _ in rest if timeline.current.caution[c]]

        if live.status == EMERGENCY:
            self.mode, self.hold_cell = "emergency", live.hold_cell
            self._adopt(live, elapsed_s)
            return self._tick(when, elapsed_s, crew, ACTION_EMERGENCY, "WARNING: " + "; ".join(live.messages[-2:]),
                              live)
        if live.return_reason == "radiation":
            switch = self.mode != "return"
            self.mode = "return"
            if switch or unsafe:
                self._adopt(live, elapsed_s)
                return self._tick(when, elapsed_s, crew, ACTION_RETURN_NOW,
                                  f"WARNING: radiation alert. Return now via {live.plan_id}, "
                                  f"{live.total_s / 60:.1f} min", live)
        if live.return_reason == "link_lost" and self.mode == "go":
            self.mode = "return"
            self._adopt(live, elapsed_s)
            return self._tick(when, elapsed_s, crew, LINK_LOST,
                              "WARNING: hazard data stale; science stops, returning with last closures held", live)
        if unsafe:
            cell, t = unsafe[0]
            self._adopt(live, elapsed_s)
            return self._tick(when, elapsed_s, crew, REROUTE,
                              f"WARNING: hazard predicted at {list(cell)} in {t / 60:.1f} min. Rerouting: "
                              f"{live.plan_id}, {live.total_s / 60:.1f} min, margin {live.margin_s / 60:.1f} min", live)
        if caution:
            return self._tick(when, elapsed_s, crew, CAUTION,
                              f"caution: {len(caution)} squares ahead are near hazard limits; keep the route", live)
        current_s = rest[-1][1]
        if live.plan_id == self.plan_id and live.total_s is not None and \
                current_s - live.total_s >= self.policy.reroute_saving_s:
            return self._tick(when, elapsed_s, crew, SUGGEST,
                              f"a safe route saves {(current_s - live.total_s) / 60:.1f} min; not switching", live)
        return self._tick(when, elapsed_s, crew, CONTINUE, "route clear", live)


def simulate(baseline, snapshot, feed, start_utc, *, policy=LivePolicy(), tick_s=60.0, max_ticks=180, **plan_kwargs):
    """Offline rehearsal: move the crew tick by tick and record every decision."""
    monitor = Monitor(baseline, snapshot, feed, policy, plan_kwargs)
    ticks = [monitor.start(start_utc)]
    for i in range(1, max_ticks + 1):
        tick = monitor.tick(i * tick_s)
        ticks.append(tick)
        if tick.action == ARRIVED or tick.elapsed_s >= snapshot.remaining_s:
            break
    return ticks


def main(argv=None):
    from argparse import ArgumentParser
    from runtime.marswalk.demo import DEMO_TIME_UTC, demo_inputs

    parser = ArgumentParser(prog="python -m runtime.hazards.monitor", description=__doc__.split("\n\n")[0])
    parser.add_argument("feed", type=Path, help="live hazard feed JSON (runtime/examples/live-hazards-*.json)")
    parser.add_argument("--platform", choices=("human", "rover"), default="human")
    parser.add_argument("--start-cell", type=int, nargs=2, metavar=("ROW", "COL"))
    parser.add_argument("--remaining-s", type=int)
    parser.add_argument("--no-science", action="store_true", help="plan the return only")
    parser.add_argument("--tick-s", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.feed.read_text())
        scenario = data.get("scenario", {})
        baseline, snapshot = demo_inputs(platform=args.platform,
                                         remaining_s=args.remaining_s or scenario.get("remaining_s", 3600))
        start = args.start_cell or scenario.get("start_cell")
        snapshot = replace(snapshot, current_cell=tuple(start) if start else snapshot.current_cell,
                           tasks=() if (args.no_science or scenario.get("no_science")) else snapshot.tasks)
        feed = load_feed(args.feed, baseline.support)
        ticks = simulate(baseline, snapshot, feed, data.get("start_utc", DEMO_TIME_UTC), tick_s=args.tick_s)
    except MarswalkError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([t.to_dict() for t in ticks], allow_nan=False))
        return 0
    print(f"SIMULATED live hazard rehearsal on the synthetic demo map ({args.platform}) - feed {feed.feed_id}")
    print(f"{'t':>6}  {'crew':<10} {'action':<11} message")
    shown = None
    for t in ticks:
        if (t.action == CONTINUE or (t.action, t.message) == shown) and t is not ticks[-1]:
            continue
        shown = (t.action, t.message)
        print(f"{t.elapsed_s / 60:5.1f}m  {str(list(t.crew_cell)):<10} {t.action:<11} {t.message}")
    print(f"({len(ticks)} ticks of {args.tick_s:g} s; 'route clear' and repeated ticks not shown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
