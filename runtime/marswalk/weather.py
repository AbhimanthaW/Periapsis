"""Live weather feed from base stations (both modes).

Base stations send messages; the planner never trusts a forecast on its own.

    observed, at or above the warning limit  -> WARNING   (active: changes the plan)
    observed, at or above the caution limit  -> CAUTION   (shown to the crew)
    observed, below caution                  -> NOMINAL
    forecast                                 -> ADVISORY  (shown to the crew, never changes the plan)
    no fresh observed message from any station -> LINK_LOST (weather unknown; fail closed if required)

Messages are checked before use: known station, known variable, matching unit,
value in a sane range, timestamp not in the future, and fresh (age <= max_age_s).
Rejected and stale messages are reported, never used.

Active effects:
    return_now        science plans fail the weather rule; the direct return stays allowed
    no_solar_credit   rover solar charging is credited as zero

Every limit below is a prototype ASSUMPTION for review (Isath), not a sourced
operational threshold. No live Mars weather exists in this repository; feeds
are simulated or replay published records, and are tagged as such.
"""
from dataclasses import dataclass, field, replace
import math

from .errors import FAIL, MarswalkError, PASS, UNKNOWN

NOMINAL, ADVISORY, CAUTION, WARNING, LINK_LOST = "nominal", "advisory", "caution", "warning", "link_lost"
REJECTED, STALE = "rejected", "stale"
MESSAGE_KINDS = frozenset({"observed", "forecast"})
MESSAGE_PROVENANCE = frozenset({"simulated", "historical_replay", "measured"})
EFFECTS = frozenset({"return_now", "no_solar_credit"})
FUTURE_TOLERANCE_S = 60.0


@dataclass(frozen=True)
class WeatherLimit:
    variable: str
    unit: str
    caution: float | None
    warning: float
    effect: str
    valid_min: float
    valid_max: float
    provenance: str = "assumed"

    def __post_init__(self):
        if self.effect not in EFFECTS:
            raise MarswalkError("INVALID_WEATHER", f"unknown weather effect {self.effect!r}")
        numbers = [self.warning, self.valid_min, self.valid_max] + ([] if self.caution is None else [self.caution])
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in numbers):
            raise MarswalkError("INVALID_WEATHER", f"{self.variable} limits must be finite numbers")
        if not self.valid_min <= (self.caution if self.caution is not None else self.warning) <= self.warning \
                <= self.valid_max:
            raise MarswalkError("INVALID_WEATHER", f"{self.variable} needs valid_min <= caution <= warning <= valid_max")


DEFAULT_LIMITS = (
    WeatherLimit("wind_speed", "m/s", caution=15.0, warning=20.0, effect="return_now", valid_min=0.0, valid_max=100.0),
    WeatherLimit("dust_optical_depth", "1", caution=1.0, warning=2.0, effect="no_solar_credit",
                 valid_min=0.0, valid_max=15.0),
    WeatherLimit("sep_alert", "flag", caution=None, warning=1.0, effect="return_now", valid_min=0.0, valid_max=1.0),
)


@dataclass(frozen=True)
class WeatherStation:
    id: str
    cell: tuple | None = None
    provenance: str = "simulated"


@dataclass(frozen=True)
class WeatherMessage:
    station_id: str
    variable: str
    value: float
    unit: str
    kind: str                  # observed | forecast
    time_utc: str              # observation time, or forecast issue time
    provenance: str = "simulated"
    valid_to_utc: str | None = None   # forecasts: end of the forecast window
    note: str = ""


