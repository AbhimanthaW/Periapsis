"""Evaluate a scripted dust drill on the existing Marswalk demo terrain.

Storm footprints are scenario inputs. The station model is evaluated independently
and supplies point-based advice only. The Perseverance archive reading is an
independent evidence record and is never fed to the demo planner or model.
"""
from dataclasses import dataclass, replace
from datetime import timedelta
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

from runtime.marswalk import plan_marswalk
from runtime.marswalk.demo import DEMO_TIME_UTC, NORTH_RAMP_CLOSURE, demo_inputs
from runtime.marswalk.environment import parse_utc
from runtime.marswalk.forecast import ForecastModel, issue_forecast
from runtime.marswalk.weather import DEFAULT_LIMITS, WeatherFeed, WeatherMessage, WeatherStation, without_solar
from runtime.tradeoff import assess, load_envelope

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SCENARIO = "marswalk-north-ramp-dust-drill-v1"
START = (36, 109)
BUDGET_S = 5400
PLATFORMS = ("human", "rover")
STATION = "drill-base"
DUST_LIMIT = next(limit for limit in DEFAULT_LIMITS if limit.variable == "dust_optical_depth")


@dataclass(frozen=True)
class Event:
    elapsed_s: int
    dust: float
    extent: str
    detail: str


EVENTS = (
    Event(0, 0.72, "clear", "Both return corridors are open."),
    Event(90, 1.14, "edge", "A simulated dust pocket reaches the northern crossing."),
    Event(180, 1.19, "edge", "Dust rises slightly. The advisory footprint and route options are unchanged."),
    Event(270, 2.4, "closed", "The drill excludes the northern corridor. Its previous route crosses blocked terrain."),
    Event(871, 2.4, "stale", "The last dust message has expired. The last corridor closure stays in force."),
    Event(1110, 0.68, "clear", "A fresh reading arrives and the drill reopens the northern corridor."),
)


