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
from dataclasses import dataclass, field, replace

from .errors import (INSUFFICIENT_TERRAIN_EVIDENCE, LEG_NO_EVIDENCE, MarswalkError, NO_RETURN_ROUTE, OK,
                     RETURN_OVER_RESERVE)
from .environment import (ACTIVE, activate_environment, comms_and_forecast_assessment, mars_sun,
                          terrain_illumination)
from .mobility import pace_for
from .optimization import (EXCLUDED_FROM_CORE, compare_pareto, compose_candidate_plans,
                           enforce_hard_constraints, reevaluate_science_tasks, select_next_action)
from .resources import MARGIN_NO_ROUTE, MARGIN_OVER_RESERVE, return_time_margin
from .routing import Router, TerrainGraph, diverse_routes

SCHEMA = "marswalk-plan-v1"
ASSUMPTIONS = (
    "Pace parameters are illustrative scenario assumptions, not calibrated Mars-suit walking data.",
    "Slope and roughness thresholds are prototype policy assumptions and do not establish human safety.",
    "Only crew time is budgeted for people; consumables enter as the authorized remaining time supplied by the crew.",
    "Rover numbers come from a hypothetical or cited vehicle record; no equivalence to NASA rover specifications.",
    "Rover energy credits no regeneration; traction, slip and sinkage are not modelled.",
    "Historical weather and radiation are context only; no forecast or human dose is inferred.",
    "The return check assumes no rescue or vehicle support.",
    "Closures and scenario events are simulated field reports unless tagged as evidence.",
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

    @property
    def pareto_front(self):
        return self.front

    @property
    def direct_leg(self):
        return self.plans[0].legs[0][1]

    def plan(self, plan_id):
        return next(p for p in self.plans if p.id == plan_id)

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
            "solver": {"backend": self.router.backend, "dijkstra_runs": self.router.dijkstra_runs,
                       "edges": len(self.router.graph), "cells": int(self.router.graph.n)},
            "provenance": [list(p) for p in snap.provenance],
            "environment": self._environment_dict(),
            "assumptions": list(ASSUMPTIONS), "excluded_from_core": list(EXCLUDED_FROM_CORE),
        }


def _profile_dict(prof):
    if prof.platform == "rover":
        from .rover import summary, traction_assessment
        return {**summary(prof), "neighbours": prof.neighbours, "traction": traction_assessment(prof)}
    return {"profile_id": prof.profile_id, "pace_model": prof.pace_model, "pace_scenario": prof.pace_scenario,
            "neighbours": prof.neighbours, "crew_size": prof.crew_size, "provenance": prof.provenance}


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
    sun = mars_sun(snap.time_utc, snap.site_lat_deg, snap.site_lon_east_deg)
    cells = {"current": snap.current_cell, "return": snap.return_cell,
             **{f"task:{t.id}": t.approach_cell for t in snap.tasks}}
    lit = terrain_illumination(self.baseline, list(cells.values()), sun)
    out["solar"] = {"status": "computed", "method": "Mars24 (Allison & McEwen 2000)", "sun": sun.to_dict(),
                    "illumination": {name: lit[tuple(c)] for name, c in cells.items()}}
    return out


MarswalkPlan._environment_dict = _environment_dict


def plan_marswalk(baseline, snapshot, *, backend="auto", multistop=False, exposure_slope_deg=10.0,
                  alternatives_k=0, expected_revision=None):
    """Run the whole Human Marswalk path for one immutable snapshot."""
    support = baseline.support
    if not support.pack_version:
        raise MarswalkError("MIXED_PACK", "loaded terrain must declare its pack version")
    snapshot.validate(support.shape, pack_id=support.pack_id, pack_version=support.pack_version,
                      expected_revision=expected_revision)
    profile = snapshot.profile
    activations = tuple(activate_environment(snapshot.environment, time_utc=snapshot.time_utc))
    blocked = tuple(cell for v, a in zip(snapshot.environment, activations)
                    if a.status == ACTIVE and a.effect == "block_cells" for cell in v.cells)
    graph = TerrainGraph(baseline, pace_for(profile), scenario=getattr(profile, "pace_scenario", "nominal"),
                         neighbours=profile.neighbours)
    router = Router(graph, snapshot.closure_cells + blocked, backend=backend)

    plans = compose_candidate_plans(snapshot, router, multistop=multistop)
    reevaluate_science_tasks(plans, snapshot, router)
    direct_plan = plans[0]
    direct = direct_plan.legs[0][1]
    gate = return_time_margin(snapshot.remaining_s, snapshot.reserve_s, direct)
    enforce_hard_constraints(direct_plan, snapshot, router, activations=activations)
    for plan in plans[1:]:
        enforce_hard_constraints(plan, snapshot, router, direct_plan=direct_plan, activations=activations)
    front, used = compare_pareto(plans, router, exposure_slope_deg=exposure_slope_deg)
    recommendation = select_next_action(plans, front, snapshot)

    if gate.status == MARGIN_NO_ROUTE:
        status = INSUFFICIENT_TERRAIN_EVIDENCE if direct.status == LEG_NO_EVIDENCE else NO_RETURN_ROUTE
    elif gate.status == MARGIN_OVER_RESERVE:
        status = RETURN_OVER_RESERVE
    else:
        status = OK if direct_plan.passed else NO_RETURN_ROUTE

    alternatives = {}
    if alternatives_k > 1 and recommendation not in (None, "direct_return"):
        rec = next(p for p in plans if p.id == recommendation)
        outbound = rec.legs[0][1]
        feasible = []
        for alternative in diverse_routes(router, outbound.start, outbound.goal, k=alternatives_k):
            candidate = replace(rec, legs=[("outbound", alternative.leg), *rec.legs[1:]],
                                failure_reasons=[], deferred_artifacts=[])
            reevaluate_science_tasks([candidate], snapshot, router)
            enforce_hard_constraints(candidate, snapshot, router, direct_plan=direct_plan, activations=activations)
            if candidate.passed:
                rank = len(feasible)
                label = "baseline" if rank == 0 else f"alternate_{rank}"
                feasible.append(replace(alternative, rank=rank, label=label))
        alternatives[f"{rec.id}:outbound"] = feasible
    return MarswalkPlan(snapshot, baseline, router, status, gate, plans, front, used, recommendation, alternatives,
                        activations)
