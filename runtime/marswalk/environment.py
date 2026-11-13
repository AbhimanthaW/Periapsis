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
from datetime import datetime, timedelta, timezone
import math
from numbers import Real

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
    return when.astimezone(timezone.utc)


def _julian_tt(when):
    if when.year < 2017:
        raise MarswalkError("INVALID_TIME", "TT - UTC is pinned for dates from 2017 onward")
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


def terrain_illumination(baseline, cells, sun, *, horizon_upper_bound_m=None):
    """Resolve terrain rays against a separately declared upper bound on all
    intervening terrain, including beyond the grid. The DEM is piecewise constant."""
    if not sun.above_horizon:
        return {tuple(c): "night" for c in cells}
    z = np.asarray(baseline.z_m, float)
    sup = baseline.support
    rows, cols = z.shape
    tan_el = math.tan(math.radians(sun.elevation_deg))
    az = math.radians(sun.azimuth_deg)
    row_rate = -math.cos(az) / sup.cell_dy_m
    col_rate = math.sin(az) / sup.cell_dx_m

    def crossings(rate):
        if abs(rate) < 1e-15:
            return 0, math.inf, math.inf
        step = 1 / abs(rate)
        return (1 if rate > 0 else -1), step / 2, step

    dr, first_row, row_step = crossings(row_rate)
    dc, first_col, col_step = crossings(col_rate)
    out = {}
    for cell in cells:
        r, c = cell
        z0 = z[r, c]
        status = "unresolved"
        if np.isfinite(z0):
            next_row, next_col = first_row, first_col
            while True:
                dist = min(next_row, next_col)
                ray = z0 + dist * tan_el
                if horizon_upper_bound_m is not None and ray > horizon_upper_bound_m:
                    status = "lit"
                    break
                if next_row == dist:
                    r += dr
                    next_row += row_step
                if next_col == dist:
                    c += dc
                    next_col += col_step
                if not (0 <= r < rows and 0 <= c < cols) or not np.isfinite(z[r, c]):
                    break
                if z[r, c] > ray:
                    status = "shadow"
                    break
        out[tuple(cell)] = status
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
def _nonnegative_finite(value):
    return isinstance(value, Real) and not isinstance(value, bool) and 0 <= value < math.inf


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
    curve_source: str | None = None       # solar | non_solar
    horizon_upper_bound_m: float | None = None  # declared in the terrain vertical datum

    def __post_init__(self):
        if self.kind not in {"declared_curve", "solar_derived", "non_solar", "none"}:
            raise MarswalkError("INVALID_POWER", f"unknown power scenario {self.kind!r}")
        if self.provenance not in {"assumed", "authorized", "simulated", "evidence"}:
            raise MarswalkError("INVALID_POWER", "power scenario needs a provenance tag")
        if self.kind == "declared_curve":
            if not isinstance(self.curve, (list, tuple)) or len(self.curve) < 2 or any(
                not isinstance(point, (tuple, list)) or len(point) != 2
                or not all(_nonnegative_finite(value) for value in point)
                for point in self.curve
            ):
                raise MarswalkError("INVALID_POWER", "curve needs at least two finite (seconds, watts) points")
            ts = [t for t, _ in self.curve]
            if ts[0] != 0 or any(a >= b for a, b in zip(ts, ts[1:])):
                raise MarswalkError("INVALID_POWER", "curve times must strictly increase from zero")
            object.__setattr__(self, "curve", tuple(tuple(point) for point in self.curve))
            if self.curve_source not in (None, "solar", "non_solar"):
                raise MarswalkError("INVALID_POWER", "curve_source must be solar or non_solar")
        if self.kind == "non_solar" and not _nonnegative_finite(self.constant_w):
            raise MarswalkError("INVALID_POWER", "non_solar needs finite constant_w >= 0")
        if self.kind == "solar_derived":
            if self.orientation != "horizontal":
                raise MarswalkError("INVALID_POWER", "only a horizontal panel is supported")
            area, efficiency, transmittance = (
                self.panel_area_m2, self.panel_efficiency, self.atmospheric_transmittance)
            if (not all(map(_nonnegative_finite, (area, efficiency, transmittance)))
                    or not (area > 0 and 0 < efficiency <= 1 and transmittance <= 1)):
                raise MarswalkError("INVALID_POWER", "solar parameters must be finite and in range")
        bound = self.horizon_upper_bound_m
        if bound is not None and (not isinstance(bound, Real) or isinstance(bound, bool)
                                  or not -math.inf < bound < math.inf):
            raise MarswalkError("INVALID_POWER", "horizon upper bound must be finite")

    def validate_source(self, source):
        if self.kind == "none":
            return
        declared = {"solar_derived": "solar", "non_solar": "non_solar",
                    "declared_curve": self.curve_source}[self.kind]
        if declared != source or declared is None:
            raise MarswalkError("INVALID_POWER", f"{self.kind} is incompatible with rover source {source!r}")


