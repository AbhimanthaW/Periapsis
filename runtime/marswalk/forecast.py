"""Advisory station forecast for the command centre and the astronaut.

Loads a model artifact from ``python -m return_window_pipeline.forecast train`` and, from whatever
sensors are fresh, forecasts pressure, air temperature, wind and dust optical depth 1-6 Mars hours ahead.

* Uses as little information as is available: each target uses the smallest validated sensor kit
  that the fresh sensors can supply; with no usable sensors it falls back to climatology.
* Every number carries its band (P10/P50/P90), its base (climatology or persistence), its validated
  track record and, for limited variables, the chance of crossing the caution and warning limits.
* Forecasts stay advisory. ``forecast_messages`` emits ``kind="forecast"`` WeatherMessages, which
  ``assess_weather`` classifies as ADVISORY and never lets change the plan.

    python -m runtime.marswalk.forecast MODEL.json OBSERVATIONS.json
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import math
from pathlib import Path

import numpy as np

from .environment import _PBS, _julian_tt, parse_utc
from .errors import MarswalkError
from .weather import DEFAULT_LIMITS, WeatherMessage

SOL_S = 88775.244
MARS_HOUR_S = SOL_S / 24.0
ALIASES = {"wind_speed": "wind_ms", "dust_optical_depth": "dust_tau", "pressure": "pressure_pa",
           "air_temperature": "air_temp_k"}
LABELS = {"pressure_pa": "barometer", "air_temp_k": "thermometer", "wind_ms": "anemometer", "dust_tau": "sky opacity"}


def local_time(time_utc, lon_east_deg):
    """Ls, LTST and a continuous local true solar hour count, as in the training pipeline."""
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
    msd = (jd_tt - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626
    hours = msd * 24.0 + lon_east_deg / 15.0 + eot_deg / 15.0
    return {"ls_deg": ls, "ltst_h": hours % 24.0, "local_hours": hours}


def _fmt_ltst(hours):
    h = int(hours) % 24
    return f"{h:02d}:{int(round((hours - int(hours)) * 60)) % 60:02d}"


@dataclass(frozen=True)
class Observation:
    variable: str
    value: float
    time_utc: str


class ForecastModel:
    def __init__(self, artifact: dict):
        if artifact.get("schema_version") != 1 or artifact.get("classification") != "station_forecast_minimal_sensor":
            raise MarswalkError("INVALID_FORECAST_MODEL", "unsupported forecast model artifact")
        self.artifact = artifact
        self.id = artifact["model_id"]
        self.bins = int(artifact["time_axis"]["bins_per_sol"])
        self.horizons = {key: int(b) for key, b in artifact["horizons"].items()}
        clim = artifact["climatology"]
        self.centers = np.asarray(clim["ls_centers_deg"], dtype=float)
        self.tables = {v: np.asarray(t, dtype=float) for v, t in clim["tables"].items()}
        self.support = {v: np.asarray(t, dtype=int) for v, t in clim.get("support", {}).items()}
        self.models = artifact["models"]
        self.selection = artifact["selection"]
        self.rows = {(r["target"], f"{r['horizon_h']}h", r["kit"]): r for r in artifact["rows"]}
        self.settings = artifact["settings"]
        self.station = artifact["station"]
        self.variables = artifact["variables"]

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def climatology(self, variable, bin_index, ls):
        step = self.centers[1] - self.centers[0]
        pos = (ls % 360) / step
        lo = int(math.floor(pos)) % len(self.centers)
        hi = (lo + 1) % len(self.centers)
        w = pos - math.floor(pos)
        b = int(bin_index) % self.bins
        table = self.tables[variable]
        level = int(max(self.support[variable][b, lo], self.support[variable][b, hi])) if variable in self.support else 0
        return float(table[b, lo] * (1 - w) + table[b, hi] * w), level

    def eligible(self, target, key, kit_name):
        row = self.rows.get((target, key, kit_name))
        s = self.settings
        return bool(row and row.get("skill_vs_climatology") is not None
                    and row["skill_vs_climatology"] >= s["min_gain"]
                    and row["skill_vs_best_baseline"] >= -s["tolerance"]
                    and (row.get("coverage_p10_p90") or 0) >= s["min_coverage"]), row


def _bin_observations(model, observations, now_utc, lon):
    """Mean anomaly per sensor in the current local-time bin (0) and the two before it (1, 2)."""
    now = local_time(now_utc, lon)
    now_abs = math.floor(now["local_hours"] * model.bins / 24.0)
    sums = {}
    latest = {}
    for obs in observations:
        variable = ALIASES.get(obs.variable, obs.variable)
        if variable not in model.tables or not isinstance(obs.value, (int, float)) or not math.isfinite(obs.value):
            continue
        t = local_time(obs.time_utc, lon)
        if parse_utc(obs.time_utc) > parse_utc(now_utc):
            continue
        offset = now_abs - math.floor(t["local_hours"] * model.bins / 24.0)
        if not 0 <= offset <= 2:
            continue
        clim, _ = model.climatology(variable, math.floor(t["ltst_h"] * model.bins / 24.0), t["ls_deg"])
        bucket = sums.setdefault(variable, {})
        total, count = bucket.get(offset, (0.0, 0))
        bucket[offset] = (total + obs.value - clim, count + 1)
        if variable not in latest or parse_utc(obs.time_utc) > parse_utc(latest[variable][1]):
            latest[variable] = (obs.value, obs.time_utc)
    anomalies = {v: {o: tot / n for o, (tot, n) in b.items()} for v, b in sums.items()}
    fresh = sorted(v for v, a in anomalies.items() if 0 in a and 1 in a)
    return now, now_abs, anomalies, fresh, latest


def _features(kit, target, anomalies, now_abs, h, bins, ls):
    cols = []
    for v in kit:
        a = anomalies[v]
        now, prev = a[0], a[1]
        mean3 = float(np.mean([a[o] for o in (0, 1, 2) if o in a]))
        cols += [now - prev, now - mean3] if v == target else [now, now - prev, mean3]
    phase = 2 * math.pi * ((now_abs + h) % bins) / bins
    lsr = math.radians(ls)
    return np.asarray(cols + [math.sin(phase), math.cos(phase), math.sin(lsr), math.cos(lsr)], dtype=float)


def _limit_for(variable, limits):
    weather_variable = {"wind_ms": "wind_speed", "dust_tau": "dust_optical_depth"}.get(variable)
    return next((l for l in limits if l.variable == weather_variable), None)


def issue_forecast(model: ForecastModel, observations, now_utc, *, lon_east_deg=None, limits=DEFAULT_LIMITS,
                   provenance="simulated"):
    """Forecast every target and horizon from the observations available at ``now_utc``."""
    lon = model.station["lon_east_deg"] if lon_east_deg is None else lon_east_deg
    if lon is None:
        raise MarswalkError("INVALID_FORECAST_MODEL", "station longitude is required for local time")
    obs = [o if isinstance(o, Observation) else Observation(**o) for o in observations]
    now, now_abs, anomalies, fresh, latest = _bin_observations(model, obs, now_utc, lon)
    issued = parse_utc(now_utc)
    forecasts = []
    for target, by_h in model.models.items():
        for key, kits in by_h.items():
            h = model.horizons[key]
            valid_bin = now_abs + h
            clim, support = model.climatology(target, valid_bin % model.bins, now["ls_deg"])
            clock = kits.get("clock")
            reason, status, kit_name, entry = None, "climatology", "clock", clock
            selected = model.selection.get(target, {}).get(key, {})
            if selected.get("status") != "model":
                reason = "no sensor kit passed validation for this target and horizon"
            else:
                usable = []
                for name, candidate in kits.items():
                    if name == "clock" or not set(candidate["sensors"]) <= set(fresh):
                        continue
                    ok, row = model.eligible(target, key, name)
                    if ok:
                        usable.append((len(candidate["sensors"]), -row["skill_vs_climatology"], name, row))
                if not usable:
                    missing = [LABELS[v] for v in selected.get("sensors", []) if v not in fresh]
                    reason = "no validated kit can be built from fresh sensors" + (f" (missing {', '.join(missing)})" if missing else "")
                else:
                    best = min(r[1] for r in usable)  # most negative = highest skill
                    within = [u for u in usable if -u[1] >= -best - model.settings["tolerance"]]
                    _, _, kit_name, _ = min(within)
                    entry, status = kits[kit_name], "model"
            point, base, correction = clim, clim, 0.0
            if status == "model":
                x = _features(tuple(entry["sensors"]), target, anomalies, now_abs, h, model.bins, now["ls_deg"])
                ranges = np.asarray(entry["ranges"])
                if not np.all((x >= ranges[0]) & (x <= ranges[1])):
                    status, reason, entry, kit_name = "abstained", "inputs outside the training range", clock, "clock"
                else:
                    base = clim + (anomalies[target][0] if entry["base"] == "anomaly_persistence" else 0.0)
                    z = (x - np.asarray(entry["mean"])) / np.asarray(entry["scale"])
                    correction = float(entry["intercept"] + z @ np.asarray(entry["coef"]))
                    point = base + correction
            if support >= 3:
                reason = (reason + "; " if reason else "") + "season not in the training record (climatology extrapolated)"
            pct = np.asarray(entry["residual_percentiles"], dtype=float)
            values = point + pct
            row = model.rows.get((target, key, kit_name), {})
            result = {"target": target, "label": model.variables[target]["label"], "unit": model.variables[target]["unit"],
                      "horizon": key, "valid_utc": (issued + timedelta(seconds=h * SOL_S / model.bins)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "valid_ltst": _fmt_ltst((valid_bin % model.bins + 0.5) * 24 / model.bins),
                      "p10": round(float(point + pct[9]), 3), "p50": round(float(point + pct[49]), 3),
                      "p90": round(float(point + pct[89]), 3), "climatology": round(clim, 3), "base": round(base, 3),
                      "correction": round(correction, 3), "status": status, "kit": kit_name,
                      "sensors_used": list(entry["sensors"]), "reason": reason,
                      "track_record": {k: row.get(k) for k in ("skill_vs_climatology", "skill_vs_best_baseline", "coverage_p10_p90", "n")}}
            limit = _limit_for(target, limits)
            if limit is not None:
                result["weather_variable"] = limit.variable
                result["chance_at_or_above"] = {"caution": None if limit.caution is None else round(float((values >= limit.caution).mean()), 2),
                                                "warning": round(float((values >= limit.warning).mean()), 2)}
                result["limits"] = {"caution": limit.caution, "warning": limit.warning, "provenance": limit.provenance}
            forecasts.append(result)
    return {"issued_utc": issued.strftime("%Y-%m-%dT%H:%M:%SZ"), "model_id": model.id, "provenance": provenance,
            "station": model.station, "ltst_now": _fmt_ltst(now["ltst_h"]), "ls_deg": round(now["ls_deg"], 2),
            "sensors_fresh": [LABELS[v] for v in fresh], "latest": {v: {"value": val, "time_utc": t} for v, (val, t) in latest.items()},
            "forecasts": forecasts}


def forecast_messages(bundle, station_id):
    """ADVISORY WeatherMessages for limited variables; the value is the conservative P90."""
    out = []
    for f in bundle["forecasts"]:
        if "weather_variable" not in f:
            continue
        unit = "m/s" if f["weather_variable"] == "wind_speed" else "1"
        out.append(WeatherMessage(station_id=station_id, variable=f["weather_variable"], value=max(0.0, f["p90"]), unit=unit,
                                  kind="forecast", time_utc=bundle["issued_utc"], valid_to_utc=f["valid_utc"],
                                  provenance=bundle["provenance"],
                                  note=f"P90 of {f['horizon']} forecast (P10 {f['p10']:g}, P50 {f['p50']:g}); {f['status']} via {f['kit']}; "
                                       f"model {bundle['model_id']}"))
    return out


def command_view(bundle, assessment=None):
    """Everything the command centre needs to audit the forecast."""
    rows = [{"variable": f["label"], "horizon": f["horizon"], "valid_ltst": f["valid_ltst"], "p10": f["p10"], "p50": f["p50"],
             "p90": f["p90"], "unit": f["unit"], "climatology": f["climatology"], "correction": f["correction"],
             "status": f["status"], "kit": f["kit"], "reason": f["reason"], "chance_at_or_above": f.get("chance_at_or_above"),
             "track_record": f["track_record"]} for f in bundle["forecasts"]]
    flags = [f"{f['label']} {f['horizon']}: {int(100 * f['chance_at_or_above']['warning'])}% chance >= warning "
             f"{f['limits']['warning']:g} {f['unit']} (limit {f['limits']['provenance']})"
             for f in bundle["forecasts"] if f.get("chance_at_or_above") and f["chance_at_or_above"]["warning"] >= 0.1]
    return {"audience": "command_centre", "issued_utc": bundle["issued_utc"], "ltst_now": bundle["ltst_now"], "ls_deg": bundle["ls_deg"],
            "model_id": bundle["model_id"], "provenance": bundle["provenance"], "station": bundle["station"],
            "sensors_fresh": bundle["sensors_fresh"], "latest_observations": bundle["latest"], "advisory_flags": flags,
            "forecasts": rows, "weather_assessment": None if assessment is None else assessment.to_dict(),
            "rule": "Forecasts are advisory; only fresh observed values can change the plan."}


def crew_view(bundle, horizon="3h"):
    """At most three short lines for the astronaut, most important first."""
    by = {(f["target"], f["horizon"]): f for f in bundle["forecasts"]}
    lines, level = [], "nominal"
    for f in bundle["forecasts"]:
        chance = f.get("chance_at_or_above")
        if chance and chance["warning"] >= 0.1:
            level = "advisory"
            lines.append(f"ADVISORY {f['label']} may reach {f['p90']:.0f} {f['unit']} by {f['valid_ltst']} "
                         f"({int(100 * chance['warning'])}% chance >= {f['limits']['warning']:g}). Observed values decide.")
            break
    parts = []
    wind = by.get(("wind_ms", horizon))
    if wind:
        parts.append(f"wind {max(0, wind['p10']):.0f}-{wind['p90']:.0f} m/s")
    pressure = by.get(("pressure_pa", horizon))
    latest = bundle["latest"].get("pressure_pa")
    if pressure:
        trend = ""
        if latest:
            change = pressure["p50"] - latest["value"]
            trend = " steady" if abs(change) < 2 else (" rising" if change > 0 else " falling")
        parts.append(f"pressure {pressure['p50']:.0f} Pa{trend}")
    temp = by.get(("air_temp_k", horizon))
    if temp:
        parts.append(f"{temp['p50'] - 273.15:.0f} °C")
    dust = by.get(("dust_tau", horizon))
    if dust:
        parts.append(f"dust τ {dust['p50']:.1f}")
    if parts:
        lines.append(f"Next {horizon[:-1]} h to {_valid(by, horizon)} LTST: " + " · ".join(parts))
    used = sorted({s for f in bundle["forecasts"] if f["status"] == "model" for s in f["sensors_used"]})
    lines.append("Forecast from " + (", ".join(LABELS[s] for s in used) if used else "climatology only")
                 + (" · " + bundle["provenance"] if bundle["provenance"] != "measured" else "") + " · advisory")
    return {"audience": "astronaut", "level": level, "lines": lines[:3]}


def _valid(by, horizon):
    any_f = next((f for (t, h), f in by.items() if h == horizon), None)
    return any_f["valid_ltst"] if any_f else "?"


def main(argv=None):
    import argparse
    from .weather import assess_weather, feed_from_dict

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", type=Path)
    parser.add_argument("observations", type=Path, help="JSON with now_utc, observations[] and optionally a weather feed")
    parser.add_argument("--lon-east", type=float)
    args = parser.parse_args(argv)
    try:
        model = ForecastModel.load(args.model)
        data = json.loads(args.observations.read_text())
        bundle = issue_forecast(model, data["observations"], data["now_utc"], lon_east_deg=args.lon_east,
                                provenance=data.get("provenance", "simulated"))
        assessment = None
        if "feed" in data:
            feed = data["feed"]
            station = feed["stations"][0]["id"]
            feed = {**feed, "messages": list(feed.get("messages", [])) + [m.__dict__ for m in forecast_messages(bundle, station)]}
            assessment = assess_weather(feed_from_dict(feed), data["now_utc"])
        print(json.dumps({"command_centre": command_view(bundle, assessment), "astronaut": crew_view(bundle)},
                         indent=2, ensure_ascii=False))
        return 0
    except (MarswalkError, KeyError, OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
