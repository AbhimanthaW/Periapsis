"""Subsystem 01 · Mission configuration.

Boxes implemented here:
  * Mission snapshot            - one immutable, versioned record per request
  * Human operating profile     - tagged human profile (pace model, scenario, movement)
  * Authorized operating limits - who set each hard rule, its unit, scope and source

The snapshot never invents values: unknown required inputs are refused, not
defaulted. Every value carries a provenance tag so simulated events can never
be mistaken for evidence. Medical suitability, crew ranking and rescue
assumptions are deliberately absent (see "Excluded from core" in the README).
"""
from dataclasses import dataclass, field

from .errors import MarswalkError

MAX_SECONDS = 86_400
PROVENANCE = frozenset({"evidence", "authorized", "assumed", "simulated", "crew_input"})
CREW_STATUS = frozenset({"ok", "issue"})


def _seconds(name, value):
    if type(value) is not int or not 0 <= value <= MAX_SECONDS:
        raise MarswalkError("INVALID_UNITS", f"{name} must be whole seconds from 0 to {MAX_SECONDS}")
    return value


def _cell(name, cell, shape=None):
    if (not isinstance(cell, (tuple, list)) or len(cell) != 2
            or any(type(v) is not int or v < 0 for v in cell)):
        raise MarswalkError("BAD_POSITION", f"{name} must be a [row, col] pair of non-negative integers")
    if shape is not None and not (cell[0] < shape[0] and cell[1] < shape[1]):
        raise MarswalkError("BAD_POSITION", f"{name} {list(cell)} is outside the grid {list(shape)}")
    return tuple(cell)


def _tag(name, provenance):
    if provenance not in PROVENANCE:
        raise MarswalkError("INVALID_PROVENANCE", f"{name}: {provenance!r} not in {sorted(PROVENANCE)}")
    return provenance


@dataclass(frozen=True)
class AuthorizedLimit:
    """One hard rule and who stands behind it."""

    id: str
    value: float
    unit: str
    authorized_by: str
    scope: str = "mission"
    source: str = ""
    provenance: str = "assumed"

    def __post_init__(self):
        _tag(f"limit {self.id}", self.provenance)
        if not self.id or not self.unit or not self.authorized_by:
            raise MarswalkError("INVALID_LIMIT", "limits need id, unit and authorized_by")


@dataclass(frozen=True)
class HumanProfile:
    """Tagged human operating profile. The pace model lives in Subsystem 04;
    this record only says which one is authorized for the request."""

    profile_id: str = "human-pair-illustrative"
    platform: str = "human"
    pace_model: str = "tobler_scaled"          # or "control_linear" (fixture software control)
    pace_scenario: str = "nominal"             # "nominal" or "slow"
    neighbours: int = 8
    crew_size: int = 2
    provenance: str = "assumed"

    def __post_init__(self):
        if self.platform != "human":
            raise MarswalkError("INVALID_PROFILE", "Human Marswalk accepts only a human profile")
        if self.pace_model not in {"tobler_scaled", "control_linear"}:
            raise MarswalkError("INVALID_PROFILE", f"unknown pace model {self.pace_model!r}")
        if self.pace_scenario not in {"nominal", "slow"}:
            raise MarswalkError("INVALID_PROFILE", f"unknown pace scenario {self.pace_scenario!r}")
        if self.neighbours not in {4, 8}:
            raise MarswalkError("INVALID_PROFILE", "neighbours must be 4 or 8")
        if type(self.crew_size) is not int or self.crew_size < 1:
            raise MarswalkError("INVALID_PROFILE", "crew_size must be a positive integer")
        _tag("profile", self.provenance)


@dataclass(frozen=True)
class Task:
    id: str
    approach_cell: tuple
    dwell_s: int
    priority: int
    objective: str = ""
    expected_artifact: str = ""
    evidence_id: str = ""
    prerequisites: tuple = ()


