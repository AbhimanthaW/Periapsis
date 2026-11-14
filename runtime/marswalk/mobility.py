"""Subsystem 04 · Human Marswalk - Human traversal time.

Turns a directed move (horizontal length, signed height change) into
non-negative seconds for the crew pair. Uphill and downhill differ, so the
routing graph is directed. All parameters are ILLUSTRATIVE scenario
assumptions, not calibrated Mars-suit walking data.

Models
------
tobler_scaled   v(g) = v_flat * exp(-k * (|g + offset| - offset))
                Tobler (1993) hiking-function shape, rescaled so v(0) = v_flat.
                v_flat = 0.5 m/s follows the traverse pace in NASA's lunar EVA
                optimisation example (NTRS 20240000165); not validated for Mars.
control_linear  seconds = length * base + ascent * max(dz, 0) + descent * max(-dz, 0)
                The existing fixture software control (1 s/m + 2 s per metre of
                ascent), kept so results can be checked against runtime.mission.

Pace scenario "slow" multiplies speed by 0.7 (e.g. 0.5 -> 0.35 m/s). A uniform scenario factor rescales every time equally, so it never changes
which route is fastest - only how long it takes.
"""
from dataclasses import dataclass
import math

import numpy as np

from .errors import MarswalkError

SCENARIO_SPEED_FACTOR = {"nominal": 1.0, "slow": 0.7}

# Per-edge tags of the shared mobility contract
TAG_OK = 0
TAG_REFUSED_GRADE = 1          # along-edge grade or local tilt above the profile limit
TAG_UNSUPPORTED = 2            # a required terrain property has no support at this edge
TAG_CLEARANCE = 3              # local relief above the vehicle's ground clearance


@dataclass(frozen=True)
class EdgeTimes:
    """Tagged per-edge result handed to Terrain routing (09)."""

    seconds: np.ndarray      # float64, > 0 where usable, inf where refused
    tag: np.ndarray          # uint8 TAG_* per edge
    model: str
    params: tuple
    energy_j: np.ndarray | None = None   # rover profiles only: electrical J per edge


@dataclass(frozen=True)
class ToblerScaled:
    v_flat_mps: float = 0.5
    k: float = 3.5
    offset: float = 0.05
    max_abs_grade: float | None = None
    name: str = "tobler_scaled"

    @property
    def max_speed_mps(self):
        return self.v_flat_mps * math.exp(self.k * self.offset)

    def seconds(self, length_m, dz_m):
        grade = dz_m / length_m
        speed = self.v_flat_mps * np.exp(-self.k * (np.abs(grade + self.offset) - self.offset))
        return length_m / speed


@dataclass(frozen=True)
class SlopeLimitedTobler:
    """Mars Tobler with a walking slope limit. Refuses an edge when its own
    grade or either end cell's Horn slope exceeds the limit, and marks it
    unsupported when an end cell has no slope estimate (fail closed). The
    pace scenario factor is already folded into v_flat_mps."""

    v_flat_mps: float
    max_slope_deg: float
    k: float = 3.5
    offset: float = 0.05
    name: str = "tobler_slope_limited"

    def edge_times(self, length_m, dz_m, src, dst, baseline):
        length_m = np.asarray(length_m, float)
        dz_m = np.asarray(dz_m, float)
        if np.any(length_m <= 0) or not np.all(np.isfinite(dz_m)):
            raise MarswalkError("INVALID_TERRAIN", "edge lengths must be positive and height changes finite")
        seconds = ToblerScaled(self.v_flat_mps, self.k, self.offset).seconds(length_m, dz_m)
        slope = np.asarray(baseline.slope_deg, float).ravel()
        s_src, s_dst = slope[src], slope[dst]
        tag = np.full(seconds.shape, TAG_OK, dtype=np.uint8)
        unsupported = ~np.isfinite(s_src) | ~np.isfinite(s_dst)
        grade_deg = np.degrees(np.arctan(np.abs(dz_m / length_m)))
        with np.errstate(invalid="ignore"):
            steep = (grade_deg > self.max_slope_deg) | (s_src > self.max_slope_deg) | (s_dst > self.max_slope_deg)
        tag[steep & ~unsupported] = TAG_REFUSED_GRADE
        tag[unsupported] = TAG_UNSUPPORTED
        seconds = np.where(tag == TAG_OK, seconds, np.inf)
        params = (("k", self.k), ("max_slope_deg", self.max_slope_deg), ("offset", self.offset),
                  ("v_flat_mps", self.v_flat_mps))
        return EdgeTimes(seconds=seconds.astype(float), tag=tag, model=self.name, params=params)


@dataclass(frozen=True)
class ControlLinear:
    base_s_per_m: float = 1.0
    ascent_s_per_m: float = 2.0
    descent_s_per_m: float = 0.0
    max_abs_grade: float | None = None
    name: str = "control_linear"

    def seconds(self, length_m, dz_m):
        return (length_m * self.base_s_per_m + self.ascent_s_per_m * np.maximum(dz_m, 0.0)
                + self.descent_s_per_m * np.maximum(-dz_m, 0.0))


def pace_for(profile):
    """Mobility model authorized by the operating profile (Subsystem 01).
    Human profiles get a pace model; rover profiles get Subsystem 05."""
    if getattr(profile, "platform", None) == "rover":
        from .rover import RoverMobility
        return RoverMobility(profile)
    if profile.pace_model == "tobler_scaled":
        v_flat = getattr(profile, "v_flat_mps", 0.5)
        limit = getattr(profile, "max_slope_deg", None)
        if limit is not None:
            return SlopeLimitedTobler(v_flat * SCENARIO_SPEED_FACTOR[profile.pace_scenario], limit)
        return ToblerScaled(v_flat_mps=v_flat)
    if profile.pace_model == "control_linear":
        return ControlLinear()
    raise MarswalkError("INVALID_PROFILE", profile.pace_model)


def human_traversal_time(length_m, dz_m, *, model, scenario="nominal"):
    """Vectorised directional seconds for candidate edges -> EdgeTimes."""
    if scenario not in SCENARIO_SPEED_FACTOR:
        raise MarswalkError("INVALID_PROFILE", f"unknown pace scenario {scenario!r}")
    length_m = np.asarray(length_m, dtype=float)
    dz_m = np.asarray(dz_m, dtype=float)
    if np.any(length_m <= 0) or not np.all(np.isfinite(dz_m)):
        raise MarswalkError("INVALID_TERRAIN", "edge lengths must be positive and height changes finite")
    seconds = model.seconds(length_m, dz_m) / SCENARIO_SPEED_FACTOR[scenario]
    tag = np.full(seconds.shape, TAG_OK, dtype=np.uint8)
    if model.max_abs_grade is not None:
        refused = np.abs(dz_m / length_m) > model.max_abs_grade
        seconds = np.where(refused, np.inf, seconds)
        tag[refused] = TAG_REFUSED_GRADE
    usable = np.isfinite(seconds)
    if np.any(seconds[usable] <= 0):
        raise MarswalkError("INVALID_PROFILE", "traversal times must be strictly positive")
    params = tuple(sorted((k, v) for k, v in model.__dict__.items() if k != "name")) + (("scenario", scenario),)
    return EdgeTimes(seconds=seconds.astype(float), tag=tag, model=model.name, params=params)
