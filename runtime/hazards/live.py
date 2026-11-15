"""Live hazard map: per-square hazard state on the terrain grid, changing in time.

The fixed terrain baseline (Phase 1) never changes. This module builds a second,
live layer on EXACTLY the same grid and answers, for any time t:

    which squares are blocked by a hazard, which need caution, and why?

Inputs (all JSON, see runtime/examples/live-hazards-*.json):

  storms        moving dust devils or storm cells: centre (map metres), radius,
                velocity, wind and dust inside. Each observation carries a time.
                Between observations the footprint moves at the observed velocity
                (a declared, deterministic nowcast) for at most `extrapolate_max_s`.
  layers        raster readings (wind_speed m/s, dust_optical_depth) with the same
                shape and affine as the terrain. NaN means "no reading".
  alerts        whole-map radiation alerts (solar particle events). Radiation over a
                Marswalk area is effectively uniform, so an active alert means
                "return now" for the whole map, not blocked squares.

Rules:
  * A layer whose shape or affine differs from the terrain grid is refused.
  * Measured values at or above the block limit block squares; caution limits flag.
  * kind="forecast" inputs never block; they
    flag caution (forecasts stay advisory, as in runtime.marswalk.weather).
  * Extrapolated motion only ever ADDS closures; nothing here unblocks terrain.
  * An input older than max_age_s is stale: its last footprint is held in force
    (as in the hazard drill) and the feed reports link_lost.

All storm, layer and alert values in the examples are SIMULATED. The only real
values used are the Perseverance MEDA background wind (9.08 m/s, sol 36) and the
MSL RAD Gale background dose rate (0.21 mGy/day), both quoted for context only.
"""
from dataclasses import dataclass, field
from datetime import timedelta
import json
import math
from pathlib import Path

import numpy as np

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import MarswalkError

KINDS = frozenset({"observed", "forecast"})
PROVENANCE = frozenset({"simulated", "historical_replay", "measured"})
VARIABLES = {"wind_speed": "m/s", "dust_optical_depth": "1"}
BACKGROUND = {"wind_speed_mps": 9.08, "wind_source": "Perseverance MEDA, Jezero sol 36 (documentation/marsdoc/eva)",
              "dose_rate_mgy_per_day": 0.21, "dose_source": "MSL RAD, Gale (Hassler et al. 2014)"}


def _utc(text, what):
    try:
        return parse_utc(text)
    except MarswalkError as error:
        raise MarswalkError("INVALID_HAZARD", f"{what}: invalid UTC time") from error


