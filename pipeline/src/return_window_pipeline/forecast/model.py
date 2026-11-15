"""Minimal-sensor station forecaster.

Question: with as few sensors as possible, how well can we forecast pressure, air temperature, wind
and dust optical depth 1, 3 and 6 Mars hours ahead at one site?

* Baseline ("clock" kit, no sensors): diurnal x seasonal climatology fitted on the training block.
* Kits: subsets of sensors available at issue time. Each kit gets an L2 ridge correction of the
  climatology from that kit's recent anomalies (now, 1-bin tendency, 3-bin mean) and time harmonics.
* Bands: split-conformal. Residual percentiles from a separate calibration block give P10/P50/P90
  and exceedance probabilities; no distributional assumption.
* Abstain: features outside the training range -> climatology, with the reason.
* Selection: for each target and horizon, the smallest kit whose test skill is within ``tolerance``
  of the best kit, beats every baseline (climatology, persistence, anomaly persistence) and keeps
  P10-P90 coverage >= ``min_coverage``. If none qualifies, the target ships as climatology.

Blocks are contiguous by sol (train | gap | calibration | gap | test) so nothing leaks forward.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
import hashlib
import json

import numpy as np

from .station import VARIABLES, Grid, StationDataError

SENSOR_ORDER = ("pressure_pa", "air_temp_k", "wind_ms", "dust_tau")
SENSOR_LABEL = {"pressure_pa": "barometer", "air_temp_k": "thermometer", "wind_ms": "anemometer",
                "dust_tau": "sky opacity"}
PERCENTILES = np.arange(1, 100)


@dataclass(frozen=True)
class Settings:
    horizons_h: tuple = (1, 3, 6)
    ls_window_deg: float = 10.0
    ls_step_deg: float = 5.0
    min_clim_count: int = 3
    l2: float = 1.0
    train_frac: float = 0.6
    cal_frac: float = 0.2
    gap_sols: int = 1
    tolerance: float = 0.02
    min_gain: float = 0.02
    min_coverage: float = 0.7
    min_samples: int = 100
    range_margin: float = 0.25


class Climatology:
    """Mean value per local-time bin in circular Ls windows, interpolated linearly between window centres."""

    def __init__(self, grid: Grid, sol_mask: np.ndarray, s: Settings, variables=None):
        self.bins = grid.bins
        self.centers = np.arange(0.0, 360.0, s.ls_step_deg)
        self.tables, self.support = {}, {}
        ls = grid.ls[sol_mask]
        for v in variables or grid.meta["variables_present"]:
            data = grid.values[v][sol_mask]
            fallback = _nanmean(data, axis=0)
            table = np.empty((self.bins, len(self.centers)))
            support = np.full((self.bins, len(self.centers)), 3, dtype=int)  # 0-2 = window widening step, 3 = global
            distance = np.abs((ls[None, :] - self.centers[:, None] + 180) % 360 - 180)
            for j in range(len(self.centers)):
                column = np.full(self.bins, np.nan)
                for step, window in enumerate((s.ls_window_deg, 2 * s.ls_window_deg, 4 * s.ls_window_deg)):
                    block = data[distance[j] <= window]  # widen the season window before giving up
                    count = np.isfinite(block).sum(axis=0) if len(block) else np.zeros(self.bins)
                    mean = _nanmean(block, axis=0) if len(block) else column
                    take = np.isnan(column) & (count >= s.min_clim_count)
                    support[take, j] = step
                    column = np.where(take, mean, column)
                table[:, j] = np.where(np.isnan(column), fallback, column)
            if np.isnan(table).any():
                table = np.where(np.isnan(table), np.nanmean(data), table)
            self.tables[v] = table
            self.support[v] = support

    @classmethod
    def from_dict(cls, data: dict):
        self = cls.__new__(cls)
        self.bins = data["bins"]
        self.centers = np.asarray(data["ls_centers_deg"], dtype=float)
        self.tables = {v: np.asarray(t, dtype=float) for v, t in data["tables"].items()}
        self.support = {v: np.asarray(t, dtype=int) for v, t in data.get("support", {}).items()}
        return self

    def __call__(self, variable: str, bin_index: np.ndarray, ls: np.ndarray) -> np.ndarray:
        table = self.tables[variable]
        step = self.centers[1] - self.centers[0]
        pos = (np.asarray(ls) % 360) / step
        lo = np.floor(pos).astype(int) % len(self.centers)
        hi = (lo + 1) % len(self.centers)
        w = pos - np.floor(pos)
        b = np.asarray(bin_index) % self.bins
        return table[b, lo] * (1 - w) + table[b, hi] * w

    def to_dict(self):
        return {"bins": self.bins, "ls_centers_deg": self.centers.tolist(),
                "tables": {v: np.round(t, 4).tolist() for v, t in self.tables.items()},
                "support": {v: t.tolist() for v, t in self.support.items()},
                "support_levels": ["Ls window", "2x window", "4x window", "season not in training (all-season mean)"]}


def _nanmean(a, axis=None):
    a = np.asarray(a, dtype=float)
    count = np.isfinite(a).sum(axis=axis)
    total = np.nansum(a, axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def feature_names(kit: tuple, target: str) -> list[str]:
    names = []
    for v in kit:
        names += [f"{v}:tendency", f"{v}:now_minus_mean3"] if v == target else \
                 [f"{v}:anom_now", f"{v}:anom_tendency", f"{v}:anom_mean3"]
    return names + ["sin_target_time", "cos_target_time", "sin_ls", "cos_ls"]


def uses_persistence(kit: tuple, target: str) -> bool:
    """Kits that include the target's own sensor start from anomaly persistence, otherwise from climatology."""
    return target in kit


