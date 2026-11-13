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
from .traversability import local_relief_m

MARS_GRAVITY_MPS2 = 3.721


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
        tag[too_steep] = TAG_REFUSED_GRADE
        too_high = ~too_steep & ((relief[src] > p.clearance_m) | (relief[dst] > p.clearance_m))
        tag[too_high] = TAG_CLEARANCE
        usable = tag == TAG_OK

        # 2. duration: surface distance at the declared nominal speed
        surface = np.hypot(length_m, dz_m)
        seconds = np.where(usable, surface / p.nominal_speed_mps, np.inf)

        # 3. energy: mechanical work, clipped at zero downhill (no regeneration)
        mass = p.mass_kg + p.payload_kg
        weight = mass * MARS_GRAVITY_MPS2
        cos_theta = length_m / surface
        work = weight * dz_m + p.rolling_resistance * weight * cos_theta * surface
        electrical = np.maximum(work, 0.0) / p.drivetrain_efficiency + p.auxiliary_power_w * surface / p.nominal_speed_mps
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
        "reason": "quantitative wheel-ground mechanics need terrain measurements, matched vehicle "
                  "trials and held-out site data; none are available",
        "baseline": "authorized vehicle limits (incline, clearance) and declared coefficients only",
    }


def summary(profile):
    return {k: getattr(profile, k) for k in (
        "profile_id", "source_type", "source", "provenance", "mass_kg", "payload_kg", "clearance_m",
        "max_incline_deg", "nominal_speed_mps", "rolling_resistance", "drivetrain_efficiency",
        "auxiliary_power_w", "science_power_w", "battery_capacity_j", "battery_reserve_j",
        "initial_charge_j", "power_source", "max_charge_w", "max_discharge_w")}


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
