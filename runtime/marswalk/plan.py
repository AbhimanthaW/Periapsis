"""Marswalk pipeline: 01 -> 04 (human) or 05 (rover) + 03 + 06 -> 09 -> 07 -> 10.

    snapshot (01) ──crew profile──► traversal time (04) ──directional time──┐
    pack terrain ──► traversability (03) ──allowed terrain──────────────────┤
                                                       terrain routing (09) ◄┘
                                                              │ direct return + legs
                                                       resource budgets (07)
                                                              │
                                                    mission optimization (10)

Rover profiles replace 04 with Subsystem 05 and add a battery ledger. Subsystem
06 enters only through Environmental activation: active block_cells become
closures, an active return_now blocks science, a required input that is not
active leaves science unknown.
"""
from dataclasses import asdict, dataclass, field, replace

from runtime.reporting import stage

from .errors import (FAIL, INSUFFICIENT_TERRAIN_EVIDENCE, LEG_NO_EVIDENCE, MarswalkError, NO_RETURN_ROUTE, OK, PASS,
                     RETURN_ENERGY_SEARCH_EXHAUSTED, RETURN_ENERGY_UNVERIFIED, RETURN_ENVIRONMENT_UNVERIFIED,
                     RETURN_OVER_RESERVE, RETURN_WALKBACK_EXCEEDED, UNKNOWN)
from .environment import (ACTIVE, activate_environment, comms_and_forecast_assessment, mars_sun,
                          parse_utc, terrain_illumination)
from .mobility import pace_for
from .optimization import (EXCLUDED_FROM_CORE, compare_pareto, compose_candidate_plans,
                           enforce_hard_constraints, reevaluate_science_tasks, select_constrained_legs,
                           select_energy_feasible_legs,
                           select_next_action)
from .resources import MARGIN_NO_ROUTE, MARGIN_OVER_RESERVE, return_time_margin
from .routing import Router, TerrainGraph, diverse_routes
from .site import gate_for_support
from .walkback import WalkbackPolicy, walkback_router, walkback_rule
from .weather import assess_weather, without_solar

SCHEMA = "marswalk-plan-v1"
SEARCH_HORIZON_MIN_CELLS = 250_000      # "auto": limit outbound search to B - R on grids at least this large
ASSUMPTIONS = (
    "Pace parameters are illustrative scenario assumptions, not calibrated Mars-suit walking data.",
    "Slope and roughness thresholds are prototype policy assumptions and do not establish human safety.",
    "Only crew time is budgeted for people; consumables enter as the authorized remaining time supplied by the crew.",
    "Rover numbers come from a hypothetical or cited vehicle record; no equivalence to NASA rover specifications.",
    "Rover energy credits no regeneration; traction, slip and sinkage are not modelled.",
    "Historical weather and radiation are context only; no forecast or human dose is inferred.",
    "The return check assumes no rescue or vehicle support.",
    "Closures and scenario events are simulated field reports unless tagged as evidence.",
    "Rover walkback uses the Apollo planners' 0.75 m/s emergency walkback average and a 15 degree walking limit.",
    "Weather limits are prototype assumptions; forecasts are advisory and never change the plan.",
)


@dataclass
class MarswalkPlan:
    snapshot: object
    baseline: object
    router: object
    status: str
    direct_gate: object
    plans: list
    front: list
    objectives_used: list
    recommendation: str | None
    alternatives: dict = field(default_factory=dict)
    activations: tuple = ()
    site_gate: object = None
    weather: object = None
    walkback: dict | None = None
    search_horizon_s: float | None = None

    @property
    def pareto_front(self):
        return self.front

    @property
    def direct_leg(self):
        return self.plans[0].legs[0][1]

    def plan(self, plan_id):
        return next(p for p in self.plans if p.id == plan_id)

    @property
    def dijkstra_runs(self):
        extra = 0 if self.walkback is None else self.walkback.get("dijkstra_runs", 0)
        return self.router.dijkstra_runs + extra

    def to_dict(self):
        snap, prof = self.snapshot, self.snapshot.profile
        rec = None if self.recommendation is None else self.plan(self.recommendation)
        return {
            "schema": SCHEMA, "status": self.status,
            "mission_id": snap.mission_id, "revision": snap.revision,
            "pack_id": snap.pack_id, "pack_version": snap.pack_version, "scenario_id": snap.scenario_id,
            "classification": self.baseline.support.classification,
            "platform": prof.platform,
            "profile": _profile_dict(prof),
            "terrain": {"policy_id": self.baseline.policy.policy_id, "cells": self.baseline.reason_counts(),
                        "flagged_features": [list(f) for f in self.baseline.flagged],
                        "notes": list(self.baseline.notes)},
            "remaining_s": snap.remaining_s, "reserve_s": snap.reserve_s,
            "crew_status": snap.crew_status,
            "closure_ids": [cid for cid, _ in snap.closures],
            "completed_task_ids": list(snap.completed_task_ids),
            "direct_return": self.direct_leg.to_dict(),
            "return_margin": self.direct_gate.to_dict(),
            "candidates": [p.to_dict() for p in self.plans],
            "pareto_front": self.front, "objectives_used": self.objectives_used,
            "recommendation": self.recommendation,
            "recommended_task_ids": [] if rec is None else list(rec.task_ids),
            "alternatives": {k: [a.__dict__ | {"leg": a.leg.to_dict()} for a in v]
                             for k, v in self.alternatives.items()},
            "solver": {"backend": self.router.backend, "dijkstra_runs": self.dijkstra_runs,
                       "edges": len(self.router.graph), "cells": int(self.router.graph.n),
                       "outbound_search_horizon_s": self.search_horizon_s},
            "site": None if self.site_gate is None else self.site_gate.to_dict(),
            "weather": None if self.weather is None else self.weather.to_dict(),
            "walkback": self.walkback,
            "provenance": [list(p) for p in snap.provenance],
            "environment": self._environment_dict(),
            "assumptions": list(ASSUMPTIONS), "excluded_from_core": list(EXCLUDED_FROM_CORE),
        }