def build_features(anom: dict, kit: tuple, k: np.ndarray, h_bins: int, bins: int, ls_flat: np.ndarray, target: str):
    """Features at issue indices k. Returns (X, valid). Uses only values at k, k-1, k-2.

    The target's own sensor contributes level-free features (its level is already in the persistence base),
    so a climatology offset in an unseen season does not push the inputs out of range."""
    cols, valid = [], np.ones(len(k), dtype=bool)
    for v in kit:
        a = anom[v]
        now, prev = a[k], a[np.maximum(k - 1, 0)]
        older = a[np.maximum(k - 2, 0)]
        valid &= np.isfinite(now) & np.isfinite(prev) & (k >= 2)
        mean3 = _nanmean(np.vstack([now, prev, older]), axis=0)
        cols += [now - prev, now - mean3] if v == target else [now, now - prev, mean3]
    phase = 2 * np.pi * ((k + h_bins) % bins) / bins
    lsr = np.radians(ls_flat[k])
    cols += [np.sin(phase), np.cos(phase), np.sin(lsr), np.cos(lsr)]
    x = np.column_stack(cols)
    return x, valid & np.isfinite(x).all(axis=1)


class Ridge:
    def fit(self, x, y, l2):
        self.mean = x.mean(0)
        self.scale = np.where(x.std(0) > 0, x.std(0), 1.0)
        z = (x - self.mean) / self.scale
        self.intercept = float(y.mean())
        a = z.T @ z + l2 * np.eye(z.shape[1])
        self.coef = np.linalg.solve(a, z.T @ (y - self.intercept))
        return self

    def predict(self, x):
        return self.intercept + ((x - self.mean) / self.scale) @ self.coef


def _blocks(n_sols: int, s: Settings) -> np.ndarray:
    """0 = train, 1 = calibration, 2 = test, -1 = gap."""
    block = np.full(n_sols, -1)
    a = int(round(n_sols * s.train_frac))
    b = int(round(n_sols * (s.train_frac + s.cal_frac)))
    block[:a] = 0
    block[a + s.gap_sols:b] = 1
    block[b + s.gap_sols:] = 2
    if (block == 0).sum() < 10 or (block == 1).sum() < 3 or (block == 2).sum() < 3:
        raise StationDataError(f"Too few sols ({n_sols}) for train/calibration/test blocks")
    return block


def candidate_kits(present: list[str]) -> list[tuple]:
    sensors = [v for v in SENSOR_ORDER if v in present]
    kits = [()]
    for size in range(1, len(sensors) + 1):
        kits += [tuple(c) for c in combinations(sensors, size)]
    return kits


def kit_id(kit: tuple) -> str:
    return "clock" if not kit else "+".join(SENSOR_LABEL[v] for v in kit)


class Prepared:
    def __init__(self, grid: Grid, clim: Climatology):
        self.grid, self.clim, self.bins = grid, clim, grid.bins
        n = len(grid.sols) * grid.bins
        self.k = np.arange(n)
        self.ls = grid.flat_ls
        self.bin = self.k % grid.bins
        self.values = {v: grid.flat(v) for v in grid.meta["variables_present"]}
        self.climv = {v: clim(v, self.bin, self.ls) for v in self.values}
        self.anom = {v: self.values[v] - self.climv[v] for v in self.values}
        self.sol_index = self.k // grid.bins