def _time(origin, seconds):
    return (parse_utc(origin) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _spans(rows):
    """Compact local-metre map geometry, encoded as row/first column/length."""
    for r, row in enumerate(rows):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        yield from ((r, int(a), int(b - a)) for a, b in zip(edges[::2], edges[1::2]))


def _mask(shape, cells):
    mask = np.zeros(shape, dtype=bool)
    for row, col in cells:
        mask[row, col] = True
    return list(_spans(mask))


def _exposure_m(cells, footprint, cell_m):
    """Length through the scripted footprint on the cell-centre polyline."""
    return round(sum(math.dist(a, b) * cell_m * ((a in footprint) + (b in footprint)) / 2
                     for a, b in zip(cells, cells[1:])))


class HazardReplay:
    def __init__(self, model_path=None):
        self.model_error = None
        self.model = None
        if model_path is not None:
            try:
                model = ForecastModel.load(model_path)
                if model.station.get("provenance") != "simulated" or model.station.get("station_id") != "synthetic-north-48":
                    raise ValueError("this replay requires its synthetic station artifact")
                self.model = model
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
                self.model_error = str(error)
        self.weather_samples = json.loads((EXAMPLES / "forecast-observations-simulated.json").read_text())
        self.archive = json.loads((EXAMPLES / "weather-jezero-meda-replay.json").read_text())
        self.inputs = {platform: demo_inputs(platform=platform, closed=True, remaining_s=BUDGET_S)
                       for platform in PLATFORMS}
        baseline, snapshot = self.inputs["human"]
        self.full = frozenset(snapshot.closure_cells)
        self.edge = frozenset((r, c) for r, c in self.full if 39 <= r <= 46 and c <= 102)
        sup = baseline.support
        levels = np.floor(np.nan_to_num(baseline.z_m, nan=-1) / 4).astype(int)
        self.terrain = {
            "shape": sup.shape, "cell_m": sup.cell_dx_m, "start": START, "shelter": snapshot.return_cell,
            "classification": sup.classification, "pack_id": sup.pack_id, "pack_version": sup.pack_version,
            "elevation": [list(_spans(levels == i)) for i in range(int(levels.max()) + 1)],
            "excluded": list(_spans(baseline.known_excluded)), "unknown": list(_spans(baseline.unknown)),
            "slope_limit_deg": baseline.policy.slope_limit_deg,
        }

    def _weather(self, event, now, station_cell):
        age_s = event.elapsed_s - EVENTS[3].elapsed_s if event.extent == "stale" else 0
        observed = _time(now, -age_s)
        return WeatherFeed(
            stations=(WeatherStation(STATION, station_cell),),
            messages=(WeatherMessage(STATION, "dust_optical_depth", event.dust, "1", "observed",
                                     observed, "simulated"),),
            required=True,
        ), observed

    def _forecast(self, event):
        model = self.model
        if model is None:
            return {"status": "unavailable", "reason": "No usable synthetic station model artifact."}
        samples = self.weather_samples
        now = _time(samples["now_utc"], event.elapsed_s)
        readings = [] if event.extent == "stale" else samples["observations"]
        try:
            outlook = issue_forecast(model, readings, now, provenance="simulated")
            # Empirical residual bands are retained; the replay emits no event probabilities.
            return {
                "status": "issued", "model_id": model.id, "provenance": outlook["provenance"],
                "issued_utc": outlook["issued_utc"], "station": model.station,
                "latest": outlook["latest"], "sensors_fresh": outlook["sensors_fresh"],
                "rows": [{k: row[k] for k in ("target", "label", "unit", "horizon", "valid_utc",
                                              "p10", "p50", "p90", "status", "kit", "reason", "track_record")}
                         for row in outlook["forecasts"]],
            }
        except (ValueError, TypeError, KeyError, IndexError, RuntimeError, AttributeError, ArithmeticError):
            return {"status": "unavailable", "reason": "The station forecast could not be evaluated."}

    def _plan(self, platform, index, avoid):
        baseline, snapshot = self.inputs[platform]
        event = EVENTS[index]
        now = _time(DEMO_TIME_UTC, event.elapsed_s)
        feed, _ = self._weather(event, now, snapshot.return_cell)
        snapshot = replace(
            snapshot, current_cell=START, tasks=(), mission_id=SCENARIO, revision=index + 1,
            remaining_s=BUDGET_S - event.elapsed_s, time_utc=now, weather=feed,
            power=without_solar(snapshot.power) if event.extent == "stale" and snapshot.power else snapshot.power,
            closures=((NORTH_RAMP_CLOSURE, tuple(sorted(self.full))),) if avoid else (),
        )
        return plan_marswalk(baseline, snapshot, backend="python")

    def _route(self, route_id, plan, footprint, now, *, blocked=False):
        leg, candidate = plan.direct_leg, plan.plans[0]
        crew = None
        if plan.snapshot.profile.platform == "human" and not blocked:
            result = assess(
                plan, EXAMPLES / "crew-human-factors.json", EXAMPLES / "human-cost-policy.json",
                load_envelope(EXAMPLES / "tradeoff-envelope-simulated.json", now_utc=now), now_utc=now,
                telemetry=None, decision_window_s=0, one_way_light_time_s=0,
            )
            option = result["assessments"][0]
            crew = {
                "class": option["class"],
                "reason": option["first_failing_rule"],
                "margin_s": min((p["margin_s"] for p in option["per_astronaut"]), default=None),
            }
        energy = candidate.energy_ledger
        return {
            "id": route_id, "cells": leg.cells, "distance_m": None if leg.length_m is None else round(leg.length_m),
            "seconds": None if blocked or leg.seconds is None else round(leg.seconds),
            "margin_s": None if blocked or candidate.margin_s is None else round(candidate.margin_s),
            "energy_margin_wh": None if blocked or energy is None or energy.margin is None else round(energy.margin / 3600),
            "exposure_m": _exposure_m(leg.cells, footprint, plan.baseline.support.cell_dx_m),
            "status": "blocked" if blocked else "feasible" if candidate.passed and (crew is None or crew["class"] == "GREEN")
                      else "infeasible",
            "reasons": ["Crosses the active northern corridor closure."] if blocked else candidate.failure_reasons,
            "checks": [] if blocked else [{"id": rule, "status": value, "reason": why}
                                          for rule, value, why in candidate.constraints],
            "crew": crew,
        }

    @lru_cache(maxsize=len(EVENTS))
    def frame(self, index):
        if type(index) is not int or not 0 <= index < len(EVENTS):
            raise IndexError("unknown replay step")
        event = EVENTS[index]
        now = _time(DEMO_TIME_UTC, event.elapsed_s)
        blocked = event.extent in ("closed", "stale")
        footprint = self.full if blocked else self.edge if event.extent == "edge" else frozenset()
        _, observed_utc = self._weather(event, now, self.inputs["human"][1].return_cell)
        routes = {}
        for platform in PLATFORMS:
            # Once closed, retain the previous route as map geometry for comparison.
            # Only the plan on the open graph in a non-closure frame can be selected.
            crossing = self._plan(platform, 0 if blocked else index, False)
            bypass = self._plan(platform, index, True)
            routes[platform] = [
                self._route("A", crossing, footprint, now, blocked=blocked),
                self._route("B", bypass, footprint, now),
            ]
        weather = bypass.weather
        sample = weather.alerts[0]
        return {
            "schema_version": 1, "scenario_id": SCENARIO, "index": index, "time_utc": now,
            "elapsed_s": event.elapsed_s, "detail": event.detail,
            "footprint": _mask(self.terrain["shape"], footprint), "extent": event.extent,
            "weather": {
                "value": event.dust, "observed_utc": observed_utc, "age_s": sample.age_s,
                "status": sample.level, "freshness_limit_s": bypass.snapshot.weather.max_age_s,
                "caution": DUST_LIMIT.caution, "warning": DUST_LIMIT.warning,
                "solar_disabled": weather.no_solar_credit or weather.link_lost, "provenance": "simulated",
            },
            "forecast": self._forecast(event), "routes": routes,
        }

    def bundle(self):
        return {"schema_version": 1, "scenario_id": SCENARIO, "terrain": self.terrain,
                "archive": self.archive, "frames": [self.frame(i) for i in range(len(EVENTS))]}


def main():
    from argparse import ArgumentParser

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    replay = HazardReplay(args.model)
    if replay.model is None:
        parser.error(replay.model_error or "model required")
    args.out.write_text(json.dumps(replay.bundle(), separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
