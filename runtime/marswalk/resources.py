"""Subsystem 07 · Resource budgets.

Boxes:
  * Compute return-time margin - B - R - travel for the direct return, keeping
    "no route" distinct from "route exists but eats the reserve".
  * Route resource ledger      - ordered phases (outbound, dwell, return, ...),
    per-phase use, remaining after each phase, reserve and signed margin.
    A prefix check runs after every phase: a good end balance can never hide
    an earlier depletion. A missing (None) use fails the check, never defaults.

Only TIME is modelled. Human consumables enter as the authorized remaining
time B supplied by the crew; no oxygen or physiology model is used here.
"""
from dataclasses import dataclass

from .errors import FAIL, PASS, UNKNOWN

MARGIN_OK = "ok"
MARGIN_OVER_RESERVE = "over_reserve"
MARGIN_NO_ROUTE = "no_route"


@dataclass(frozen=True)
class ReturnMargin:
    status: str
    travel_s: float | None
    margin_s: float | None

    def to_dict(self):
        return {"status": self.status, "travel_s": self.travel_s, "margin_s": self.margin_s}


def return_time_margin(remaining_s, reserve_s, direct_leg):
    """Signed margin of going home now: B - R - travel."""
    if direct_leg is None or not direct_leg.ok:
        return ReturnMargin(MARGIN_NO_ROUTE, None, None)
    margin = remaining_s - reserve_s - direct_leg.seconds
    return ReturnMargin(MARGIN_OK if margin >= 0 else MARGIN_OVER_RESERVE, direct_leg.seconds, margin)


@dataclass(frozen=True)
class Phase:
    name: str
    kind: str                 # outbound | dwell | transfer | return
    use_s: float | None


@dataclass(frozen=True)
class LedgerRow:
    name: str
    kind: str
    use_s: float | None
    remaining_s: float | None
    prefix_ok: bool | None


@dataclass(frozen=True)
class ResourceLedger:
    resource: str
    unit: str
    initial: float
    reserve: float
    rows: tuple
    total_use: float | None
    final_remaining: float | None
    margin: float | None
    check: str               # pass | fail | unknown
    reason: str

    def to_dict(self):
        return {"resource": self.resource, "unit": self.unit, "initial": self.initial,
                "reserve": self.reserve, "total_use": self.total_use, "final_remaining": self.final_remaining,
                "margin": self.margin, "check": self.check, "reason": self.reason,
                "rows": [r.__dict__ for r in self.rows]}


def route_resource_ledger(phases, *, initial_s, reserve_s):
    """Evaluate ordered phases against the time budget.
    Prefix rule: after every phase, enough must remain to cover the reserve."""
    rows, remaining, total = [], float(initial_s), 0.0
    check, reason = PASS, "fits within budget and reserve"
    for phase in phases:
        if phase.use_s is None:
            rows.append(LedgerRow(phase.name, phase.kind, None, None, None))
            check, reason, remaining, total = UNKNOWN, f"unsupported value in phase {phase.name}", None, None
            break
        remaining -= phase.use_s
        total += phase.use_s
        prefix_ok = remaining >= reserve_s
        rows.append(LedgerRow(phase.name, phase.kind, float(phase.use_s), remaining, prefix_ok))
        if not prefix_ok and check == PASS:
            check, reason = FAIL, f"reserve breached during {phase.name}"
    margin = None if remaining is None else remaining - reserve_s
    return ResourceLedger("time", "s", float(initial_s), float(reserve_s), tuple(rows),
                          total, remaining, margin, check, reason)