def _fit_kit(p: Prepared, target, kit, h, idx, s):
    x, ok = build_features(p.anom, kit, idx, h, p.bins, p.ls, target)
    y = p.anom[target][idx + h] - (p.anom[target][idx] if uses_persistence(kit, target) else 0.0)
    ok &= np.isfinite(y)
    if ok.sum() < s.min_samples:
        return None
    model = Ridge().fit(x[ok], y[ok], s.l2)
    span = x[ok].max(0) - x[ok].min(0)
    model.ranges = np.vstack([x[ok].min(0) - s.range_margin * span, x[ok].max(0) + s.range_margin * span])
    model.n_train = int(ok.sum())
    return model


def _predict(p: Prepared, target, kit, h, idx, model):
    """Point forecast (value units) and abstain flags at issue indices idx."""
    clim = p.climv[target][idx + h]
    if not kit or model is None:
        return clim, np.zeros(len(idx), dtype=bool)
    base = clim + p.anom[target][idx] if uses_persistence(kit, target) else clim
    x, ok = build_features(p.anom, kit, idx, h, p.bins, p.ls, target)
    inside = ok & np.isfinite(base) & np.all((x >= model.ranges[0]) & (x <= model.ranges[1]), axis=1)
    point = np.where(inside, base + model.predict(np.where(np.isfinite(x), x, 0.0)), clim)
    return point, ~inside


def _metrics(pred, y, lo=None, hi=None, ref_mae=None):
    err = np.abs(pred - y)
    out = {"n": int(len(y)), "mae": float(err.mean()), "rmse": float(np.sqrt(((pred - y) ** 2).mean()))}
    if lo is not None:
        out["coverage_p10_p90"] = float(((y >= lo) & (y <= hi)).mean())
        out["mean_band_width"] = float((hi - lo).mean())
    if ref_mae:
        out.update({k: (1 - out["mae"] / v if v > 0 else None) for k, v in ref_mae.items()})
    return out


