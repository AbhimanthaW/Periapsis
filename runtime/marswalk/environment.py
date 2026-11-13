"""Subsystem 06 · Environmental models.

Boxes:
  * Historical weather & RAD   (P2) - pinned observations; context only
  * Solar geometry & shadow    (P1) - Sun direction + resolved terrain occlusion
  * Power availability scenario(P1) - declared supply; solar only from declared
                                      attenuation, area, efficiency, orientation
  * Environmental activation   (P0) - the only door from environment to constraints
  * Comms and forecast research(P2) - NOT modelled: explicit unavailable status

Historical and simulated inputs are always marked. Nothing here forecasts
weather or human dose. Missing required context yields unverified_environment.

Sun position follows the Mars24 algorithm (Allison & McEwen 2000, Planetary
and Space Science 48; NASA GISS Mars24 technical notes) with TT - UTC fixed at
69.184 s (valid for dates after 2017-01-01). It stands in for the pinned SPICE
kernels named in the architecture and is accurate to about 0.1 degree, which
is ample for context, daylight and shadow screening.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import math

import numpy as np

from .errors import MarswalkError

TT_MINUS_UTC_S = 69.184
SOLAR_CONSTANT_1AU_W_M2 = 1361.0
SOL_S = 88_775.244

# ------------------------------------------------------------------ time
def parse_utc(text):
    """Strict ISO 8601 UTC ('...Z' or '+00:00') -> aware datetime."""
    if not isinstance(text, str):
        raise MarswalkError("INVALID_TIME", "time must be an ISO 8601 UTC string")
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MarswalkError("INVALID_TIME", f"cannot parse {text!r}") from error
    if when.utcoffset() is None or when.utcoffset().total_seconds() != 0:
        raise MarswalkError("INVALID_TIME", "time must be explicitly UTC")
    if when.year < 2017:
        raise MarswalkError("INVALID_TIME", "TT - UTC is pinned for dates from 2017 onward")
    return when.astimezone(timezone.utc)


def _julian_tt(when):
    jd_ut = when.timestamp() / 86400.0 + 2440587.5
    return jd_ut + TT_MINUS_UTC_S / 86400.0


# ------------------------------------------------------------------ solar geometry (P1)
_PBS = ((0.0071, 2.2353, 49.409), (0.0057, 2.7543, 168.173), (0.0039, 1.1177, 191.837),
        (0.0037, 15.7866, 21.736), (0.0021, 2.1354, 15.704), (0.0020, 2.4694, 95.528),
        (0.0018, 32.8493, 49.095))


@dataclass(frozen=True)
class SunPosition:
    time_utc: str
    solar_longitude_deg: float      # Ls, season
    declination_deg: float
    heliocentric_distance_au: float
    local_mean_solar_time_h: float
    local_true_solar_time_h: float
    elevation_deg: float
    azimuth_deg: float               # clockwise from north
    top_of_atmosphere_w_m2: float

    @property
    def above_horizon(self):
        return self.elevation_deg > 0

    def to_dict(self):
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def mars_sun(time_utc, lat_deg, lon_east_deg):
    """Sun direction at a Mars site (planetocentric latitude, east longitude)."""
    if isinstance(time_utc, datetime):
        if time_utc.utcoffset() is None or time_utc.utcoffset().total_seconds() != 0:
            raise MarswalkError("INVALID_TIME", "datetime must be timezone-aware UTC")
        when = time_utc
    else:
        when = parse_utc(time_utc)
    jd_tt = _julian_tt(when)
    dt = jd_tt - 2451545.0
    m = math.radians((19.3871 + 0.52402073 * dt) % 360)
    alpha_fms = (270.3871 + 0.524038496 * dt) % 360
    pbs = sum(a * math.cos(math.radians(0.985626 * dt / tau + phi)) for a, tau, phi in _PBS)
    nu_m = ((10.691 + 3.0e-7 * dt) * math.sin(m) + 0.623 * math.sin(2 * m) + 0.050 * math.sin(3 * m)
            + 0.005 * math.sin(4 * m) + 0.0005 * math.sin(5 * m) + pbs)
    ls = (alpha_fms + nu_m) % 360
    lsr = math.radians(ls)
    eot_deg = 2.861 * math.sin(2 * lsr) - 0.071 * math.sin(4 * lsr) + 0.002 * math.sin(6 * lsr) - nu_m
    mst = (24 * (((jd_tt - 2451549.5) / 1.0274912517) + 44796.0 - 0.0009626)) % 24
    lmst = (mst + lon_east_deg / 15.0) % 24
    ltst = (lmst + eot_deg / 15.0) % 24
    dec = math.degrees(math.asin(0.42565 * math.sin(lsr))) + 0.25 * math.sin(lsr)
    r_au = 1.52367934 * (1.00436 - 0.09309 * math.cos(m) - 0.004336 * math.cos(2 * m)
                         - 0.00031 * math.cos(3 * m) - 0.00003 * math.cos(4 * m))
    h = math.radians(15.0 * (ltst - 12.0))
    phi, d = math.radians(lat_deg), math.radians(dec)
    sin_el = math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.cos(h)
    el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
    az = math.degrees(math.atan2(-math.sin(h) * math.cos(d),
                                 math.sin(d) * math.cos(phi) - math.cos(d) * math.sin(phi) * math.cos(h))) % 360
    return SunPosition(when.strftime("%Y-%m-%dT%H:%M:%SZ"), ls, dec, r_au, lmst, ltst, el, az,
                       SOLAR_CONSTANT_1AU_W_M2 / r_au ** 2)


def terrain_illumination(baseline, cells, sun):
    """'night' | 'shadow' | 'lit' | 'unresolved' per cell. A ray toward the Sun
    is marched across the grid; it is only 'lit' if it rises above every cell
    in the grid before leaving it, otherwise terrain beyond the grid could
    still block it and the answer is 'unresolved'."""
    z = np.asarray(baseline.z_m, float)
    sup = baseline.support
    rows, cols = z.shape
    ceiling = np.nanmax(z)
    out = {}
    if not sun.above_horizon:
        return {tuple(c): "night" for c in cells}
    tan_el = math.tan(math.radians(sun.elevation_deg))
    az = math.radians(sun.azimuth_deg)
    east, north = math.sin(az), math.cos(az)
    step = 0.5 * min(sup.cell_dx_m, sup.cell_dy_m)
    for cell in cells:
        r0, c0 = map(int, cell)
        z0 = z[r0, c0]
        if not np.isfinite(z0):
            out[(r0, c0)] = "unresolved"
            continue
        status, dist = None, step
        while status is None:
            col = c0 + east * dist / sup.cell_dx_m
            row = r0 - north * dist / sup.cell_dy_m
            ri, ci = int(round(row)), int(round(col))
            ray = z0 + dist * tan_el
            if not (0 <= ri < rows and 0 <= ci < cols):
                status = "lit" if ray > ceiling else "unresolved"
            elif not np.isfinite(z[ri, ci]):
                status = "unresolved"
            elif z[ri, ci] > ray:
                status = "shadow"
            elif ray > ceiling:
                status = "lit"
            dist += step
        out[(r0, c0)] = status
    return out


# ------------------------------------------------------------------ historical observations (P2)
@dataclass(frozen=True)
class Observation:
    """One pinned measurement (e.g. MEDA air temperature, RAD dose rate)."""

    variable: str
    value: float
    unit: str
    time_utc: str
    location: str
    sensor: str
    uncertainty: str
    source_id: str

    def __post_init__(self):
        parse_utc(self.time_utc)
        if not all((self.variable, self.unit, self.location, self.sensor, self.source_id)):
            raise MarswalkError("INVALID_OBSERVATION", "observations need variable, unit, location, sensor, source")


# ------------------------------------------------------------------ power availability (P1)
@dataclass(frozen=True)
class PowerScenario:
    """Declared supply for a vehicle. 'none' is a declared no-generation case,
    not a guess. Solar output is derived only from declared attenuation, area,
    efficiency and a horizontal panel; other orientations are refused."""

    kind: str                              # declared_curve | solar_derived | non_solar | none
    provenance: str = "assumed"
    curve: tuple = ()                      # ((t_s, watts), ...) from plan start, declared_curve
    constant_w: float | None = None        # non_solar
    panel_area_m2: float | None = None     # solar_derived
    panel_efficiency: float | None = None
    atmospheric_transmittance: float | None = None   # 0..1, declared (dust/opacity assumption)
    orientation: str = "horizontal"

    def __post_init__(self):
        if self.kind not in {"declared_curve", "solar_derived", "non_solar", "none"}:
            raise MarswalkError("INVALID_POWER", f"unknown power scenario {self.kind!r}")
        if self.provenance not in {"assumed", "authorized", "simulated", "evidence"}:
            raise MarswalkError("INVALID_POWER", "power scenario needs a provenance tag")
        if self.kind == "declared_curve":
            ts = [t for t, _ in self.curve]
            if len(self.curve) < 2 or ts != sorted(ts) or ts[0] != 0 or any(w < 0 for _, w in self.curve):
                raise MarswalkError("INVALID_POWER", "curve needs >= 2 points from t=0, increasing t, watts >= 0")
        if self.kind == "non_solar" and (self.constant_w is None or self.constant_w < 0):
            raise MarswalkError("INVALID_POWER", "non_solar needs constant_w >= 0")
        if self.kind == "solar_derived":
            if self.orientation != "horizontal":
                raise MarswalkError("INVALID_POWER", "only a horizontal panel is supported")
            for name in ("panel_area_m2", "panel_efficiency", "atmospheric_transmittance"):
                if getattr(self, name) is None:
                    raise MarswalkError("INVALID_POWER", f"solar_derived needs {name}")
            if not (self.panel_area_m2 > 0 and 0 < self.panel_efficiency <= 1
                    and 0 <= self.atmospheric_transmittance <= 1):
                raise MarswalkError("INVALID_POWER", "solar parameters out of range")


def supply_energy_j(scenario, t0_s, t1_s, *, time_utc=None, lat_deg=None, lon_east_deg=None, step_s=60.0):
    """Energy supplied between plan times t0 and t1 (seconds from plan start).
    Returns None when the scenario needs context that was not declared."""
    if scenario is None or t1_s < t0_s:
        return None
    if t1_s == t0_s or scenario.kind == "none":
        return 0.0
    if scenario.kind == "non_solar":
        return scenario.constant_w * (t1_s - t0_s)
    if scenario.kind == "declared_curve":
        ts = np.array([t for t, _ in scenario.curve], float)
        ws = np.array([w for _, w in scenario.curve], float)
        if t1_s > ts[-1]:
            return None                             # beyond the declared curve
        grid = np.unique(np.concatenate([[t0_s, t1_s], ts[(ts > t0_s) & (ts < t1_s)]]))
        return float(np.trapezoid(np.interp(grid, ts, ws), grid))
    if time_utc is None or lat_deg is None or lon_east_deg is None:
        return None                                 # solar needs time and site
    start = parse_utc(time_utc).timestamp()
    n = max(2, int(math.ceil((t1_s - t0_s) / step_s)) + 1)
    times = np.linspace(t0_s, t1_s, n)
    watts = []
    for t in times:
        sun = mars_sun(datetime.fromtimestamp(start + t, tz=timezone.utc), lat_deg, lon_east_deg)
        watts.append(sun.top_of_atmosphere_w_m2 * scenario.atmospheric_transmittance * scenario.panel_area_m2
                     * scenario.panel_efficiency * max(0.0, math.sin(math.radians(sun.elevation_deg))))
    return float(np.trapezoid(watts, times))


# ------------------------------------------------------------------ environmental activation (P0)
MODES = ("inactive", "historical_context", "explicit_scenario", "supported_prediction")
EFFECTS = ("context", "return_now", "block_cells")
ACTIVE = "active"
CONTEXT_ONLY = "context_only"
INACTIVE = "inactive"
UNVERIFIED = "unverified_environment"


@dataclass(frozen=True)
class EnvironmentalVariable:
    """A declared environmental input and how it may be used."""

    id: str
    variable: str                     # e.g. "solar_particle_event", "local_dust", "air_temperature"
    mode: str                         # one of MODES
    effect: str = "context"           # one of EFFECTS
    purpose: str = ""
    authorized_by: str = ""
    provenance: str = "simulated"
    valid_from_utc: str | None = None
    valid_to_utc: str | None = None
    cells: tuple = ()                 # block_cells footprint
    validation_ref: str = ""          # required for supported_prediction
    required: bool = False            # if True and not active -> unverified_environment
    observations: tuple = ()          # Observation, ... (historical context)
    note: str = ""

    def __post_init__(self):
        if self.mode not in MODES:
            raise MarswalkError("INVALID_ENVIRONMENT", f"mode must be one of {MODES}")
        if self.effect not in EFFECTS:
            raise MarswalkError("INVALID_ENVIRONMENT", f"effect must be one of {EFFECTS}")
        if self.provenance not in {"evidence", "authorized", "assumed", "simulated"}:
            raise MarswalkError("INVALID_ENVIRONMENT", "environment needs a provenance tag")
        if self.effect == "block_cells" and not self.cells:
            raise MarswalkError("INVALID_ENVIRONMENT", "block_cells needs a footprint")
        for t in (self.valid_from_utc, self.valid_to_utc):
            if t is not None:
                parse_utc(t)
        object.__setattr__(self, "cells", tuple(tuple(c) for c in self.cells))


@dataclass(frozen=True)
class Activation:
    id: str
    variable: str
    status: str
    effect: str
    reason: str
    required: bool

    def to_dict(self):
        return dict(self.__dict__)


def activate_environment(variables, *, time_utc=None):
    """Classify every variable. Only an authorized, applicable explicit
    scenario or validated prediction becomes ACTIVE and may constrain a plan."""
    out = []
    now = None if time_utc is None else parse_utc(time_utc)
    for v in variables:
        status, reason = None, ""
        if v.mode == "inactive":
            status, reason = INACTIVE, "declared inactive"
        elif v.mode == "historical_context":
            status, reason = CONTEXT_ONLY, "historical records are context only and never constrain a plan"
        elif not v.authorized_by:
            status, reason = UNVERIFIED, "no authorization recorded"
        elif v.mode == "supported_prediction" and not v.validation_ref:
            status, reason = UNVERIFIED, "prediction has no validation reference"
        elif v.valid_from_utc or v.valid_to_utc:
            if now is None:
                status, reason = UNVERIFIED, "time window declared but plan time is unknown"
            elif (v.valid_from_utc and now < parse_utc(v.valid_from_utc)) or \
                    (v.valid_to_utc and now > parse_utc(v.valid_to_utc)):
                status, reason = INACTIVE, "plan time is outside the declared window"
        if status is None:
            if v.effect == "context":
                status, reason = CONTEXT_ONLY, "authorized but declared for context only"
            else:
                status, reason = ACTIVE, f"{v.mode.replace('_', ' ')} authorized by {v.authorized_by}"
        if status in (INACTIVE, CONTEXT_ONLY) and v.required and v.effect != "context":
            status, reason = UNVERIFIED, f"required input not active ({reason})"
        out.append(Activation(v.id, v.variable, status, v.effect, reason, v.required))
    return out


# ------------------------------------------------------------------ comms and forecasts (P2)
def comms_and_forecast_assessment():
    return {
        "communications": {"status": "not_modelled",
                           "requires": ["relay ephemerides", "antenna state", "terrain line of sight", "link budget"]},
        "weather_forecast": {"status": "not_modelled",
                             "requires": ["verified forecast product", "domain", "horizon", "uncertainty"]},
        "note": "terrain elevation alone cannot predict communications, wind or landslides",
    }
