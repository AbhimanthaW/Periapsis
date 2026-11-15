"""Integrated planning session for the synthetic Marswalk site."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from math import ceil, dist, isfinite
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
import numpy as np

from ranking.lexicon import Parser, tokenize
from runtime.hazards.planning import POLICY as SPATIAL_POLICY, planning_mask, update_feed
from runtime.hazards.timing import timed_hazards
from runtime.humancost import load_crew, load_policy, prepare
from runtime.marswalk import EnvironmentalVariable, MarswalkError, WalkbackPolicy, plan_marswalk
from runtime.marswalk.config import _cell
from runtime.marswalk.demo import DEMO_TIME_UTC, NORTH_RAMP_CLOSURE, demo_inputs
from runtime.marswalk.environment import SOL_S, PowerScenario, parse_utc
from runtime.marswalk.forecast import ForecastModel, Observation, issue_forecast
from runtime.marswalk.mobility import SCENARIO_SPEED_FACTOR
from runtime.marswalk.optimization import compare_pareto, select_next_action
from runtime.marswalk.profiles import load_profile
from runtime.marswalk.routing import SearchCache
from runtime.marswalk.weather import DEFAULT_LIMITS, WeatherFeed, WeatherMessage, WeatherStation, without_solar
from runtime.objective_model import ObjectiveModel
from runtime.tradeoff import assess, load_envelope
from runtime.tradeoff.accept import GREEN
from runtime.tradeoff.classify import walking_preference
from runtime.tradeoff.walkback import crew_walkback_check

EXAMPLES = Path(__file__).with_name("examples")
START = (36, 109)
BUDGET_S = 5400
WEATHER_LIMITS = {limit.variable: limit for limit in DEFAULT_LIMITS}
REQUIRED_WEATHER = ("wind_speed", "dust_optical_depth")
FORECAST_ONLY = {"pressure_pa": ("Pa", 50, 1500), "air_temp_k": ("K", 100, 320)}
TASK_CONCEPTS = {"transect": "stratigraphy", "photo-set": "sedimentary"}
SPATIAL_CLOSURE_ID = "spatial-planning-mask"

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Cell = Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=2, max_length=2)]
PositiveRevision = Annotated[int, Field(gt=0)]
NonnegativeNumber = Annotated[FiniteFloat, Field(ge=0)]
DecisionSeconds = Annotated[FiniteFloat, Field(ge=0, le=86_400)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HazardEvent(Input):
    hazard_id: Identifier
    revision: PositiveRevision
    action: Literal["caution", "close", "clear"]
    observed_utc: Identifier
    cells: Annotated[list[Cell], Field(max_length=4096)] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_geometry(self):
        if self.hazard_id == SPATIAL_CLOSURE_ID:
            raise ValueError("this hazard ID is reserved for the spatial mapper")
        if bool(self.cells) != (self.action != "clear"):
            raise ValueError("caution and close need cells; clear removes the existing footprint")
        if len({tuple(cell) for cell in self.cells}) != len(self.cells):
            raise ValueError("duplicate hazard cells")
        return self


class WeatherReading(Input):
    variable: Literal["wind_speed", "dust_optical_depth", "sep_alert", "pressure_pa", "air_temp_k"]
    value: FiniteFloat
    unit: Identifier
    time_utc: Identifier

    @model_validator(mode="after")
    def check_value(self):
        if self.variable in FORECAST_ONLY:
            unit, low, high = FORECAST_ONLY[self.variable]
        else:
            limit = WEATHER_LIMITS[self.variable]
            unit, low, high = limit.unit, limit.valid_min, limit.valid_max
        if self.unit != unit or not low <= self.value <= high:
            raise ValueError(f"{self.variable} requires {unit} in [{low}, {high}]")
        return self


class RoutingRequest(Input):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    request_id: Identifier
    pack_id: Identifier
    pack_version: Identifier
    expected_revision: Annotated[int, Field(ge=0)]
    time_utc: Identifier
    current_cell: Cell
    objective: Annotated[str, Field(max_length=1024)] = ""
    confirmed_task_ids: Annotated[list[Identifier], Field(max_length=16)] = Field(default_factory=list)
    completed_task_ids: Annotated[list[Identifier], Field(max_length=16)] = Field(default_factory=list)
    weather_readings: Annotated[list[WeatherReading], Field(max_length=96)] = Field(default_factory=list)
    hazard_events: Annotated[list[HazardEvent], Field(max_length=16)] = Field(default_factory=list)
    live_hazards: dict | None = None  # The team mapper validates the grid and the observation schema.
    crew_stores: Annotated[dict[Identifier, dict[Identifier, NonnegativeNumber]], Field(max_length=16)] | None = None
    rover_charge_wh: NonnegativeNumber | None = None
    telemetry: dict | None = None  # Validated by the trade-off model's versioned loader.
    decision_window_s: DecisionSeconds | None = None
    one_way_light_time_s: DecisionSeconds | None = None
    include_shortest_distance: bool = True


def _update_hazards(previous, events, now, shape):
    latest = dict(previous)
    for event in events:
        observed = parse_utc(event.observed_utc)
        if observed > now:
            raise MarswalkError("INVALID_HAZARD", "hazard observation is in the future")
        for cell in event.cells:
            _cell("hazard", cell, shape)
        prior = latest.get(event.hazard_id)
        if prior is not None:
            if event == prior:
                continue
            if event.revision <= prior.revision or observed < parse_utc(prior.observed_utc):
                raise MarswalkError("STALE_HAZARD", f"superseded or conflicting event for {event.hazard_id}")
            if prior.action == "close" and event.action == "caution":
                raise MarswalkError("INVALID_HAZARD", f"clear {event.hazard_id} before changing it to a caution")
        latest[event.hazard_id] = event
    return latest


def _update_weather(previous, readings, now):
    history = dict(previous)
    for reading in readings:
        time = parse_utc(reading.time_utc)
        if time > now:
            raise MarswalkError("INVALID_WEATHER", "weather observation is in the future")
        key = (reading.variable, time)
        if key in history and history[key].value != reading.value:
            raise MarswalkError("WEATHER_CONFLICT", f"conflicting {reading.variable} readings at {reading.time_utc}")
        history[key] = reading
    # The forecast uses the current local bin and the two preceding bins.
    return dict(sorted(((key, value) for key, value in history.items() if (now - key[1]).total_seconds() <= SOL_S / 6),
                       key=lambda entry: entry[0][1])[-4096:])


def _weather_products(history, model, station, time_utc):
    recent = {}
    observations = []
    for (variable, _), reading in history.items():
        recent[variable] = reading
        if variable != "sep_alert":
            observations.append(Observation(variable, reading.value, reading.time_utc))
    messages = tuple(WeatherMessage(station.id, var, item.value, item.unit, "observed", item.time_utc)
                     for var, item in recent.items() if var in WEATHER_LIMITS)
    feed = WeatherFeed((station,), messages, required=True, required_variables=REQUIRED_WEATHER)
    try:
        outlook = issue_forecast(model, observations, time_utc, provenance="simulated")
        json.dumps(outlook, allow_nan=False)
        outlook["status"] = "issued"
    except (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError, MarswalkError):
        outlook = {"status": "unavailable", "model_id": model.id, "provenance": "simulated",
                   "forecasts": [], "reason": "station forecast evaluation failed"}
    return feed, outlook


def _objective_tasks(parser, model, catalogue, request):
    parsed = parser.parse(request.objective)
    # Planetary-layer support is independent of this synthetic site's authored tasks.
    recognized = {item["id"] for item in (*parsed["concepts"], *parsed["unsupported"])}
    matches = recognized - {item["id"] for item in parsed["negated"]}
    eligible = {task.id for task in catalogue if TASK_CONCEPTS[task.id] in matches}
    prediction = model.predict(request.objective)
    suggested = prediction["suggested_task_id"]
    has_negation = any(token.group() in parser.negation for token in tokenize(request.objective))
    learned_eligible = suggested is not None and not has_negation and (not eligible or suggested in eligible)
    if learned_eligible:
        eligible.add(suggested)
    confirmed = set(request.confirmed_task_ids)
    if confirmed - eligible or len(confirmed) != len(request.confirmed_task_ids):
        raise MarswalkError("INVALID_TASK_CONFIRMATION", "confirm each matching catalogue task at most once")
    # A completed task remains in the snapshot for prerequisite and history validation.
    included = confirmed | set(request.completed_task_ids)
    return (tuple(task for task in catalogue if task.id in included),
            {"text": request.objective, "interpretation": parsed, "prediction": prediction,
             "model_suggestion_eligible": learned_eligible, "eligible_task_ids": sorted(eligible),
             "confirmed_task_ids": sorted(confirmed), "requires_confirmation": sorted(eligible - included)})


def _plan_result(plan, cautions, tradeoff=None, *, include_shortest_distance=True, hazard_mode="static"):
    status = plan.status
    recommendation = plan.recommendation
    candidates = plan.plans
    front, objectives_used = [], []
    assessments = {} if tradeoff is None else {row["option_id"]: row["class"] for row in tradeoff["assessments"]}
    if tradeoff is not None:
        if assessments["direct_return"] == GREEN:
            passing = [candidate for candidate in candidates if assessments[candidate.id] == GREEN]
            front, objectives_used = compare_pareto(passing, plan.router)
            recommendation = select_next_action(passing, front, plan.snapshot)
        else:
            recommendation = None
            if status == "OK":
                status = "RETURN_RESOURCE_LIMIT"
    reference = (plan.router.shortest_distance(plan.snapshot.current_cell, plan.snapshot.return_cell)
                 if include_shortest_distance else None)
    output = plan.to_dict()
    output["shortest_distance_return"] = None if reference is None else reference.to_dict()
    output["hazard_routing"] = hazard_mode
    # Publish one recommendation and Pareto set after the full resource gate.
    output["recommendation"] = recommendation
    output["recommended_task_ids"] = [] if recommendation is None else list(plan.plan(recommendation).task_ids)
    if tradeoff is not None:
        output["pareto_front"] = front
        output["objectives_used"] = objectives_used
    output["status"] = status
    support = plan.baseline.support
    for candidate, row in zip(candidates, output["candidates"]):
        legs = [leg for _, leg in candidate.legs]
        routed = all(leg.ok for leg in legs)
        row["distance_m"] = sum(leg.length_m for leg in legs) if routed else None
        row["surface_m"] = sum(leg.surface_m for leg in legs) if routed else None
        row["travel_s"] = sum(leg.seconds for leg in legs) if routed else None
        row["elapsed_s"] = candidate.ledger.total_use if routed else None
        row["elapsed_sols"] = None if not routed else row["elapsed_s"] / SOL_S
        row["caution_exposure_m"] = sum(
            dist(support.center_xy(*a), support.center_xy(*b)) * ((a in cautions) + (b in cautions)) / 2
            for leg in legs for a, b in zip(leg.cells, leg.cells[1:])
        ) if routed else None
        row["envelope_class"] = assessments.get(candidate.id)
        row["eligible_for_recommendation"] = candidate.passed and (
            tradeoff is None or (assessments["direct_return"] == GREEN and assessments[candidate.id] == GREEN))
    return output


class FinalRoutingSession:
    """One loopback drill. Updates and plan publication commit in revision order."""

    def __init__(self, forecast_model: ForecastModel, *, rover_profile=None, human_policy=None):
        station = forecast_model.station
        if station["provenance"] != "simulated" or station["station_id"] != "synthetic-north-48":
            raise ValueError("the routing drill requires the synthetic-north-48 station model")
        self._model = forecast_model
        self._baseline, human = demo_inputs(closed=True, remaining_s=BUDGET_S)
        self._search_cache = SearchCache(self._baseline)
        _, rover = demo_inputs(platform="rover", remaining_s=BUDGET_S)
        self._crew = load_crew(EXAMPLES / "crew-human-factors.json")
        self._policy = load_policy(human_policy or EXAMPLES / "human-cost-policy.json")
        human_inputs = prepare(self._crew, self._policy)["routing_inputs"]
        self._envelope = load_envelope(EXAMPLES / "tradeoff-envelope-simulated.json", now_utc=DEMO_TIME_UTC)
        self._parser = Parser()
        self._objective_model = ObjectiveModel(
            EXAMPLES / "objective-training-simulated.json", TASK_CONCEPTS, self._parser.stop | self._parser.generic)
        self._station = WeatherStation(station["station_id"], human.return_cell)
        self._template = replace(human, mission_id="integrated-routing-drill", closures=(),
                                 profile=load_profile(human_inputs["profile"]), reserve_s=human_inputs["reserve_s"],
                                 site_lat_deg=station["lat_deg"], site_lon_east_deg=station["lon_east_deg"])
        self._north_ramp_cells = tuple(dict(human.closures)[NORTH_RAMP_CLOSURE])
        self._rover_profile = rover.profile if rover_profile is None else load_profile(rover_profile)
        if self._rover_profile.platform != "rover":
            raise ValueError("the integrated rover profile must describe a rover")
        self._rover_power = rover.power if self._rover_profile.power_source == "solar" else PowerScenario("none")
        self._lock = Lock()
        self._revision = 0
        self._start = self._time = parse_utc(DEMO_TIME_UTC)
        self._hazards, self._weather = {}, {}
        self._spatial = None
        self._oxygen_factors = {}
        self._completed = set()
        self._crew_stores = None
        self._rover_charge_j = self._rover_profile.initial_charge_j
        self._last_request = self._last_result = None

    def site(self):
        support = self._baseline.support
        return {"schema_version": 1, "pack_id": support.pack_id, "pack_version": support.pack_version,
                "classification": support.classification, "mission_id": self._template.mission_id,
                "start_time_utc": DEMO_TIME_UTC, "current_cell": START, "shelter_cell": self._template.return_cell,
                "initial_budget_s": BUDGET_S, "reserve_s": self._template.reserve_s,
                "grid": {"shape": support.shape, "affine": support.affine, "index_order": "row_col"},
                "terrain": {"elevation_m": [[float(z) if isfinite(z) else None for z in row]
                                            for row in self._baseline.z_m],
                            "permanent_exclusions": self._baseline.known_excluded.tolist(),
                            "unsupported": self._baseline.unknown.tolist()},
                "tasks": [{"id": task.id, "concept": TASK_CONCEPTS[task.id], "approach_cell": task.approach_cell,
                           "dwell_s": task.dwell_s} for task in self._template.tasks],
                "demo_footprints": {NORTH_RAMP_CLOSURE: self._north_ramp_cells}}

    def update(self, request: RoutingRequest):
        with self._lock:
            return self._update(request)

    def latest(self):
        with self._lock:
            return {"revision": self._revision, "plan": deepcopy(self._last_result)}

    def _solve(self, snapshot, timing, swept, *, preference=None, walkback=None, walkback_cost=None):
        options = {"search_cache": self._search_cache, "constrained_search": True,
                   "alternative_preference": preference, "walkback": walkback}

        def solve(snap, hazard_check):
            return plan_marswalk(self._baseline, snap, **options,
                                 candidate_rule=None if hazard_check is None else hazard_check.rule,
                                 walkback_resources=None if walkback_cost is None else walkback_cost(hazard_check))

        plan = solve(snapshot, timing)
        if timing is None:
            return plan, "swept" if swept else "static"
        if plan.plans[0].passed:
            return plan, "arrival_time"
        closures = tuple((cid, cells) for cid, cells in snapshot.closures if cid != SPATIAL_CLOSURE_ID)
        closed = replace(snapshot, closures=closures + ((SPATIAL_CLOSURE_ID, swept),))
        return solve(closed, None), "swept_fallback"

    def _update(self, request):
        support = self._baseline.support
        if (request.pack_id, request.pack_version) != (support.pack_id, support.pack_version):
            raise MarswalkError("MIXED_PACK", "the update must target this session's terrain pack")
        encoded = request.model_dump_json()
        if encoded == self._last_request:
            return deepcopy(self._last_result)
        if request.expected_revision != self._revision:
            raise MarswalkError("STALE_REVISION", f"current routing revision is {self._revision}")
        now = parse_utc(request.time_utc)
        if now < self._time:
            raise MarswalkError("STALE_REVISION", "mission time cannot move backwards")
        current = _cell("current position", request.current_cell, support.shape)
        completed = set(request.completed_task_ids)
        if not self._completed <= completed <= TASK_CONCEPTS.keys() or len(completed) != len(request.completed_task_ids):
            raise MarswalkError("INVALID_TASK_COMPLETION", "completed tasks must be unique known IDs and remain completed")
        tasks, objective = _objective_tasks(self._parser, self._objective_model, self._template.tasks, request)
        hazards = _update_hazards(self._hazards, request.hazard_events, now, support.shape)
        active = [event for _, event in sorted(hazards.items()) if event.action != "clear"]
        closures = tuple((event.hazard_id, tuple(map(tuple, event.cells))) for event in active if event.action == "close")
        cautions = {tuple(cell) for event in active if event.action == "caution" for cell in event.cells}
        history = _update_weather(self._weather, request.weather_readings, now)
        feed, outlook = _weather_products(history, self._model, self._station, request.time_utc)
        stores = self._crew_stores if request.crew_stores is None else request.crew_stores
        charge = self._rover_charge_j if request.rover_charge_wh is None else request.rover_charge_wh * 3600
        rover_profile = replace(self._rover_profile, initial_charge_j=charge)

        revision = self._revision + 1
        remaining_s = max(0, BUDGET_S - ceil((now - self._start).total_seconds()))
        spatial = update_feed(self._spatial, request.live_hazards, support, now)
        spatial_output, environment, power = None, (), self._rover_power
        timing, swept = None, ()
        if spatial is not None:
            state, blocked, caution, radiation, no_solar = planning_mask(spatial, support, now, remaining_s)
            swept = tuple(map(tuple, np.argwhere(blocked).tolist()))
            timing, static = timed_hazards(spatial, support, now, remaining_s, state)
            cells = swept if timing is None else tuple(map(tuple, np.argwhere(static).tolist()))
            if cells:
                closures += ((SPATIAL_CLOSURE_ID, cells),)
            cautions.update(map(tuple, np.argwhere(caution).tolist()))
            reason = "radiation alert overlaps the planning window" if radiation else None
            if state.link_lost and reason is None:
                reason = "spatial observations are stale"
            if reason:
                environment = (EnvironmentalVariable(
                    id="live-hazard-return", variable="live_hazards", mode="explicit_scenario", effect="return_now",
                    purpose=reason, authorized_by="simulated routing policy", provenance="simulated",
                    valid_from_utc=request.time_utc, scenario_id=self._template.scenario_id,
                ),)
            if no_solar:
                power = without_solar(power)
            spatial_output = {"feed_id": spatial.feed_id, "blocked_now": np.argwhere(state.blocked).tolist(),
                              "blocked_for_plan": swept, "blocked_static": cells,
                              "caution_cells": np.argwhere(caution).tolist(),
                              "window_s": remaining_s, "stale": list(state.stale), "radiation_in_window": radiation,
                              "no_solar_credit": no_solar, "return_reason": reason}
        snapshot = replace(self._template, revision=revision, current_cell=current, tasks=tasks, objective=request.objective,
                           completed_task_ids=tuple(sorted(completed)), time_utc=request.time_utc, weather=feed,
                           remaining_s=remaining_s, closures=closures, environment=environment)
        preference = walking_preference(self._crew, self._policy, self._envelope, stores,
                                        self._oxygen_factors, request.telemetry, now)
        human, human_mode = self._solve(snapshot, timing, swept, preference=preference)
        review = assess(human, self._crew, self._policy, self._envelope, now_utc=request.time_utc, current_stores=stores,
                        telemetry=request.telemetry, decision_window_s=request.decision_window_s,
                        one_way_light_time_s=request.one_way_light_time_s, prior_oxygen_factors=self._oxygen_factors)
        factors = review["model"]["oxygen_update"]["applied_factors"]
        walkback = WalkbackPolicy(speed_mps=snapshot.profile.v_flat_mps *
                                  SCENARIO_SPEED_FACTOR[snapshot.profile.pace_scenario],
                                  slope_limit_deg=snapshot.profile.max_slope_deg,
                                  source="simulated human-cost operating profile")
        rover, rover_mode = self._solve(
            replace(snapshot, profile=rover_profile, power=power), timing, swept, walkback=walkback,
            walkback_cost=lambda hazard: crew_walkback_check(
                self._crew, self._policy, self._envelope, stores, factors, hazard),
        )
        freshness = [parse_utc(item.time_utc) + timedelta(seconds=feed.max_age_s, microseconds=1)
                     for item in feed.messages if (now - parse_utc(item.time_utc)).total_seconds() <= feed.max_age_s]
        if spatial is not None:
            for item in (*spatial.storms, *spatial.layers):
                expiry = parse_utc(item.observed_utc) + timedelta(seconds=SPATIAL_POLICY.max_age_s, microseconds=1)
                if item.kind == "observed" and expiry > now:
                    freshness.append(expiry)
        finish = now + timedelta(seconds=remaining_s)
        advisories = [row for row in outlook["forecasts"] if row["status"] == "model"
                      and row.get("limits", {}).get("caution") is not None and row["p90"] >= row["limits"]["caution"]
                      and parse_utc(row["valid_utc"]) <= finish]
        result = {"schema_version": 1, "request_id": request.request_id, "revision": revision,
                  "mission_id": snapshot.mission_id, "pack_id": snapshot.pack_id, "pack_version": snapshot.pack_version,
                  "classification": support.classification, "time_utc": request.time_utc, "current_cell": current,
                  "weather_recheck_utc": min(freshness).isoformat().replace("+00:00", "Z") if freshness else None,
                  "remaining_s": snapshot.remaining_s, "reserve_s": snapshot.reserve_s, "objective": objective,
                  "hazards": [event.model_dump() | {"provenance": "simulated"} for event in active],
                  "spatial_hazards": spatial_output,
                  "observed_weather": human.weather.to_dict(),
                  "forecast": outlook | {"advisory_only": True, "station_cell": self._station.cell,
                                         "planning_window_advisories": advisories},
                  "human": _plan_result(human, cautions, review, hazard_mode=human_mode,
                                        include_shortest_distance=request.include_shortest_distance),
                  "rover": _plan_result(rover, cautions, hazard_mode=rover_mode,
                                        include_shortest_distance=request.include_shortest_distance),
                  "tradeoff": review, "rover_charge_wh": charge / 3600,
                  "human_stores_source": "simulated_start" if stores is None else "simulated_report"}
        self._revision, self._time, self._completed = revision, now, completed
        self._hazards, self._weather, self._crew_stores, self._rover_charge_j = hazards, history, stores, charge
        self._spatial = spatial
        self._oxygen_factors = factors
        self._last_request, self._last_result = encoded, deepcopy(result)
        return result