def train_and_evaluate(grid: Grid, s: Settings = Settings(), *, transfer: Grid | None = None) -> dict:
    present = grid.meta["variables_present"]
    if not present:
        raise StationDataError("No variables present")
    blocks = _blocks(len(grid.sols), s)
    clim = Climatology(grid, blocks == 0, s)
    p = Prepared(grid, clim)
    block_of = blocks[p.sol_index]
    kits = candidate_kits(present)
    horizons = {h: max(1, int(round(h * grid.bins / 24))) for h in s.horizons_h}
    models, rows, selection = {}, [], {}
    gbm = _gbm()
    for target in present:
        models[target] = {}
        selection[target] = {}
        for h_hours, h in horizons.items():
            n = len(p.k) - h
            same = lambda b: np.nonzero((block_of[:n] == b) & (block_of[h:h + n] == b))[0]
            train_idx, cal_idx, test_idx = same(0), same(1), same(2)
            fitted = {}
            for kit in kits:  # kits[0] is the clock kit; its bands are the fallback for abstained points
                model = _fit_kit(p, target, kit, h, train_idx, s) if kit else None
                if kit and model is None:
                    continue
                pred, abstain = _predict(p, target, kit, h, cal_idx, model)
                y = p.values[target][cal_idx + h]
                ok = np.isfinite(y) & np.isfinite(pred)
                if kit:
                    ok &= ~abstain  # abstained points fall back to climatology and its bands
                if ok.sum() < 20:
                    continue
                residual_pct = np.percentile(y[ok] - pred[ok], PERCENTILES)
                fitted[kit] = (model, residual_pct, int(ok.sum()))
            if () not in fitted:
                selection[target][f"{h_hours}h"] = {"status": "insufficient_calibration_data", "kit": "clock"}
                continue
            # common test set: target observed at issue and at valid time, and every fitted kit valid
            y_now = p.values[target][test_idx]
            y_true = p.values[target][test_idx + h]
            common = np.isfinite(y_now) & np.isfinite(y_true)
            for kit in fitted:
                if kit:
                    common &= build_features(p.anom, kit, test_idx, h, p.bins, p.ls, target)[1]
            idx = test_idx[common]
            y = p.values[target][idx + h]
            key = f"{h_hours}h"
            if len(idx) < 20:
                selection[target][key] = {"status": "insufficient_test_data", "kit": "clock", "n_test": int(len(idx))}
                continue
            clim_pred = p.climv[target][idx + h]
            persist = p.values[target][idx]
            anom_persist = clim_pred + p.anom[target][idx]
            ref = {"skill_vs_climatology": np.abs(clim_pred - y).mean()}
            best_baseline = min(np.abs(clim_pred - y).mean(), np.abs(persist - y).mean(), np.abs(anom_persist - y).mean())
            ref["skill_vs_best_baseline"] = best_baseline
            for name, pred in (("baseline:climatology", clim_pred), ("baseline:persistence", persist),
                               ("baseline:anomaly_persistence", anom_persist)):
                rows.append({"target": target, "horizon_h": h_hours, "kit": name, "sensors": 0, **_metrics(pred, y, ref_mae=ref)})
            models[target][key] = {}
            candidates = []
            for kit, (model, pct, n_cal) in fitted.items():
                pred, abstain = _predict(p, target, kit, h, idx, model)
                clock_pct = fitted[()][1]
                lo = np.where(abstain, pred + clock_pct[9], pred + pct[9])
                hi = np.where(abstain, pred + clock_pct[89], pred + pct[89])
                m = _metrics(pred, y, lo, hi, ref)
                m["abstain_rate"] = float(abstain.mean())
                rows.append({"target": target, "horizon_h": h_hours, "kit": kit_id(kit), "sensors": len(kit), **m})
                models[target][key][kit_id(kit)] = _serialise(kit, model, pct, n_cal, h, target)
                if (kit and m["skill_vs_climatology"] >= s.min_gain and m["skill_vs_best_baseline"] >= -s.tolerance
                        and m["coverage_p10_p90"] >= s.min_coverage):
                    candidates.append((kit, m))
            if gbm is not None and len(fitted) > 1:
                full = max((k for k in fitted if k), key=len)
                rows.append(_gbm_row(gbm, p, target, full, h, train_idx, idx, y, ref, h_hours))
            if candidates:
                best = max(m["skill_vs_climatology"] for _, m in candidates)
                good = [(kit, m) for kit, m in candidates if m["skill_vs_climatology"] >= best - s.tolerance]
                kit, m = min(good, key=lambda item: (len(item[0]), -item[1]["skill_vs_climatology"]))
                gain = m["skill_vs_best_baseline"]
                selection[target][key] = {"status": "model", "kit": kit_id(kit), "sensors": list(kit),
                                          "base": "anomaly_persistence" if uses_persistence(kit, target) else "climatology",
                                          "skill_vs_climatology": m["skill_vs_climatology"],
                                          "skill_vs_best_baseline": gain,
                                          "ml_adds_over_best_baseline": bool(gain >= s.min_gain),
                                          "coverage_p10_p90": m["coverage_p10_p90"], "best_kit_skill": best, "n_test": m["n"]}
            else:
                anomaly_skill = 1 - np.abs(anom_persist - y).mean() / ref["skill_vs_climatology"]
                selection[target][key] = {"status": "climatology", "kit": "clock", "sensors": [], "n_test": int(len(idx)),
                                          "reason": (f"no sensor kit beat climatology by {s.min_gain}, stayed within "
                                                     f"{s.tolerance} of every baseline and kept P10-P90 coverage >= {s.min_coverage}"),
                                          "anomaly_persistence_skill_vs_climatology": float(anomaly_skill)}
    result = {"climatology": clim.to_dict(), "models": models, "rows": [_round(r) for r in rows],
              "selection": _round(selection), "kits": {kit_id(k): list(k) for k in kits},
              "horizons": {f"{h}h": b for h, b in horizons.items()},
              "blocks": {"train_sols": int((blocks == 0).sum()), "calibration_sols": int((blocks == 1).sum()),
                         "test_sols": int((blocks == 2).sum()), "gap_sols": s.gap_sols},
              "challenger": "sklearn HistGradientBoostingRegressor on the full kit (evaluation only)" if gbm else None}
    if transfer is not None:
        result["transfer"] = evaluate_transfer(result, transfer, s)
    return result


def _serialise(kit, model, pct, n_cal, h, target):
    entry = {"sensors": list(kit), "horizon_bins": h, "features": feature_names(kit, target) if kit else [],
             "base": "anomaly_persistence" if uses_persistence(kit, target) else "climatology",
             "residual_percentiles": np.round(pct, 4).tolist(), "n_calibration": n_cal}
    if model is not None:
        entry.update({"mean": model.mean.tolist(), "scale": model.scale.tolist(), "coef": model.coef.tolist(),
                      "intercept": model.intercept, "ranges": model.ranges.tolist(), "n_train": model.n_train})
    return entry


def _gbm():
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
    except ImportError:
        return None
    return HistGradientBoostingRegressor


