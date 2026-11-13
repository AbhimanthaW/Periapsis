"""Subsystem 10 · Mission optimization.

Boxes, in order:
  * Compose candidate plans     - "return now" is always pinned; plus
                                  outbound -> one unfinished task -> return (P0)
  * Reevaluate science tasks    - every unfinished task, same closure and pace,
                                  both legs + dwell, signed margins, kept reasons
  * Enforce hard constraints    - pass / fail / unknown per rule; the direct-return
                                  gate runs before any science is recommended;
                                  an unknown required value blocks the plan
  * Compare Pareto alternatives - only passing plans, distinct objectives,
                                  never blended into one score
  * Select next action          - science priority, then margin, then stable id
  * Bounded multi-stop (P1)     - ordered 2-task sequences with a leg cache
  * Excluded from core          - no AI/ML, live telemetry, suit forecasts,
                                  safety scores, medical ranking or rescue assumptions
"""
from dataclasses import dataclass, field, replace
from itertools import permutations, product

import numpy as np

from .errors import FAIL, LEG_NO_EVIDENCE, LEG_OK, PASS, UNKNOWN
from .environment import ACTIVE, UNVERIFIED, supply_energy_j
from .resources import EnergyPhase, Phase, ResourceLedger, energy_ledger, route_resource_ledger

EXCLUDED_FROM_CORE = (
    "AI/ML decision making", "live telemetry", "suit or life-support forecasts",
    "universal safety scores", "medical suitability or crew ranking",
    "assumed rover or vehicle rescue", "unsupported global routing",
)


@dataclass
class CandidatePlan:
    id: str
    kind: str                         # direct_return | science | multi
    task_ids: tuple
    legs: list                        # [(name, Leg)]
    dwell: list = field(default_factory=list)   # [(task_id, seconds)]
    science_value: int = 0
    ledger: object = None
    constraints: list = field(default_factory=list)   # [(rule, outcome, reason)]
    objectives: dict = field(default_factory=dict)
    failure_reasons: list = field(default_factory=list)
    deferred_artifacts: list = field(default_factory=list)
    energy_ledger: object = None      # rover plans only

    @property
    def passed(self):
        return bool(self.constraints) and all(outcome == PASS for _, outcome, _ in self.constraints)

    @property
    def margin_s(self):
        return None if self.ledger is None else self.ledger.margin

    def to_dict(self):
        return {
            "id": self.id, "kind": self.kind, "task_ids": list(self.task_ids),
            "legs": [{"name": name, **leg.to_dict()} for name, leg in self.legs],
            "dwell": [{"task_id": t, "seconds": s} for t, s in self.dwell],
            "science_value": self.science_value,
            "ledger": None if self.ledger is None else self.ledger.to_dict(),
            "margin_s": self.margin_s, "passed": self.passed,
            "constraints": [{"rule": r, "outcome": o, "reason": why} for r, o, why in self.constraints],
            "objectives": self.objectives, "failure_reasons": self.failure_reasons,
            "deferred_artifacts": self.deferred_artifacts,
            "energy_ledger": None if self.energy_ledger is None else self.energy_ledger.to_dict(),
        }


# ------------------------------------------------------------------ compose
def compose_candidate_plans(snapshot, router, *, multistop=False):
    current, home = snapshot.current_cell, snapshot.return_cell
    plans = [CandidatePlan("direct_return", "direct_return", (), [("return", router.leg_return(current, home))])]
    done = set(snapshot.completed_task_ids)
    unfinished = [t for t in snapshot.tasks if t.id not in done]
    for task in unfinished:
        plans.append(CandidatePlan(
            f"science:{task.id}", "science", (task.id,),
            [("outbound", router.leg_outbound(current, task.approach_cell)),
             ("return", router.leg_return(task.approach_cell, home))],
            dwell=[(task.id, task.dwell_s)], science_value=task.priority))
    if multistop:
        plans.extend(bounded_multistop(snapshot, router, unfinished))
    return plans


