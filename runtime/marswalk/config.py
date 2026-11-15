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
import math
from math import inf
from numbers import Real

from .errors import MarswalkError

# Mars Tobler shape and walk-to-run limit (runtime/docs/mars-tobler-pace.md). A
# profile whose fastest speed exceeds the limit is rejected, never clamped.
TOBLER_K = 3.5
TOBLER_OFFSET = 0.05
WALK_TO_RUN_CAP_MPS = 1.16       # sqrt(Fr* 0.36 x 3.721 m/s2 x 1 m leg), lunar suited Fr*

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
        if self.id != "max_leg_s" or self.scope != "mission":
            raise MarswalkError("INVALID_LIMIT", "only the mission-wide max_leg_s limit is supported")
        if self.unit != "s" or not self.authorized_by:
            raise MarswalkError("INVALID_LIMIT", "max_leg_s requires seconds (s) and authorized_by")
        if isinstance(self.value, bool) or not isinstance(self.value, Real) or not 0 <= self.value < inf:
            raise MarswalkError("INVALID_LIMIT", "max_leg_s must be finite and non-negative")


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
    v_flat_mps: float = 0.5                    # Mars Tobler flat speed (runtime/docs/mars-tobler-pace.md)
    max_slope_deg: float | None = None         # walking slope limit on edges and cells; None = terrain policy only

    def __post_init__(self):
        if self.platform != "human":
            raise MarswalkError("INVALID_PROFILE", "Human Marswalk accepts only a human profile")
        _positive("v_flat_mps", self.v_flat_mps)
        if self.max_slope_deg is not None:
            _positive("max_slope_deg", self.max_slope_deg)
            if self.max_slope_deg >= 90:
                raise MarswalkError("INVALID_PROFILE", "max_slope_deg must be below 90")
            if self.pace_model != "tobler_scaled":
                raise MarswalkError("INVALID_PROFILE", "max_slope_deg requires the tobler_scaled pace model")
        fastest = self.v_flat_mps * math.exp(TOBLER_K * TOBLER_OFFSET)
        if self.pace_model == "tobler_scaled" and fastest > WALK_TO_RUN_CAP_MPS:
            raise MarswalkError("INVALID_PROFILE", f"fastest walking speed {fastest:.2f} m/s exceeds the "
                                                   f"{WALK_TO_RUN_CAP_MPS} m/s walk-to-run limit")
        if self.pace_model not in {"tobler_scaled", "control_linear"}:
            raise MarswalkError("INVALID_PROFILE", f"unknown pace model {self.pace_model!r}")
        if self.pace_scenario not in {"nominal", "slow"}:
            raise MarswalkError("INVALID_PROFILE", f"unknown pace scenario {self.pace_scenario!r}")
        if self.neighbours not in {4, 8}:
            raise MarswalkError("INVALID_PROFILE", "neighbours must be 4 or 8")
        if type(self.crew_size) is not int or self.crew_size < 1:
            raise MarswalkError("INVALID_PROFILE", "crew_size must be a positive integer")
        _tag("profile", self.provenance)


def _positive(name, value, *, allow_zero=False):
    ok = (not isinstance(value, bool) and isinstance(value, Real) and value < inf
          and (value >= 0 if allow_zero else value > 0))
    if not ok:
        raise MarswalkError("INVALID_PROFILE", f"{name} must be finite and {'>= 0' if allow_zero else '> 0'}")
    return value