def _gbm_row(cls, p, target, kit, h, train_idx, idx, y, ref, h_hours):
    x, ok = build_features(p.anom, kit, train_idx, h, p.bins, p.ls, target)
    yt = p.anom[target][train_idx + h] - p.anom[target][train_idx]
    ok &= np.isfinite(yt)
    model = cls(max_iter=200, random_state=0).fit(x[ok], yt[ok])
    xt, _ = build_features(p.anom, kit, idx, h, p.bins, p.ls, target)
    pred = p.climv[target][idx + h] + p.anom[target][idx] + model.predict(xt)
    return {"target": target, "horizon_h": h_hours, "kit": "challenger:gbm:" + kit_id(kit), "sensors": len(kit),
            **_metrics(pred, y, ref_mae=ref)}


def evaluate_transfer(result: dict, other: Grid, s: Settings) -> list[dict]:
    """Apply the trained corrections at another site. Climatology is refitted on that site's training block."""
    blocks = _blocks(len(other.sols), s)
    present = [v for v in other.meta["variables_present"] if v in result["models"]]
    clim = Climatology(other, blocks == 0, s, present)
    p = Prepared(Grid(other.sols, other.ls, other.bins, {v: other.values[v] for v in present},
                      {**other.meta, "variables_present": present}), clim)
    block_of = blocks[p.sol_index]
    rows = []
    for target in present:
        for key, kits in result["models"][target].items():
            h = result["horizons"][key]
            n = len(p.k) - h
            idx = np.nonzero((block_of[:n] == 2) & (block_of[h:h + n] == 2))[0]
            y = p.values[target][idx + h]
            ok = np.isfinite(y) & np.isfinite(p.values[target][idx])
            idx, y = idx[ok], y[ok]
            if len(idx) < 20:
                continue
            clim_mae = np.abs(p.climv[target][idx + h] - y).mean()
            for name, entry in kits.items():
                kit = tuple(entry["sensors"])
                if any(v not in present for v in kit):
                    continue
                model = _model_from(entry) if kit else None
                _, valid = build_features(p.anom, kit, idx, h, p.bins, p.ls, target) if kit else (None, np.ones(len(idx), bool))
                pred, abstain = _predict(p, target, kit, h, idx[valid], model)
                pct = np.asarray(entry["residual_percentiles"])
                m = _metrics(pred, y[valid], pred + pct[9], pred + pct[89], {"skill_vs_local_climatology": clim_mae})
                rows.append(_round({"target": target, "horizon_h": int(key[:-1]), "kit": name, **m,
                                    "abstain_rate": float(abstain.mean())}))
    return rows


def _model_from(entry):
    model = Ridge()
    model.mean, model.scale = np.asarray(entry["mean"]), np.asarray(entry["scale"])
    model.coef, model.intercept = np.asarray(entry["coef"]), entry["intercept"]
    model.ranges = np.asarray(entry["ranges"])
    return model


def _round(value):
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return None if not np.isfinite(value) else round(float(value), 4)
    if isinstance(value, np.integer):
        return int(value)
    return value


def build_artifact(grid: Grid, s: Settings = Settings(), *, transfer: Grid | None = None) -> dict:
    result = train_and_evaluate(grid, s, transfer=transfer)
    meta = grid.meta
    artifact = {
        "schema_version": 1,
        "classification": "station_forecast_minimal_sensor",
        "station": {k: meta.get(k) for k in ("station_id", "name", "lat_deg", "lon_east_deg", "provenance", "sources")},
        "time_axis": {"bins_per_sol": grid.bins, "local_time": meta.get("local_time", "LTST"),
                      "sols": [int(grid.sols[0]), int(grid.sols[-1])]},
        "variables": {v: {"unit": VARIABLES[v]["unit"], "label": VARIABLES[v]["label"],
                          "weather_variable": VARIABLES[v].get("weather_variable")} for v in meta["variables_present"]},
        "settings": {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(s).items()},
        "method": ("climatology (local-time bin x Ls window) + ridge correction from the kit's recent anomalies; "
                   "split-conformal P10/P50/P90 from a held-out calibration block; abstain to climatology outside "
                   "the training feature range; the smallest kit within tolerance of the best kit that beats climatology by "
                   "min_gain with adequate coverage. ml_adds_over_best_baseline says whether the learned correction beats "
                   "plain persistence baselines by min_gain, i.e. whether ML, not persistence, earns the skill"),
        **result,
        "limitations": [
            "One training site: corrections are local and degrade elsewhere (see transfer rows when provided).",
            "Dust storms are rare in any station record; storm-time skill is not established unless reported separately.",
            "Bands come from calibration-block residuals and assume the test period behaves like it.",
            "Advisory only: in the runtime a forecast never changes the plan; observed values do.",
        ],
    }
    body = json.dumps(artifact, sort_keys=True, allow_nan=False)
    artifact["model_id"] = "station-forecast-" + hashlib.sha256(body.encode()).hexdigest()[:16]
    return artifact