def _finite(value, what, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MarswalkError("INVALID_HAZARD", f"{what} must be a finite number")
    if positive and value <= 0:
        raise MarswalkError("INVALID_HAZARD", f"{what} must be positive")
    if nonnegative and value < 0:
        raise MarswalkError("INVALID_HAZARD", f"{what} must not be negative")
    return float(value)


def _choice(value, allowed, what):
    if value not in allowed:
        raise MarswalkError("INVALID_HAZARD", f"{what} must be one of {sorted(allowed)}")
    return value


# ------------------------------------------------------------------ policy
@dataclass(frozen=True)
class LivePolicy:
    """Every threshold is a prototype ASSUMPTION for review (Isath)."""

    wind_block_mps: float = 20.0
    wind_caution_mps: float = 15.0
    dust_block_tau: float = 2.0
    dust_caution_tau: float = 1.0
    max_age_s: float = 600.0           # older inputs are stale
    extrapolate_max_s: float = 1800.0  # how far a storm observation may be carried forward
    eta_buffer_s: float = 60.0         # minimum +/- window around the predicted arrival time
    eta_buffer_fraction: float = 0.2   # the window grows with arrival time (pace uncertainty)
    slot_s: float = 60.0               # time resolution of the hazard timeline
    lookahead_s: float = 7200.0        # how far ahead the timeline is evaluated
    reroute_saving_s: float = 300.0    # suggest a safe alternative only if it saves this much
    provenance: str = "assumed"

    def __post_init__(self):
        for name in ("wind_block_mps", "wind_caution_mps", "dust_block_tau", "dust_caution_tau", "max_age_s",
                     "extrapolate_max_s", "slot_s", "lookahead_s"):
            _finite(getattr(self, name), name, positive=True)
        if not 0 <= self.eta_buffer_fraction <= 1:
            raise MarswalkError("INVALID_HAZARD", "eta_buffer_fraction must be between 0 and 1")
        for name in ("eta_buffer_s", "reroute_saving_s"):
            _finite(getattr(self, name), name, nonnegative=True)
        if self.wind_caution_mps > self.wind_block_mps or self.dust_caution_tau > self.dust_block_tau:
            raise MarswalkError("INVALID_HAZARD", "caution limits must not exceed block limits")


# ------------------------------------------------------------------ inputs
@dataclass(frozen=True)
class StormObservation:
    storm_id: str
    observed_utc: str
    centre_m: tuple            # (easting, northing) in the terrain grid's metres
    radius_m: float
    velocity_mps: tuple        # (east, north) metres per second
    wind_mps: float
    dust_tau: float
    kind: str = "observed"
    provenance: str = "simulated"

    def validate(self):
        _utc(self.observed_utc, f"storm {self.storm_id}")
        if len(self.centre_m) != 2 or len(self.velocity_mps) != 2:
            raise MarswalkError("INVALID_HAZARD", f"storm {self.storm_id}: centre and velocity need 2 values")
        for v in (*self.centre_m, *self.velocity_mps):
            _finite(v, f"storm {self.storm_id} position or velocity")
        _finite(self.radius_m, f"storm {self.storm_id} radius_m", positive=True)
        _finite(self.wind_mps, f"storm {self.storm_id} wind_mps", nonnegative=True)
        _finite(self.dust_tau, f"storm {self.storm_id} dust_tau", nonnegative=True)
        _choice(self.kind, KINDS, "storm kind")
        _choice(self.provenance, PROVENANCE, "storm provenance")
        return self


@dataclass(frozen=True)
class HazardLayer:
    variable: str
    values: np.ndarray         # rows x cols, NaN = no reading
    shape: tuple
    affine: tuple
    observed_utc: str
    kind: str = "observed"
    provenance: str = "simulated"

    def validate(self, support):
        _choice(self.variable, VARIABLES, "layer variable")
        _choice(self.kind, KINDS, "layer kind")
        _choice(self.provenance, PROVENANCE, "layer provenance")
        _utc(self.observed_utc, f"layer {self.variable}")
        if tuple(self.shape) != tuple(support.shape) or np.shape(self.values) != tuple(support.shape):
            raise MarswalkError("HAZARD_GRID_MISMATCH",
                                f"{self.variable} layer shape {tuple(self.shape)} != terrain {tuple(support.shape)}")
        if not np.allclose(np.asarray(self.affine, float), np.asarray(support.affine, float), rtol=0, atol=1e-6):
            raise MarswalkError("HAZARD_GRID_MISMATCH", f"{self.variable} layer affine differs from the terrain grid")
        values = np.asarray(self.values, float)
        finite = values[np.isfinite(values)]
        if (finite < 0).any():
            raise MarswalkError("INVALID_HAZARD", f"{self.variable} layer has negative values")
        return self


@dataclass(frozen=True)
class RadiationAlert:
    alert_id: str
    start_utc: str
    end_utc: str | None
    observed_utc: str
    kind: str = "observed"
    provenance: str = "simulated"
    note: str = ""

    def validate(self):
        start = _utc(self.start_utc, f"alert {self.alert_id}")
        _utc(self.observed_utc, f"alert {self.alert_id}")
        if self.end_utc is not None and _utc(self.end_utc, f"alert {self.alert_id}") <= start:
            raise MarswalkError("INVALID_HAZARD", f"alert {self.alert_id} must end after it starts")
        _choice(self.kind, KINDS, "alert kind")
        _choice(self.provenance, PROVENANCE, "alert provenance")
        return self

    def active(self, when):
        if when < parse_utc(self.start_utc):
            return False
        return self.end_utc is None or when < parse_utc(self.end_utc)


@dataclass(frozen=True)
class LiveFeed:
    feed_id: str
    storms: tuple = ()          # StormObservation, several per storm_id allowed
    layers: tuple = ()          # HazardLayer
    alerts: tuple = ()          # RadiationAlert
    provenance: str = "simulated"
    note: str = ""

    def validate(self, support):
        _choice(self.provenance, PROVENANCE, "feed provenance")
        for storm in self.storms:
            storm.validate()
        for layer in self.layers:
            layer.validate(support)
        for alert in self.alerts:
            alert.validate()
        keys = [(s.storm_id, s.kind, parse_utc(s.observed_utc)) for s in self.storms]
        if len(set(keys)) != len(keys):
            raise MarswalkError("INVALID_HAZARD", "duplicate storm observation")
        return self

    def received_by(self, when):
        """Only what had arrived by `when` (a live feed cannot see the future)."""
        return LiveFeed(self.feed_id,
                        tuple(s for s in self.storms if parse_utc(s.observed_utc) <= when),
                        tuple(l for l in self.layers if parse_utc(l.observed_utc) <= when),
                        tuple(a for a in self.alerts if parse_utc(a.observed_utc) <= when),
                        self.provenance, self.note)


def feed_from_dict(data, support):
    """Build and validate a LiveFeed. Storms may give `centre_cell` [row, col]
    instead of `centre_m`; it is converted with the terrain affine."""
    try:
        storms = []
        for s in data.get("storms", ()):
            s = dict(s)
            if "centre_cell" in s:
                if "centre_m" in s:
                    raise MarswalkError("INVALID_HAZARD", "give centre_m or centre_cell, not both")
                r, c = s.pop("centre_cell")
                s["centre_m"] = support.center_xy(float(r), float(c))
            s["centre_m"] = tuple(map(float, s["centre_m"]))
            s["velocity_mps"] = tuple(map(float, s["velocity_mps"]))
            storms.append(StormObservation(**s))
        layers = []
        for l in data.get("layers", ()):
            values = np.array([[np.nan if v is None else v for v in row] for row in l["values"]], float)
            layers.append(HazardLayer(l["variable"], values, tuple(l.get("shape", values.shape)),
                                      tuple(l["affine"]), l["observed_utc"], l.get("kind", "observed"),
                                      l.get("provenance", "simulated")))
        alerts = tuple(RadiationAlert(**a) for a in data.get("alerts", ()))
        return LiveFeed(data.get("feed_id", "live"), tuple(storms), tuple(layers), alerts,
                        data.get("provenance", "simulated"), data.get("note", "")).validate(support)
    except (KeyError, TypeError, ValueError) as error:
        raise MarswalkError("INVALID_HAZARD", f"malformed live hazard feed: {error}") from error


def load_feed(path, support):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise MarswalkError("INVALID_HAZARD", f"cannot read live hazard feed {path}: {error}") from error
    return feed_from_dict(data, support)


# ------------------------------------------------------------------ the map at one time
@dataclass(frozen=True)
class HazardState:
    """The live hazard map at one instant, on the terrain grid."""

    time_utc: str
    blocked: np.ndarray        # bool
    caution: np.ndarray        # bool (excludes blocked)
    wind_mps: np.ndarray       # float, NaN = no reading
    dust_tau: np.ndarray       # float, NaN = no reading
    radiation_alert: bool
    stale: tuple               # ids of stale inputs held in force
    reasons: tuple             # ("storm dd-1 blocks 314 squares", ...)

    @property
    def link_lost(self):
        return bool(self.stale)


def _cell_centres(support):
    rows, cols = support.shape
    a, _, c0, _, e, f0 = support.affine
    x = c0 + a * (np.arange(cols) + 0.5)
    y = f0 + e * (np.arange(rows) + 0.5)
    return np.meshgrid(x, y)


def storm_at(obs, when, policy):
    """Centre of a storm at `when` from its latest observation (clamped extrapolation)."""
    dt = (when - parse_utc(obs.observed_utc)).total_seconds()
    dt = min(max(dt, 0.0), policy.extrapolate_max_s)
    return obs.centre_m[0] + obs.velocity_mps[0] * dt, obs.centre_m[1] + obs.velocity_mps[1] * dt


def hazard_state(feed, support, when_utc, policy=LivePolicy(), *, now_utc=None):
    """The live map at `when_utc`, using only inputs received by `now_utc` (default: when)."""
    when = parse_utc(when_utc)
    now = parse_utc(now_utc) if now_utc is not None else when
    seen = feed.received_by(now)
    xx, yy = _cell_centres(support)
    shape = support.shape
    wind = np.full(shape, np.nan)
    dust = np.full(shape, np.nan)
    block = np.zeros(shape, bool)
    caution = np.zeros(shape, bool)
    reasons, stale = [], []

    latest = {}
    for obs in seen.storms:
        key = (obs.storm_id, obs.kind)
        if key not in latest or parse_utc(obs.observed_utc) > parse_utc(latest[key].observed_utc):
            latest[key] = obs
    for storm_id, kind in sorted(latest):
        obs = latest[storm_id, kind]
        age = (now - parse_utc(obs.observed_utc)).total_seconds()
        if age > policy.max_age_s:
            if kind == "forecast":
                continue
            stale.append(storm_id)
            cx, cy = obs.centre_m           # hold the last observed footprint in force
            moving = False
        else:
            cx, cy = storm_at(obs, when, policy)
            moving = True
        inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= obs.radius_m ** 2
        if not inside.any():
            continue
        wind = np.where(inside, np.fmax(wind, obs.wind_mps), wind)
        dust = np.where(inside, np.fmax(dust, obs.dust_tau), dust)
        hard = obs.wind_mps >= policy.wind_block_mps or obs.dust_tau >= policy.dust_block_tau
        soft = obs.wind_mps >= policy.wind_caution_mps or obs.dust_tau >= policy.dust_caution_tau
        if hard and obs.kind == "observed":
            block |= inside
            reasons.append(f"storm {storm_id} ({obs.kind}, wind {obs.wind_mps:g} m/s, dust {obs.dust_tau:g}) blocks "
                           f"{int(inside.sum())} squares" + ("" if moving else " (stale, held in force)"))
        elif hard or soft:
            caution |= inside
            reasons.append(f"storm {storm_id} ({obs.kind}) caution on {int(inside.sum())} squares")

    latest_layers = {}
    for layer in seen.layers:
        key = (layer.variable, layer.kind)
        if key not in latest_layers or parse_utc(layer.observed_utc) > parse_utc(latest_layers[key].observed_utc):
            latest_layers[key] = layer
    for key in sorted(latest_layers):
        layer = latest_layers[key]
        age = (now - parse_utc(layer.observed_utc)).total_seconds()
        values = np.asarray(layer.values, float)
        if age > policy.max_age_s:
            if layer.kind == "forecast":
                continue
            stale.append(f"layer:{layer.variable}@{layer.observed_utc}")
        limit = (policy.wind_block_mps, policy.wind_caution_mps) if layer.variable == "wind_speed" else \
            (policy.dust_block_tau, policy.dust_caution_tau)
        known = np.isfinite(values)
        over = known & (values >= limit[0])
        near = known & (values >= limit[1]) & ~over
        target = wind if layer.variable == "wind_speed" else dust
        target[:] = np.where(known, np.fmax(target, values), target)
        if layer.kind == "observed":
            block |= over
        else:
            near |= over
        caution |= near
        if over.any() or near.any():
            reasons.append(f"{layer.variable} layer ({layer.kind}): {int(over.sum())} over block limit, "
                           f"{int(near.sum())} at caution")

    radiation = any(a.active(when) and a.kind == "observed" for a in seen.alerts)
    for a in seen.alerts:
        if a.active(when):
            reasons.append(f"radiation alert {a.alert_id} ({a.kind}) active: "
                           + ("return now" if a.kind == "observed" else "advisory"))
    return HazardState(when.isoformat().replace("+00:00", "Z"), block, caution & ~block, wind, dust, radiation,
                       tuple(stale), tuple(reasons))


@dataclass
class HazardTimeline:
    """Blocked masks at every slot from now to now + lookahead (inputs as seen at now)."""

    feed: LiveFeed
    support: object
    now_utc: str
    policy: LivePolicy = field(default_factory=LivePolicy)

    def __post_init__(self):
        self.now = parse_utc(self.now_utc)
        steps = int(math.ceil(self.policy.lookahead_s / self.policy.slot_s)) + 1
        self.states = [hazard_state(self.feed, self.support, self._utc(i * self.policy.slot_s), self.policy,
                                    now_utc=self.now_utc) for i in range(steps)]
        self.blocked = np.stack([s.blocked for s in self.states])     # slots x rows x cols

    def _utc(self, seconds):
        return (self.now + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

    @property
    def current(self):
        return self.states[0]

    def slots(self, t0_s, t1_s):
        lo = max(0, int(math.floor(t0_s / self.policy.slot_s)))
        hi = min(len(self.states) - 1, int(math.ceil(t1_s / self.policy.slot_s)))
        return range(lo, hi + 1) if lo <= hi else range(0)

    def buffer_s(self, t_s):
        """Arrival-time uncertainty: max(eta_buffer_s, eta_buffer_fraction x arrival time)."""
        return max(self.policy.eta_buffer_s, self.policy.eta_buffer_fraction * max(t_s, 0.0))

    def hazardous(self, cell, t_s, until_s=None):
        """Check an arrival or occupancy interval with arrival-time uncertainty."""
        r, c = cell
        end = t_s if until_s is None else until_s
        return any(self.blocked[i, r, c] for i in
                   self.slots(t_s - self.buffer_s(t_s), end + self.buffer_s(end)))

    def footprint_around(self, t_s):
        """Union of blocked squares within t_s +/- buffer."""
        b = self.buffer_s(t_s)
        idx = list(self.slots(t_s - b, t_s + b))
        return self.blocked[idx].any(axis=0) if idx else np.zeros(self.support.shape, bool)

    def radiation_alert_within(self, t0_s, t1_s):
        start = self.now + timedelta(seconds=t0_s)
        end = self.now + timedelta(seconds=t1_s)
        alerts = self.feed.received_by(self.now).alerts
        return any(a.kind == "observed" and parse_utc(a.start_utc) <= end
                   and (a.end_utc is None or parse_utc(a.end_utc) > start) for a in alerts)