@dataclass(frozen=True)
class WeatherFeed:
    stations: tuple
    messages: tuple = ()
    limits: tuple = DEFAULT_LIMITS
    max_age_s: float = 600.0
    required: bool = False     # True: losing the link leaves science UNKNOWN
    provenance: str = "simulated"

    def validate(self, shape=None):
        ids = [s.id for s in self.stations]
        if not ids or len(set(ids)) != len(ids):
            raise MarswalkError("INVALID_WEATHER", "weather feed needs at least one uniquely named station")
        for station in self.stations:
            if station.cell is not None and shape is not None:
                r, c = station.cell
                if not (0 <= r < shape[0] and 0 <= c < shape[1]):
                    raise MarswalkError("INVALID_WEATHER", f"station {station.id} lies outside the grid")
        variables = [limit.variable for limit in self.limits]
        if len(set(variables)) != len(variables):
            raise MarswalkError("INVALID_WEATHER", "duplicate weather limit")
        if not (isinstance(self.max_age_s, (int, float)) and 0 < self.max_age_s < math.inf):
            raise MarswalkError("INVALID_WEATHER", "max_age_s must be positive and finite")
        if self.provenance not in MESSAGE_PROVENANCE:
            raise MarswalkError("INVALID_WEATHER", "feed provenance must be simulated, historical_replay or measured")
        return self


@dataclass(frozen=True)
class WeatherAlert:
    level: str
    station_id: str | None
    variable: str | None
    value: float | None
    unit: str | None
    kind: str | None
    age_s: float | None
    reason: str
    effect: str | None = None
    provenance: str | None = None


@dataclass(frozen=True)
class WeatherAssessment:
    now_utc: str
    alerts: tuple
    return_now: bool
    no_solar_credit: bool
    link_lost: bool
    required: bool
    feed_provenance: str
    limits: tuple = field(default=())

    def rule(self, plan_kind):
        """(outcome, reason) for the weather hard constraint of one plan."""
        if plan_kind == "direct_return":
            return PASS, "returning home is always allowed by weather"
        if self.return_now:
            active = [a for a in self.alerts if a.level == WARNING and a.effect == "return_now"]
            return FAIL, "return now: " + "; ".join(a.reason for a in active)
        if self.link_lost and self.required:
            return UNKNOWN, "weather link lost; required weather is unknown"
        return PASS, "no active weather restriction"

    def crew_messages(self):
        return [f"[{a.level.upper()}] {a.reason}" + ("" if a.provenance in (None, "measured") else f" ({a.provenance})")
                for a in self.alerts]

    def to_dict(self):
        return {"now_utc": self.now_utc, "feed_provenance": self.feed_provenance, "required": self.required,
                "return_now": self.return_now, "no_solar_credit": self.no_solar_credit,
                "link_lost": self.link_lost, "alerts": [a.__dict__ for a in self.alerts],
                "crew_messages": self.crew_messages(),
                "limits": [dict(l.__dict__) for l in self.limits]}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def assess_weather(feed, now_utc, *, shape=None):
    """Classify every message at `now_utc` and derive the active effects."""
    from .environment import parse_utc
    feed.validate(shape)
    now = parse_utc(now_utc)
    stations = {s.id: s for s in feed.stations}
    limits = {l.variable: l for l in feed.limits}
    alerts, live = [], set()
    for m in feed.messages:
        base = dict(station_id=m.station_id, variable=m.variable, value=m.value if _number(m.value) else None,
                    unit=m.unit, kind=m.kind, provenance=m.provenance)
        problem = None
        limit = limits.get(m.variable)
        if m.station_id not in stations:
            problem = f"unknown station {m.station_id!r}"
        elif limit is None:
            problem = f"no limit declared for {m.variable!r}"
        elif m.kind not in MESSAGE_KINDS:
            problem = f"unknown message kind {m.kind!r}"
        elif m.provenance not in MESSAGE_PROVENANCE:
            problem = f"unknown provenance {m.provenance!r}"
        elif m.unit != limit.unit:
            problem = f"{m.variable} unit {m.unit!r} != {limit.unit!r}"
        elif not _number(m.value) or not limit.valid_min <= m.value <= limit.valid_max:
            problem = f"{m.variable} value outside {limit.valid_min:g}..{limit.valid_max:g} {limit.unit}"
        if problem is None:
            try:
                sent = parse_utc(m.time_utc)
                until = None if m.valid_to_utc is None else parse_utc(m.valid_to_utc)
            except MarswalkError:
                problem = "invalid timestamp"
        if problem is not None:
            alerts.append(WeatherAlert(REJECTED, age_s=None, reason=f"{m.station_id}: message rejected ({problem})",
                                       **base))
            continue
        age = (now - sent).total_seconds()
        label = f"{m.variable} {m.value:g}{'' if m.unit == '1' else ' ' + m.unit} at {m.station_id}"
        if age < -FUTURE_TOLERANCE_S:
            alerts.append(WeatherAlert(REJECTED, age_s=age, reason=f"{label}: timestamp is in the future", **base))
            continue
        if m.kind == "forecast":
            if until is not None and until < now:
                alerts.append(WeatherAlert(STALE, age_s=age, reason=f"forecast {label}: window ended", **base))
                continue
            over = " (exceeds the warning limit; forecasts never change the plan)" if m.value >= limit.warning else ""
            alerts.append(WeatherAlert(ADVISORY, age_s=age, reason=f"forecast {label}{over}", **base))
            continue
        if age > feed.max_age_s:
            alerts.append(WeatherAlert(STALE, age_s=age, reason=f"{label}: {age / 60:.0f} min old, ignored", **base))
            continue
        live.add(m.station_id)
        if m.value >= limit.warning:
            alerts.append(WeatherAlert(WARNING, age_s=age, effect=limit.effect,
                                       reason=f"{label} >= warning {limit.warning:g}", **base))
        elif limit.caution is not None and m.value >= limit.caution:
            alerts.append(WeatherAlert(CAUTION, age_s=age, reason=f"{label} >= caution {limit.caution:g}", **base))
        else:
            alerts.append(WeatherAlert(NOMINAL, age_s=age, reason=label, **base))
    for station in feed.stations:
        if station.id not in live:
            alerts.append(WeatherAlert(CAUTION, station.id, None, None, None, None, None,
                                       f"no fresh observation from {station.id}", provenance=station.provenance))
    link_lost = not live
    if link_lost:
        alerts.append(WeatherAlert(LINK_LOST, None, None, None, None, None, None,
                                   "no fresh observation from any station; weather is unknown"))
    warnings = [a for a in alerts if a.level == WARNING]
    return WeatherAssessment(now_utc=now_utc, alerts=tuple(alerts),
                             return_now=any(a.effect == "return_now" for a in warnings),
                             no_solar_credit=any(a.effect == "no_solar_credit" for a in warnings),
                             link_lost=link_lost, required=feed.required, feed_provenance=feed.provenance,
                             limits=tuple(feed.limits))


