"""T1 · Option table: Marswalk candidates -> ordered human-cost phases -> nominal ledgers.

One option per Marswalk ``CandidatePlan``. Legs become walking phases
(``seconds``, ``ascent_m``, ``length_m``, ``max_slope_deg``) and each dwell
becomes a dwell phase. ``humancost.evaluate()`` then prices the phases at
nominal rates. Nothing here classifies or changes a plan.

"No route" stays separate from "route exists but breaches a reserve":
``route_status`` is ``ok`` only when every leg is admissible, and only then
are ledgers computed.

The crew file's starting stores are read as the stores at the moment of the
assessment. Reconciling them with stores actually used earlier in the EVA is
P1 work (the burn-rate belief) and is not attempted here.
"""
from dataclasses import dataclass

from runtime.humancost import Phase, evaluate
from runtime.marswalk.errors import LEG_NO_EVIDENCE, LEG_OK, LEG_SEARCH_LIMIT, MarswalkError

from ._common import refuse

ROUTE_OK, NO_ROUTE, ROUTE_UNVERIFIED, LEDGER_UNAVAILABLE = "ok", "no_route", "route_unverified", "ledger_unavailable"


@dataclass(frozen=True)
class Option:
    id: str
    kind: str                    # direct_return | science | multi
    task_ids: tuple
    science_value: int
    route_status: str
    route_reason: str
    phases: tuple                # humancost Phase, ...
    human_cost: dict | None      # humancost.evaluate() payload; None unless route_status == "ok"
    plan: object                 # the Marswalk CandidatePlan (read only)


def phases_for(plan):
    """Ordered humancost phases for one candidate, or (None, reason) if a leg value is missing."""
    dwell, phases = dict(plan.dwell), []
    for name, leg in plan.legs:
        values = {"seconds": leg.seconds, "ascent_m": leg.ascent_m, "length_m": leg.length_m,
                  "max_slope_deg": leg.max_slope_deg}
        missing = sorted(k for k, value in values.items() if value is None)
        if missing:
            return None, f"{name} leg has no {', '.join(missing)}"
        phases.append(Phase(name, name, float(leg.seconds), float(leg.ascent_m),
                            distance_m=float(leg.length_m), max_slope_deg=float(leg.max_slope_deg)))
        if name in ("outbound", "transfer") and plan.task_ids:
            target = plan.task_ids[0] if name == "outbound" else plan.task_ids[1]
            phases.append(Phase(f"dwell:{target}", "dwell", float(dwell[target]), 0.0))
    return tuple(phases), ""


def build_options(marswalk_plan, crew, policy):
    """One Option per candidate, in the planner's order (direct_return first)."""
    if marswalk_plan.snapshot.profile.platform != "human":
        refuse("UNSUPPORTED_PLATFORM", "the option table prices walking EVAs only; rover plans are not supported")
    if not marswalk_plan.plans or marswalk_plan.plans[0].id != "direct_return":
        refuse("INVALID_PLAN", "the planner's first candidate must be direct_return")
    options = []
    for plan in marswalk_plan.plans:
        statuses = [leg.status for _, leg in plan.legs]
        base = (plan.id, plan.kind, tuple(plan.task_ids), int(plan.science_value))
        if any(status != LEG_OK for status in statuses):
            unverified = all(status in (LEG_OK, LEG_NO_EVIDENCE, LEG_SEARCH_LIMIT) for status in statuses)
            reason = "; ".join(f"{name} leg: {leg.status}" for name, leg in plan.legs if not leg.ok)
            options.append(Option(*base, ROUTE_UNVERIFIED if unverified else NO_ROUTE, reason, (), None, plan))
            continue
        phases, reason = phases_for(plan)
        if phases is None:
            options.append(Option(*base, LEDGER_UNAVAILABLE, reason, (), None, plan))
            continue
        try:
            payload = evaluate(crew, policy, list(phases))
        except MarswalkError as error:
            options.append(Option(*base, LEDGER_UNAVAILABLE, str(error), phases, None, plan))
            continue
        options.append(Option(*base, ROUTE_OK, "", phases, payload, plan))
    return options