def bounded_multistop(snapshot, router, unfinished, max_tasks=2):
    """P1: every ordered pair of unfinished tasks. Legs come from a cache of
    one forward run per task approach plus the shared fields."""
    if max_tasks != 2:
        raise ValueError("only two-task sequences are supported")
    current, home = snapshot.current_cell, snapshot.return_cell
    plans = []
    for first, second in permutations(unfinished, 2):
        plans.append(CandidatePlan(
            f"multi:{first.id}>{second.id}", "multi", (first.id, second.id),
            [("outbound", router.leg_outbound(current, first.approach_cell)),
             ("transfer", router.leg_outbound(first.approach_cell, second.approach_cell)),
             ("return", router.leg_return(second.approach_cell, home))],
            dwell=[(first.id, first.dwell_s), (second.id, second.dwell_s)],
            science_value=first.priority + second.priority))
    return plans


# ------------------------------------------------------------------ reevaluate
def _energy_ledger(plan, snapshot, router):
    """Check driving at edge resolution and science dwell as a stationary phase."""
    mobility = router.graph.mobility
    profile, dwell = mobility.profile, dict(plan.dwell)
    phases, t = [], 0.0
    ctx = dict(time_utc=snapshot.time_utc, lat_deg=snapshot.site_lat_deg,
               lon_east_deg=snapshot.site_lon_east_deg, baseline=router.baseline,
               max_charge_w=profile.max_charge_w)
    if any(leg.seconds or leg.edge_ids for _, leg in plan.legs) or any(dwell.values()):
        if profile.max_discharge_w is None or profile.max_charge_w is None:
            return ResourceLedger("energy", "J", profile.initial_charge_j, profile.battery_reserve_j,
                                  (), None, None, None, UNKNOWN, "battery power ratings are undeclared")

    def add(name, kind, consumption, duration, *, cell=None):
        nonlocal t
        if duration is None:
            phases.append(EnergyPhase(name, kind, None, None, None))
            return
        supply = supply_energy_j(snapshot.power, t, t + duration, stationary_cell=cell, **ctx)
        phases.append(EnergyPhase(name, kind, consumption, supply, duration))
        t += duration

    times = router.graph.times
    for name, leg in plan.legs:
        if leg.edge_ids:
            for index, edge in enumerate(leg.edge_ids, start=1):
                add(f"{name}:edge:{index}", name, float(times.energy_j[edge]), float(times.seconds[edge]))
        else:
            add(name, name, leg.energy_j, leg.seconds)
        if name in ("outbound", "transfer") and plan.task_ids:
            target = plan.task_ids[0] if name == "outbound" else plan.task_ids[1]
            add(f"dwell:{target}", "dwell", mobility.dwell_energy_j(dwell[target]), dwell[target], cell=leg.goal)
    return energy_ledger(phases, initial_j=profile.initial_charge_j, reserve_j=profile.battery_reserve_j,
                         capacity_j=profile.battery_capacity_j, max_discharge_w=profile.max_discharge_w)


def select_energy_feasible_legs(plan, snapshot, router, *, direct_plan=None, activations=()):
    """Try bounded time/energy combinations when the fastest plan fails energy."""
    ledger = plan.energy_ledger
    if (ledger is None or ledger.check != FAIL
            or any(outcome != PASS for rule, outcome, _ in plan.constraints if rule != "energy_budget")):
        return plan
    max_discharge_w = router.graph.mobility.profile.max_discharge_w
    choices = [[(name, route) for route in (leg, *router.energy_alternatives(leg, max_discharge_w))]
               for name, leg in plan.legs]
    routes = sorted(product(*choices), key=lambda legs: sum(leg.seconds for _, leg in legs))
    for legs in routes:
        if list(legs) == plan.legs:
            continue
        candidate = replace(plan, legs=list(legs), failure_reasons=[], deferred_artifacts=[])
        reevaluate_science_tasks([candidate], snapshot, router)
        enforce_hard_constraints(candidate, snapshot, router, direct_plan=direct_plan, activations=activations)
        if candidate.passed:
            return candidate
    plan.failure_reasons.append("bounded route search found no energy-feasible alternative")
    return plan