def without_solar(power):
    """The same power scenario with solar generation credited as zero."""
    if power is None:
        return None
    if power.kind == "solar_derived":
        return replace(power, atmospheric_transmittance=0.0)
    if power.kind == "declared_curve" and power.curve_source == "solar":
        return replace(power, curve=tuple((t, 0.0) for t, _ in power.curve))
    return power


def feed_from_dict(data):
    """Build a WeatherFeed from JSON (see runtime/examples/weather-*.json)."""
    try:
        stations = tuple(WeatherStation(s["id"], None if s.get("cell") is None else tuple(s["cell"]),
                                        s.get("provenance", "simulated")) for s in data["stations"])
        messages = tuple(WeatherMessage(**m) for m in data.get("messages", ()))
        limits = (DEFAULT_LIMITS if "limits" not in data else
                  tuple(WeatherLimit(**l) for l in data["limits"]))
        required = data.get("required", False)
        if not isinstance(required, bool):
            raise MarswalkError("INVALID_WEATHER", "required must be true or false")
        return WeatherFeed(stations=stations, messages=messages, limits=limits,
                           max_age_s=data.get("max_age_s", 600.0), required=required,
                           provenance=data.get("provenance", "simulated")).validate()
    except (KeyError, TypeError) as error:
        raise MarswalkError("INVALID_WEATHER", f"malformed weather feed: {error}") from error