def supply_energy_j(scenario, t0_s, t1_s, *, time_utc=None, lat_deg=None, lon_east_deg=None,
                    baseline=None, stationary_cell=None, max_charge_w=None):
    """Credit declared supply. Solar credit is available only for a resolved
    stationary interval. During driving and unresolved visibility it is zero."""
    if scenario is None or t1_s < t0_s:
        return None
    if t1_s == t0_s or scenario.kind == "none":
        return 0.0
    cap = math.inf if max_charge_w is None else max_charge_w
    if scenario.kind == "non_solar":
        return min(cap, scenario.constant_w) * (t1_s - t0_s)
    if scenario.kind == "declared_curve":
        ts, ws = np.asarray(scenario.curve, float).T
        if t1_s > ts[-1]:
            return None
        grid = np.unique(np.concatenate([[t0_s, t1_s], ts[(ts > t0_s) & (ts < t1_s)]]))
        # Interpolating clipped endpoints conservatively bounds energy at crossings.
        return float(np.trapezoid(np.minimum(cap, np.interp(grid, ts, ws)), grid))
    if any(value is None for value in (time_utc, lat_deg, lon_east_deg)):
        return None
    if stationary_cell is None or baseline is None or scenario.horizon_upper_bound_m is None:
        return 0.0
    start = parse_utc(time_utc)
    if start.year < 2017:
        return None
    count = max(2, int(math.ceil((t1_s - t0_s) / 60.0)) + 1)
    times = np.linspace(t0_s, t1_s, count)
    watts = []
    for t in times:
        sun = mars_sun(start + timedelta(seconds=float(t)), lat_deg, lon_east_deg)
        visibility = terrain_illumination(baseline, [stationary_cell], sun,
                                          horizon_upper_bound_m=scenario.horizon_upper_bound_m)
        power = 0.0
        if visibility[stationary_cell] == "lit":
            power = (sun.top_of_atmosphere_w_m2 * scenario.atmospheric_transmittance * scenario.panel_area_m2
                     * scenario.panel_efficiency * math.sin(math.radians(sun.elevation_deg)))
        watts.append(min(cap, power))
    return float(np.dot(np.diff(times), np.minimum(watts[:-1], watts[1:])))


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
    scenario_id: str | None = None   # scope for an explicit operating scenario

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
        if (self.valid_from_utc and self.valid_to_utc
                and parse_utc(self.valid_from_utc) > parse_utc(self.valid_to_utc)):
            raise MarswalkError("INVALID_ENVIRONMENT", "validity window ends before it starts")
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


def activate_environment(variables, *, scenario_id=None, time_utc=None, duration_s=None):
    """Classify declarations for the scenario and its full planning window."""
    now = None if time_utc is None else parse_utc(time_utc)
    out = []
    for v in variables:
        if v.mode == "inactive":
            status, reason = INACTIVE, "declared inactive"
        elif v.mode == "historical_context":
            status, reason = CONTEXT_ONLY, "historical records are context only"
        elif v.effect == "context":
            status, reason = CONTEXT_ONLY, "declared for context only"
        elif v.mode == "supported_prediction":
            # A caller-supplied reference cannot establish forecast validation,
            # spatial coverage or horizon. No qualified forecast product is wired in.
            status, reason = UNVERIFIED, "no qualified prediction coverage is configured"
        elif (not isinstance(v.authorized_by, str) or not v.authorized_by.strip()
              or not isinstance(v.purpose, str) or not v.purpose.strip()
              or v.provenance not in {"simulated", "authorized"}
              or not scenario_id or v.scenario_id != scenario_id):
            status, reason = UNVERIFIED, "operating scenario needs matching scope, purpose and authorization"
        elif (v.valid_from_utc or v.valid_to_utc) and now is None:
            status, reason = UNVERIFIED, "time window declared but plan time is unknown"
        elif ((v.valid_from_utc and now < parse_utc(v.valid_from_utc))
              or (v.valid_to_utc and now > parse_utc(v.valid_to_utc))):
            status, reason = INACTIVE, "plan start is outside the declared window"
        elif v.valid_to_utc and (duration_s is None
                                 or duration_s > (parse_utc(v.valid_to_utc) - now).total_seconds()):
            status, reason = UNVERIFIED, "validity window does not cover the planning interval"
        else:
            status, reason = ACTIVE, f"explicit scenario authorized by {v.authorized_by}"
        if status != ACTIVE and v.required and v.effect != "context":
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