def reevaluate_science_tasks(plans, snapshot, router=None):
    """Ledger, signed margin and failure reasons for every plan (same scenario).
    Rover plans also get a battery ledger."""
    by_id = {t.id: t for t in snapshot.tasks}
    mobility = None if router is None else getattr(router.graph, "mobility", None)
    vehicle = mobility is not None and hasattr(mobility, "dwell_energy_j")
    for plan in plans:
        phases, dwell = [], dict(plan.dwell)
        for name, leg in plan.legs:
            phases.append(Phase(name, name, leg.seconds if leg.ok else None))
            if name in ("outbound", "transfer") and plan.task_ids:
                target = plan.task_ids[0] if name == "outbound" else plan.task_ids[1]
                phases.append(Phase(f"dwell:{target}", "dwell", dwell[target]))
            if not leg.ok:
                plan.failure_reasons.append(f"{name} leg: {leg.status} - {leg.reason}")
        plan.ledger = route_resource_ledger(phases, initial_s=snapshot.remaining_s, reserve_s=snapshot.reserve_s)
        if plan.ledger.check == FAIL:
            plan.failure_reasons.append(plan.ledger.reason)
        if vehicle:
            plan.energy_ledger = _energy_ledger(plan, snapshot, router)
        if plan.task_ids and (plan.ledger.check != PASS or any(not leg.ok for _, leg in plan.legs)):
            plan.deferred_artifacts = [by_id[t].expected_artifact or t for t in plan.task_ids]
    return plans


# ------------------------------------------------------------------ hard constraints
def _positions_rule(snapshot, router):
    outcomes = []
    for name, cell in (("current", snapshot.current_cell), ("return", snapshot.return_cell)):
        if router.baseline.known_excluded[cell] or router.closed[cell]:
            outcomes.append((FAIL, f"{name} cell is excluded or closed"))
        elif router.baseline.unknown[cell]:
            outcomes.append((UNKNOWN, f"{name} cell has insufficient terrain evidence"))
    if any(o == FAIL for o, _ in outcomes):
        return FAIL, "; ".join(r for _, r in outcomes)
    if outcomes:
        return UNKNOWN, "; ".join(r for _, r in outcomes)
    return PASS, "current and return cells supported"


def _environment_rule(activations):
    """Only active restrictions apply. Required unverified inputs stay unknown."""
    stop = [a for a in activations if a.status == ACTIVE and a.effect == "return_now"]
    if stop:
        return FAIL, "return now required by " + ", ".join(a.id for a in stop)
    unverified = [a for a in activations if a.status == UNVERIFIED and a.required]
    if unverified:
        return UNKNOWN, "unverified_environment: " + ", ".join(a.id for a in unverified)
    return PASS, "no active environmental restriction"