@dataclass(frozen=True)
class MissionSnapshot:
    """Everything one planning request is allowed to read. Immutable."""

    mission_id: str
    revision: int
    pack_id: str
    pack_version: str
    scenario_id: str
    current_cell: tuple
    return_cell: tuple
    tasks: tuple
    completed_task_ids: tuple
    remaining_s: int
    reserve_s: int
    closures: tuple = ()                 # ((closure_id, ((r, c), ...)), ...) - simulated field reports
    profile: HumanProfile = field(default_factory=HumanProfile)
    limits: tuple = ()                   # AuthorizedLimit, ...
    crew_status: str = "ok"
    objective: str = ""
    config_version: str = "marswalk-config-v1"
    provenance: tuple = ()               # (("remaining_s", "crew_input"), ...)

    def limit(self, limit_id):
        for item in self.limits:
            if item.id == limit_id:
                return item
        return None

    @property
    def closure_cells(self):
        return tuple(cell for _, cells in self.closures for cell in cells)

    def validate(self, shape, *, pack_id=None, expected_revision=None):
        """Refuse mixed packs, bad positions, invalid units, negative reserves,
        invalid profiles and stale revisions. Returns self for chaining."""
        if pack_id is not None and pack_id != self.pack_id:
            raise MarswalkError("MIXED_PACK", f"snapshot pack {self.pack_id!r} != loaded pack {pack_id!r}")
        if type(self.revision) is not int or self.revision < 1:
            raise MarswalkError("STALE_REVISION", "revision must be a positive integer")
        if expected_revision is not None and self.revision != expected_revision:
            raise MarswalkError("STALE_REVISION", f"revision {self.revision} != current {expected_revision}")
        _seconds("remaining_s", self.remaining_s)
        _seconds("reserve_s", self.reserve_s)
        _cell("current_cell", self.current_cell, shape)
        _cell("return_cell", self.return_cell, shape)
        if self.crew_status not in CREW_STATUS:
            raise MarswalkError("INVALID_SNAPSHOT", f"crew_status must be one of {sorted(CREW_STATUS)}")
        ids = [task.id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise MarswalkError("INVALID_SNAPSHOT", "duplicate task id")
        for task in self.tasks:
            _cell(f"task {task.id}", task.approach_cell, shape)
            _seconds(f"task {task.id} dwell_s", task.dwell_s)
            if type(task.priority) is not int:
                raise MarswalkError("INVALID_SNAPSHOT", f"task {task.id} priority must be an integer")
            if set(task.prerequisites) - set(ids):
                raise MarswalkError("INVALID_SNAPSHOT", f"task {task.id} has unknown prerequisites")
        if set(self.completed_task_ids) - set(ids):
            raise MarswalkError("INVALID_SNAPSHOT", "completed task ids must refer to known tasks")
        closure_ids = [cid for cid, _ in self.closures]
        if len(set(closure_ids)) != len(closure_ids):
            raise MarswalkError("INVALID_SNAPSHOT", "duplicate closure id")
        for cid, cells in self.closures:
            for cell in cells:
                _cell(f"closure {cid}", cell, shape)
        seen = {}
        for item in self.limits:
            if item.id in seen and seen[item.id] != (item.value, item.unit):
                raise MarswalkError("CONFLICTING_LIMITS", f"limit {item.id} has conflicting values")
            seen[item.id] = (item.value, item.unit)
        for name, tag in self.provenance:
            _tag(name, tag)
        return self


def snapshot_from_pack(pack, *, closure_ids=(), remaining_s=None, revision=1,
                       profile=None, limits=(), crew_status="ok", mission_id="marswalk-demo"):
    """Freeze a mission snapshot from a checked pack v1 (`contracts.pack.CheckedPack`)."""
    if pack.scenario is None:
        raise MarswalkError("CAPABILITY_UNAVAILABLE", "pack has no scenario; load it with routing simulation enabled")
    scenario = pack.scenario
    named = {item["id"]: tuple(tuple(cell) for cell in item["cells"]) for item in scenario["closures"]}
    if len(set(closure_ids)) != len(closure_ids) or set(closure_ids) - named.keys():
        raise MarswalkError("INVALID_SNAPSHOT", "unknown or duplicate closure")
    tasks = tuple(Task(id=t["id"], approach_cell=tuple(t["approach_cell"]), dwell_s=int(t["dwell_s"]),
                       priority=int(t["priority"]), objective=t.get("objective", ""),
                       expected_artifact=t.get("expected_artifact", ""), evidence_id=t.get("evidence_id", ""))
                  for t in pack.stations)
    remaining = scenario["remaining_s"] if remaining_s is None else remaining_s
    return MissionSnapshot(
        mission_id=mission_id, revision=revision, pack_id=pack.site["pack_id"],
        pack_version=pack.site["pack_version"], scenario_id=scenario["scenario_id"],
        current_cell=tuple(scenario["checkpoint"]["cell"]), return_cell=tuple(scenario["shelter"]["cell"]),
        tasks=tasks, completed_task_ids=tuple(scenario["completed_task_ids"]),
        remaining_s=remaining, reserve_s=scenario["reserve_s"],
        closures=tuple((cid, named[cid]) for cid in closure_ids),
        profile=profile or HumanProfile(), limits=tuple(limits), crew_status=crew_status,
        provenance=(("remaining_s", "crew_input" if remaining_s is not None else "simulated"),
                    ("reserve_s", "simulated"), ("closures", "simulated"),
                    ("terrain", "simulated" if pack.site["classification"] == "synthetic" else "evidence")),
    )