@dataclass(frozen=True)
class RoverProfile:
    """Tagged vehicle record (Subsystem 01, Rover operating profile).

    Either hypothetical or explicitly sourced. No equivalence to any NASA
    rover is assumed. Generic, solar and non-solar vehicles share this shape;
    generation itself comes from a declared PowerScenario (Subsystem 06)."""

    profile_id: str
    source_type: str                 # "hypothetical" | "sourced"
    mass_kg: float
    payload_kg: float
    wheel_radius_m: float
    clearance_m: float
    max_incline_deg: float           # applies to along-edge grade and local tilt
    nominal_speed_mps: float
    rolling_resistance: float        # dimensionless coefficient, declared
    drivetrain_efficiency: float     # 0 < eta <= 1
    auxiliary_power_w: float         # computers, heaters, radios while driving
    science_power_w: float           # stationary load while the crew works
    battery_capacity_j: float
    battery_reserve_j: float
    initial_charge_j: float
    power_source: str                # "solar" | "non_solar" | "none"
    source: str = ""
    neighbours: int = 8
    platform: str = "rover"
    provenance: str = "assumed"
    max_charge_w: float | None = None
    max_discharge_w: float | None = None
    max_cross_slope_deg: float | None = None
    drive_slip_fraction: float = 0.0

    def __post_init__(self):
        if self.platform != "rover":
            raise MarswalkError("INVALID_PROFILE", "RoverProfile must have platform 'rover'")
        if self.source_type not in {"hypothetical", "sourced"}:
            raise MarswalkError("INVALID_PROFILE", "source_type must be 'hypothetical' or 'sourced'")
        if self.source_type == "sourced" and not self.source:
            raise MarswalkError("INVALID_PROFILE", "a sourced vehicle record must cite its source")
        if self.power_source not in {"solar", "non_solar", "none"}:
            raise MarswalkError("INVALID_PROFILE", "power_source must be solar, non_solar or none")
        if self.neighbours not in {4, 8}:
            raise MarswalkError("INVALID_PROFILE", "neighbours must be 4 or 8")
        for name in ("mass_kg", "wheel_radius_m", "clearance_m", "nominal_speed_mps", "battery_capacity_j"):
            _positive(name, getattr(self, name))
        for name in ("payload_kg", "rolling_resistance", "auxiliary_power_w", "science_power_w",
                     "battery_reserve_j", "initial_charge_j"):
            _positive(name, getattr(self, name), allow_zero=True)
        for name in ("max_charge_w", "max_discharge_w"):
            if getattr(self, name) is not None:
                _positive(name, getattr(self, name), allow_zero=True)
        _positive("max_incline_deg", self.max_incline_deg)
        if self.max_incline_deg >= 90:
            raise MarswalkError("INVALID_PROFILE", "max_incline_deg must be below 90")
        if self.max_cross_slope_deg is not None:
            _positive("max_cross_slope_deg", self.max_cross_slope_deg)
            if self.max_cross_slope_deg >= 90:
                raise MarswalkError("INVALID_PROFILE", "max_cross_slope_deg must be below 90")
        _positive("drive_slip_fraction", self.drive_slip_fraction, allow_zero=True)
        if self.drive_slip_fraction >= 1:
            raise MarswalkError("INVALID_PROFILE", "drive_slip_fraction must be below 1")
        _positive("drivetrain_efficiency", self.drivetrain_efficiency)
        if self.drivetrain_efficiency > 1:
            raise MarswalkError("INVALID_PROFILE", "drivetrain_efficiency must be at most 1")
        if not self.battery_reserve_j <= self.initial_charge_j <= self.battery_capacity_j:
            raise MarswalkError("INVALID_PROFILE", "need reserve <= initial charge <= capacity")
        _tag("rover profile", self.provenance)


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
    # Subsystem 06 inputs (all optional; absent means "not declared", never guessed)
    time_utc: str | None = None          # plan start, ISO 8601 UTC, e.g. "2021-02-18T20:55:00Z"
    site_lat_deg: float | None = None    # planetocentric latitude of the grid
    site_lon_east_deg: float | None = None
    environment: tuple = ()              # EnvironmentalVariable, ...
    power: object = None                 # PowerScenario (rover plans need one)
    weather: object = None               # WeatherFeed from base stations; judged at time_utc

    def limit(self, limit_id):
        for item in self.limits:
            if item.id == limit_id:
                return item
        return None

    @property
    def closure_cells(self):
        return tuple(cell for _, cells in self.closures for cell in cells)

    def __post_init__(self):
        for name in ("current_cell", "return_cell"):
            cell = getattr(self, name)
            if isinstance(cell, list):
                object.__setattr__(self, name, tuple(cell))

    def validate(self, shape, *, pack_id=None, pack_version=None, expected_revision=None):
        """Refuse mixed packs, bad positions, invalid units, negative reserves,
        invalid profiles and stale revisions. Returns self for chaining."""
        if pack_id is not None and pack_id != self.pack_id:
            raise MarswalkError("MIXED_PACK", f"snapshot pack {self.pack_id!r} != loaded pack {pack_id!r}")
        if pack_version is not None and pack_version != self.pack_version:
            raise MarswalkError("MIXED_PACK",
                                f"snapshot pack version {self.pack_version!r} != loaded version {pack_version!r}")
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
        if not isinstance(self.profile, (HumanProfile, RoverProfile)):
            raise MarswalkError("INVALID_PROFILE", "profile must be a HumanProfile or RoverProfile")
        if self.time_utc is not None:
            from .environment import parse_utc
            parse_utc(self.time_utc)
        if (self.site_lat_deg is None) != (self.site_lon_east_deg is None):
            raise MarswalkError("INVALID_SNAPSHOT", "declare both site latitude and longitude, or neither")
        if self.site_lat_deg is not None:
            if not -90 <= self.site_lat_deg <= 90 or not -360 <= self.site_lon_east_deg <= 360:
                raise MarswalkError("INVALID_SNAPSHOT", "site coordinates out of range")
        env_ids = [v.id for v in self.environment]
        if len(set(env_ids)) != len(env_ids):
            raise MarswalkError("INVALID_SNAPSHOT", "duplicate environmental variable id")
        for variable in self.environment:
            for cell in variable.cells:
                _cell(f"environment {variable.id}", cell, shape)
        if self.weather is not None:
            if self.time_utc is None:
                raise MarswalkError("INVALID_SNAPSHOT", "a weather feed needs time_utc to judge message age")
            self.weather.validate(shape)
        if isinstance(self.profile, RoverProfile) and self.power is not None:
            self.power.validate_source(self.profile.power_source)
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
