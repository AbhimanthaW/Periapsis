"""Subsystem 05 · Rover mobility.

Boxes:
  * Rover traversal time      (P0) - vehicle limits first, then duration
  * Rover drive energy        (P0) - uphill work + rolling resistance + drivetrain
                                     losses + auxiliary load; no regeneration credit
  * Traction, slip & sinkage  (P2) - NOT modelled: needs instrumented calibration

Every refusal is tagged on the edge. A missing terrain property needed by a
vehicle limit refuses the edge (fail closed); it is never assumed passable.
The human pace model (Subsystem 04) is independent of everything here.
All vehicle numbers come from the RoverProfile and are assumptions unless
the profile cites a source.
"""
from dataclasses import dataclass

import numpy as np

from .config import RoverProfile
from .errors import MarswalkError
from .mobility import TAG_CLEARANCE, TAG_OK, TAG_REFUSED_GRADE, TAG_UNSUPPORTED, EdgeTimes
from .traversability import horn_gradient, local_relief_m

MARS_GRAVITY_MPS2 = 3.721


def drive_cost(profile, length_m, dz_m):
    """Seconds and gross electrical joules before terrain eligibility checks."""
    surface = np.hypot(length_m, dz_m)
    ground_fraction = 1 - profile.drive_slip_fraction
    travel_s = surface / (profile.nominal_speed_mps * ground_fraction)
    weight = (profile.mass_kg + profile.payload_kg) * MARS_GRAVITY_MPS2
    work = weight * (dz_m + profile.rolling_resistance * length_m)
    electrical = (np.maximum(work, 0.0) / (profile.drivetrain_efficiency * ground_fraction)
                  + profile.auxiliary_power_w * travel_s)
    return travel_s, electrical


@dataclass(frozen=True)
class RoverMobility:
    profile: RoverProfile

    @property
    def name(self):
        return f"rover:{self.profile.profile_id}"

    def edge_times(self, length_m, dz_m, src, dst, baseline):
        """Tagged per-edge time and electrical energy for this vehicle."""
        p = self.profile
        length_m = np.asarray(length_m, float)
        dz_m = np.asarray(dz_m, float)
        if np.any(length_m <= 0) or not np.all(np.isfinite(dz_m)):
            raise MarswalkError("INVALID_TERRAIN", "edge lengths must be positive and height changes finite")
        sup = baseline.support
        slope = np.asarray(baseline.slope_deg, float).ravel()
        relief = local_relief_m(np.asarray(baseline.z_m, float), np.isfinite(np.asarray(baseline.z_m, float)),
                                sup.cell_dx_m, sup.cell_dy_m).ravel()

        tag = np.full(length_m.shape, TAG_OK, dtype=np.uint8)
        # 1. vehicle limits (checked before any duration)
        grade_deg = np.degrees(np.arctan(np.abs(dz_m) / length_m))
        tilt = np.maximum(slope[src], slope[dst])
        rel = np.maximum(relief[src], relief[dst])
        unsupported = ~np.isfinite(tilt) | ~np.isfinite(rel)
        tag[unsupported] = TAG_UNSUPPORTED
        too_steep = ((grade_deg > p.max_incline_deg) | (slope[src] > p.max_incline_deg)
                     | (slope[dst] > p.max_incline_deg))
        if p.max_cross_slope_deg is not None:
            east, north = horn_gradient(baseline.z_m, np.isfinite(baseline.z_m), sup.cell_dx_m, sup.cell_dy_m)
            rows, cols = np.divmod(dst, sup.shape[1])
            r0, c0 = np.divmod(src, sup.shape[1])
            direction_e = (cols - c0) * sup.cell_dx_m / length_m
            direction_n = (r0 - rows) * sup.cell_dy_m / length_m
            for nodes in (src, dst):
                cross = direction_e * north.ravel()[nodes] - direction_n * east.ravel()[nodes]
                too_steep |= np.abs(cross) > np.tan(np.radians(p.max_cross_slope_deg))
        tag[too_steep] = TAG_REFUSED_GRADE
        too_high = ~too_steep & ((relief[src] > p.clearance_m) | (relief[dst] > p.clearance_m))
        tag[too_high] = TAG_CLEARANCE
        usable = tag == TAG_OK

        # 2. Duration uses effective ground speed. A supplied slip ratio
        # applies to a matched, approximately uniform traverse.
        travel_s, electrical = drive_cost(p, length_m, dz_m)
        seconds = np.where(usable, travel_s, np.inf)
        energy = np.where(usable, electrical, np.inf)

        params = tuple(sorted((k, v) for k, v in p.__dict__.items() if not isinstance(v, str)))
        return EdgeTimes(seconds=seconds, tag=tag, model=self.name, params=params, energy_j=energy)

    def dwell_energy_j(self, seconds):
        """Stationary science energy from its own duration and load."""
        return float(self.profile.science_power_w) * float(seconds)


def traction_assessment(profile=None):
    """Traction, slip & sinkage (P2): explicitly unavailable."""
    return {
        "status": "not_calibrated",
        "reason": "quantitative wheel-ground mechanics need terrain measurements and matched vehicle trials",
        "declared_drive_slip_fraction": None if profile is None else profile.drive_slip_fraction,
        "baseline": "declared incline, clearance, optional cross-slope and uniform slip",
    }


def summary(profile):
    return {k: getattr(profile, k) for k in (
        "profile_id", "source_type", "source", "provenance", "mass_kg", "payload_kg", "clearance_m",
        "max_incline_deg", "nominal_speed_mps", "rolling_resistance", "drivetrain_efficiency",
        "auxiliary_power_w", "science_power_w", "battery_capacity_j", "battery_reserve_j",
        "initial_charge_j", "power_source", "max_charge_w", "max_discharge_w", "max_cross_slope_deg",
        "drive_slip_fraction")}


def hypothetical_crew_rover():
    """Illustrative crew-rover record for demos and tests. HYPOTHETICAL: not a
    NASA vehicle specification."""
    kwh = 3.6e6
    return RoverProfile(
        profile_id="hypothetical-crew-rover", source_type="hypothetical", mass_kg=900.0, payload_kg=250.0,
        wheel_radius_m=0.4, clearance_m=0.35, max_incline_deg=20.0, nominal_speed_mps=1.5,
        rolling_resistance=0.15, drivetrain_efficiency=0.7, auxiliary_power_w=400.0, science_power_w=150.0,
        battery_capacity_j=20 * kwh, battery_reserve_j=4 * kwh, initial_charge_j=16 * kwh, power_source="solar",
        max_charge_w=1200.0, max_discharge_w=4000.0)