def enforce_hard_constraints(plan, snapshot, router, *, direct_plan=None, activations=()):
    rules = []
    rules.append(("positions_supported", *_positions_rule(snapshot, router)))
    if plan.kind != "direct_return":
        rules.append(("crew_status", *((PASS, "crew status ok") if snapshot.crew_status == "ok"
                                        else (FAIL, "crew reported an issue: return now"))))
        rules.append(("environment", *_environment_rule(activations)))
        if direct_plan.passed:
            rules.append(("direct_return_gate", PASS, "direct return passes all required constraints"))
        else:
            blocking = ", ".join(rule for rule, outcome, _ in direct_plan.constraints if outcome != PASS)
            rules.append(("direct_return_gate", FAIL, f"direct return is blocked by {blocking}"))
    else:
        required_closures = [a for a in activations if a.effect == "block_cells" and a.required]
        if required_closures:
            rules.append(("environment", *_environment_rule(required_closures)))
    statuses = [leg.status for _, leg in plan.legs]
    if all(s == LEG_OK for s in statuses):
        rules.append(("path_exists", PASS, "all legs admissible"))
    elif any(s == LEG_NO_EVIDENCE for s in statuses) and all(s in (LEG_OK, LEG_NO_EVIDENCE) for s in statuses):
        rules.append(("path_exists", UNKNOWN, "a leg needs unverified terrain"))
    else:
        rules.append(("path_exists", FAIL, "a leg has no admissible path"))
    if plan.task_ids:
        by_id = {t.id: t for t in snapshot.tasks}
        satisfied = set(snapshot.completed_task_ids)
        missing = []
        for tid in plan.task_ids:
            missing += [p for p in by_id[tid].prerequisites if p not in satisfied]
            satisfied.add(tid)
        rules.append(("prerequisites", FAIL if missing else PASS,
                      f"missing prerequisites {missing}" if missing else "prerequisites met"))
    rules.append(("time_budget", plan.ledger.check, plan.ledger.reason))
    if plan.energy_ledger is not None:
        reason = plan.energy_ledger.reason
        if plan.energy_ledger.check == UNKNOWN and snapshot.power is None:
            reason = "no power scenario declared for the vehicle"
        rules.append(("energy_budget", plan.energy_ledger.check, reason))
    max_leg = snapshot.limit("max_leg_s")
    if max_leg is not None:
        worst = max((leg.seconds for _, leg in plan.legs if leg.ok), default=None)
        if worst is None:
            rules.append(("max_leg_s", UNKNOWN, "no admissible leg to check"))
        else:
            ok = worst <= max_leg.value
            rules.append(("max_leg_s", PASS if ok else FAIL,
                          f"longest leg {worst:.0f} s vs limit {max_leg.value:.0f} s ({max_leg.authorized_by})"))
    plan.constraints = rules
    for rule, outcome, reason in rules:
        if outcome != PASS and reason not in plan.failure_reasons:
            plan.failure_reasons.append(f"{rule}: {reason}")
    return plan


# ------------------------------------------------------------------ Pareto
OBJECTIVES = (("total_s", "min"), ("margin_s", "max"), ("science_value", "max"), ("steep_exposure_s", "min"),
              ("energy_j", "min"))


def _exposure(plan, router, threshold_deg):
    slope = np.asarray(router.baseline.slope_deg).ravel()
    total = 0.0
    for _, leg in plan.legs:
        if not leg.ok or not leg.edge_ids:
            continue
        eids = np.asarray(leg.edge_ids)
        dest = slope[router.graph.dst[eids]]
        if not np.isfinite(dest).all():
            return None
        total += float(router.graph.times.seconds[eids][dest > threshold_deg].sum())
    return total


def compare_pareto(plans, router, *, exposure_slope_deg=10.0):
    """Return (front_ids, objectives_used). Objectives are computed for every
    passing plan; one that is unavailable for any plan is dropped for all."""
    passing = [p for p in plans if p.passed]
    for plan in passing:
        plan.objectives = {
            "total_s": plan.ledger.total_use, "margin_s": plan.ledger.margin,
            "science_value": plan.science_value,
            "steep_exposure_s": _exposure(plan, router, exposure_slope_deg),
            "energy_j": None if plan.energy_ledger is None else plan.energy_ledger.total_use,
        }
    used = [(name, sense) for name, sense in OBJECTIVES
            if passing and all(p.objectives[name] is not None for p in passing)]

    def oriented(plan):
        return [plan.objectives[n] if s == "max" else -plan.objectives[n] for n, s in used]

    front = []
    for a in passing:
        va = oriented(a)
        dominated = any(all(x >= y - 1e-9 for x, y in zip(oriented(b), va))
                        and any(x > y + 1e-9 for x, y in zip(oriented(b), va))
                        for b in passing if b is not a)
        if not dominated:
            front.append(a.id)
    return sorted(front), [n for n, _ in used]


# ------------------------------------------------------------------ select
def select_next_action(plans, front_ids, snapshot):
    """Highest science priority, then greatest margin, then stable id. If no
    science plan qualifies, return now when the direct return is admissible."""
    if not plans[0].passed:
        return None
    front = [p for p in plans if p.id in front_ids and p.kind != "direct_return"]
    if snapshot.crew_status == "ok" and front:
        best = min(front, key=lambda p: (-p.science_value, -p.ledger.margin, p.id))
        return best.id
    return "direct_return"