def _profile_dict(prof):
    if prof.platform == "rover":
        from .rover import summary, traction_assessment
        return {**summary(prof), "neighbours": prof.neighbours, "traction": traction_assessment(prof)}
    return {"profile_id": prof.profile_id, "pace_model": prof.pace_model, "pace_scenario": prof.pace_scenario,
            "v_flat_mps": prof.v_flat_mps, "max_slope_deg": prof.max_slope_deg,
            "neighbours": prof.neighbours, "crew_size": prof.crew_size,
            "provenance": prof.provenance}


def _environment_dict(self):
    snap = self.snapshot
    out = {"activation": [a.to_dict() for a in self.activations],
           "historical_context": [o.__dict__ for v in snap.environment if v.mode == "historical_context"
                                  for o in v.observations],
           "power": None if snap.power is None else {k: v for k, v in snap.power.__dict__.items()},
           "comms_and_forecast": comms_and_forecast_assessment()}
    if snap.time_utc is None or snap.site_lat_deg is None:
        out["solar"] = {"status": "not_declared", "reason": "plan time and site coordinates are both required"}
        return out
    when = parse_utc(snap.time_utc)
    if when.year < 2017:
        out["solar"] = {"status": "unsupported_epoch", "reason": "Mars24 time conversion is pinned from 2017"}
        return out
    sun = mars_sun(when, snap.site_lat_deg, snap.site_lon_east_deg)
    cells = {"current": snap.current_cell, "return": snap.return_cell,
             **{f"task:{t.id}": t.approach_cell for t in snap.tasks}}
    horizon = None if snap.power is None else snap.power.horizon_upper_bound_m
    lit = terrain_illumination(self.baseline, list(cells.values()), sun, horizon_upper_bound_m=horizon)
    out["solar"] = {"status": "computed", "method": "Mars24 (Allison & McEwen 2000)", "sun": sun.to_dict(),
                    "illumination": {name: lit[tuple(c)] for name, c in cells.items()}}
    return out


MarswalkPlan._environment_dict = _environment_dict


def plan_marswalk(baseline, snapshot, *, backend="auto", multistop=False, exposure_slope_deg=10.0,
                  alternatives_k=0, expected_revision=None, evidence=None, walkback=WalkbackPolicy(),
                  search_horizon="auto", walkback_resources=None, search_cache=None, candidate_rule=None,
                  alternative_preference=None, constrained_search=False, report=None, report_scope=""):
    """Plan human (Mode A) or rover (Mode B) routes for one immutable snapshot.

    Phase 0 refuses grids that cannot support a Marswalk before routing.
    `evidence` is an optional site.EvidenceVerdict from the documentation engine.
    Rover plans also need the crew to be able to walk home from every route
    cell (`walkback`; None disables it for vehicle-only studies).
    """
    support = baseline.support
    if not support.pack_version:
        raise MarswalkError("MIXED_PACK", "loaded terrain must declare its pack version")
    profile = snapshot.profile
    rover = profile.platform == "rover"
    with stage(report, report_scope + "site_gate", "Site pack and mission snapshot validation",
               {"grid": asdict(support), "profile_id": profile.profile_id, "expected_revision": expected_revision}) as record:
        site_gate = gate_for_support(support, evidence=evidence,
                                     clearance_m=profile.clearance_m if rover else None).require()   # Phase 0
        snapshot.validate(support.shape, pack_id=support.pack_id, pack_version=support.pack_version,
                          expected_revision=expected_revision)
        if report is not None:
            record.update(site_gate.to_dict())

    with stage(report, report_scope + "environment_gate", "Observed weather and scenario activation",
               {"time_utc": snapshot.time_utc, "planning_window_s": snapshot.remaining_s,
                "weather_feed": None if snapshot.weather is None else asdict(snapshot.weather),
                "environment": [asdict(entry) for entry in snapshot.environment],
                "power": None if snapshot.power is None else asdict(snapshot.power)}) as record:
        horizon = None if snapshot.power is None else snapshot.power.horizon_upper_bound_m
        if horizon is not None and (baseline.z_m > horizon).any():
            raise MarswalkError("INVALID_POWER", "horizon upper bound contradicts the terrain grid")
        weather = None
        if snapshot.weather is not None:
            weather = assess_weather(snapshot.weather, snapshot.time_utc, shape=support.shape)
            if weather.no_solar_credit and snapshot.power is not None:
                snapshot = replace(snapshot, power=without_solar(snapshot.power))
        activations = tuple(activate_environment(snapshot.environment, scenario_id=snapshot.scenario_id,
                                                 time_utc=snapshot.time_utc, duration_s=snapshot.remaining_s))
        blocked = tuple(cell for v, a in zip(snapshot.environment, activations)
                        if a.status == ACTIVE and a.effect == "block_cells" for cell in v.cells)
        if report is not None:
            record.update(weather=None if weather is None else weather.to_dict(),
                          activations=[entry.to_dict() for entry in activations],
                          blocked_cells=blocked, power=None if snapshot.power is None else asdict(snapshot.power))

    with stage(report, report_scope + "terrain_graph", "Screen and weight directed grid edges",
               {"profile": asdict(profile), "terrain_policy": asdict(baseline.policy), "closures": snapshot.closures,
                "environment_blocked_cells": blocked, "walkback": None if not rover or walkback is None else walkback.to_dict(),
                "search_horizon": search_horizon}) as record:
        if search_horizon not in ("auto", True, False):
            raise MarswalkError("INVALID_SNAPSHOT", "search_horizon must be 'auto', True or False")
        cells = support.shape[0] * support.shape[1]
        use_horizon = search_horizon is True or (search_horizon == "auto" and cells >= SEARCH_HORIZON_MIN_CELLS)
        horizon_s = float(max(0, snapshot.remaining_s - snapshot.reserve_s)) if use_horizon else None
        closures = snapshot.closure_cells + blocked
        if search_cache is None:
            graph = TerrainGraph(baseline, pace_for(profile), scenario=getattr(profile, "pace_scenario", "nominal"),
                                 neighbours=profile.neighbours)
            router = Router(graph, closures, backend=backend, outbound_limit_s=horizon_s)
        else:
            if search_cache.baseline is not baseline:
                raise MarswalkError("MIXED_PACK", "the search cache belongs to a different terrain baseline")
            router = search_cache.router(profile, closures, backend=backend, outbound_limit_s=horizon_s)
        walk_router = None
        if rover and walkback is not None:
            walk_router = (walkback_router(baseline, closures, policy=walkback, backend=backend) if search_cache is None
                           else search_cache.router(walkback.walking_profile(), closures, backend=backend))
        if report is not None:
            record.update(baseline_cell_counts=baseline.reason_counts(), nodes=int(router.graph.n),
                          edges=len(router.graph), edge_model=router.graph.times.model, backend=router.backend,
                          outbound_search_horizon_s=horizon_s)

    def extra_rules(plan):
        rules = []
        if candidate_rule is not None:
            rules.append(("hazard_timing", *candidate_rule(plan, router)))
        if weather is not None:
            rules.append(("weather", *weather.rule(plan.kind)))
        if walk_router is not None:
            outcome, reason, _ = walkback_rule(plan, snapshot, router, walk_router)
            rules.append(("walkback", outcome, reason))
            if outcome == PASS and walkback_resources is not None:
                rules.append(("walkback_resources", *walkback_resources(plan, snapshot, router, walk_router)))
        return rules

    checks = dict(activations=activations, extra_rules=extra_rules)
    if constrained_search:
        checks_for_search = checks | {"preference": alternative_preference}
        choose_legs = select_constrained_legs
    else:
        checks_for_search = checks
        choose_legs = select_energy_feasible_legs
    with stage(report, report_scope + "route_search", "Directed Dijkstra and candidate composition",
               {"current_cell": snapshot.current_cell, "shelter_cell": snapshot.return_cell,
                "completed_task_ids": snapshot.completed_task_ids, "tasks": [asdict(task) for task in snapshot.tasks],
                "multistop": multistop}) as record:
        plans = compose_candidate_plans(snapshot, router, multistop=multistop)
        reevaluate_science_tasks(plans, snapshot, router)
        if report is not None:
            record.update(candidates=[p.to_dict() for p in plans], dijkstra_runs=router.dijkstra_runs)

    with stage(report, report_scope + "constraints", "Time and platform resource ledgers and hard gates",
               {"remaining_s": snapshot.remaining_s, "reserve_s": snapshot.reserve_s,
                "constrained_search": constrained_search, "arrival_time_checks": candidate_rule is not None,
                "crew_walkback_resource_checks": walkback_resources is not None}) as record:
        direct_plan = enforce_hard_constraints(plans[0], snapshot, router, **checks)
        plans[0] = direct_plan = choose_legs(direct_plan, snapshot, router, **checks_for_search)
        direct = direct_plan.legs[0][1]
        gate = return_time_margin(snapshot.remaining_s, snapshot.reserve_s, direct)
        for index, plan in enumerate(plans[1:], start=1):
            enforce_hard_constraints(plan, snapshot, router, direct_plan=direct_plan, **checks)
            plans[index] = choose_legs(plan, snapshot, router, direct_plan=direct_plan, **checks_for_search)
        if report is not None:
            record.update(return_margin=gate.to_dict(), candidates=[candidate.to_dict() for candidate in plans])

    with stage(report, report_scope + "pareto", "Pareto filter and stable next-action selection",
               {"crew_status": snapshot.crew_status, "exposure_slope_deg": exposure_slope_deg}) as record:
        front, used = compare_pareto(plans, router, exposure_slope_deg=exposure_slope_deg)
        recommendation = select_next_action(plans, front, snapshot)
        if report is not None:
            record.update(pareto_front=front, objectives_used=used,
                          candidates=[{"id": p.id, "objectives": p.objectives, "passed": p.passed} for p in plans],
                          recommendation=recommendation)

    if gate.status == MARGIN_NO_ROUTE:
        status = INSUFFICIENT_TERRAIN_EVIDENCE if direct.status == LEG_NO_EVIDENCE else NO_RETURN_ROUTE
    elif gate.status == MARGIN_OVER_RESERVE:
        status = RETURN_OVER_RESERVE
    else:
        blocked_rules = {rule: outcome for rule, outcome, _ in direct_plan.constraints if outcome != PASS}
        status = OK if direct_plan.passed else NO_RETURN_ROUTE
        if blocked_rules.get("environment") == UNKNOWN:
            status = RETURN_ENVIRONMENT_UNVERIFIED
        elif blocked_rules == {"energy_budget": UNKNOWN}:
            status = RETURN_ENERGY_UNVERIFIED
        elif blocked_rules == {"energy_budget": FAIL}:
            status = RETURN_ENERGY_SEARCH_EXHAUSTED
        elif blocked_rules in ({"walkback": FAIL}, {"walkback_resources": FAIL}):
            status = RETURN_WALKBACK_EXCEEDED

    alternatives = {}
    if alternatives_k > 1 and recommendation not in (None, "direct_return"):
        rec = next(p for p in plans if p.id == recommendation)
        outbound = rec.legs[0][1]
        feasible = []
        for alternative in diverse_routes(router, outbound.start, outbound.goal, k=alternatives_k):
            candidate = replace(rec, legs=[("outbound", alternative.leg), *rec.legs[1:]],
                                failure_reasons=[], deferred_artifacts=[])
            reevaluate_science_tasks([candidate], snapshot, router)
            enforce_hard_constraints(candidate, snapshot, router, direct_plan=direct_plan, **checks)
            if candidate.passed:
                rank = len(feasible)
                label = "baseline" if rank == 0 else f"alternate_{rank}"
                feasible.append(replace(alternative, rank=rank, label=label))
        alternatives[f"{rec.id}:outbound"] = feasible

    walk_summary = None
    if walk_router is not None:
        walk_home = walk_router.time_to_home(snapshot.return_cell)[tuple(snapshot.current_cell)]
        walk_summary = {"policy": walkback.to_dict(),
                        "walk_home_from_current_s": float(walk_home) if walk_home < float("inf") else None,
                        "per_plan": {p.id: walkback_rule(p, snapshot, router, walk_router)[2] for p in plans},
                        "dijkstra_runs": walk_router.dijkstra_runs}
    return MarswalkPlan(snapshot, baseline, router, status, gate, plans, front, used, recommendation, alternatives,
                        activations, site_gate, weather, walk_summary, horizon_s)
