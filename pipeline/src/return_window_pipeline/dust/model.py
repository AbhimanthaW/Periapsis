"""Dust outlook: will a mapped dust storm cover a region within the next H sols?

Target (per region r, Mars year y, anchor sol t with the region's core observed):
    Y = 1 if any observed sol in t+1..t+H has a mapped storm over >= ``storm_fraction`` of the core disc.

Baseline: seasonal climatology P(Y | region, Ls), estimated from training years only with a circular
Ls window and shrinkage toward the all-region rate for that season.

Model: L2-regularised logistic regression (numpy IRLS, deterministic) on the climatology logit plus
present and past observations (core and surrounding-ring storm coverage), and season harmonics.
Only information available at sol t is used.

Validation: leave-one-Mars-year-out. Each held-out year is scored against a climatology fitted
without that year. The artifact exposes model outputs only if pooled Brier skill over climatology
passes ``min_bss`` and is positive in a majority of held-out years; otherwise it ships climatology
alone and says so.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math

import numpy as np

from .mdad import DATASET_VERSION, DOI, DustDataError

FEATURES = ("clim_logit", "core_now", "core_max_3", "core_days_7", "ring_now", "ring_mean_7", "ring_missing",
            "sin_ls", "cos_ls", "sin_2ls", "cos_2ls")
RECENT = ("core_now", "core_max_3", "core_days_7", "ring_now", "ring_mean_7", "ring_missing")
LS_BINS = np.arange(15.0, 360.0, 30.0)


@dataclass(frozen=True)
class Settings:
    horizon_sols: int = 7
    storm_fraction: float = 0.10
    ring_nearby_fraction: float = 0.02
    core_coverage: float = 0.5
    ring_coverage: float = 0.3
    future_coverage: float = 0.6
    clim_window_deg: int = 15
    clim_shrinkage: float = 10.0
    l2: float = 1.0
    min_bss: float = 0.02
    min_bin_samples: int = 20


@dataclass
class Samples:
    region: np.ndarray
    year: np.ndarray
    ls: np.ndarray
    y: np.ndarray
    recent: np.ndarray  # (n, len(RECENT))
    extra: dict = field(default_factory=dict)


def _daily(year_data: dict, core_total: np.ndarray, ring_total: np.ndarray, s: Settings):
    sol, ls, counts = year_data["sol"], year_data["ls"], year_data["counts"].astype(float)
    nreg = counts.shape[1]
    length = int(sol.max()) + s.horizon_sols + 2
    shape = (length, nreg)
    core_frac = np.full(shape, np.nan)
    ring_frac = np.full(shape, np.nan)
    ls_day = np.full(length, np.nan)
    core_ok = counts[:, :, 0] >= s.core_coverage * core_total
    ring_ok = counts[:, :, 2] >= s.ring_coverage * np.maximum(ring_total, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        core_frac[sol] = np.where(core_ok, counts[:, :, 1] / counts[:, :, 0], np.nan)
        ring_frac[sol] = np.where(ring_ok, counts[:, :, 3] / counts[:, :, 2], np.nan)
    ls_day[sol] = ls
    return core_frac, ring_frac, ls_day


def build_samples(series: dict, s: Settings) -> Samples:
    regions, years, ls_all, ys, recent = [], [], [], [], []
    need = math.ceil(s.future_coverage * s.horizon_sols)
    for my, data in sorted(series["years"].items()):
        core, ring, ls_day = _daily(data, series["core_total"], series["ring_total"], s)
        storm = np.where(np.isnan(core), np.nan, (core >= s.storm_fraction).astype(float))
        length, nreg = core.shape
        for t in range(7, length - s.horizon_sols - 1):
            if np.isnan(ls_day[t]):
                continue
            future = storm[t + 1:t + 1 + s.horizon_sols]
            observed_future = np.sum(~np.isnan(future), axis=0)
            label = np.nansum(future, axis=0) > 0
            past_core = core[t - 6:t + 1]
            past_storm = storm[t - 6:t + 1]
            past_ring = ring[t - 6:t + 1]
            keep = ~np.isnan(core[t]) & (observed_future >= need)
            if not keep.any():
                continue
            idx = np.nonzero(keep)[0]
            with np.errstate(all="ignore"):
                ring_now = ring[t, idx]
                ring_mean = np.nanmean(past_ring[:, idx], axis=0)
                features = np.column_stack([
                    core[t, idx],
                    np.nanmax(past_core[-3:, idx], axis=0),
                    np.nansum(past_storm[:, idx], axis=0) / 7.0,
                    np.nan_to_num(ring_now, nan=0.0),
                    np.nan_to_num(ring_mean, nan=0.0),
                    np.isnan(ring_now).astype(float),
                ])
            regions.append(idx)
            years.append(np.full(len(idx), my))
            ls_all.append(np.full(len(idx), ls_day[t]))
            ys.append(label[idx].astype(float))
            recent.append(features)
    if not regions:
        raise DustDataError("No usable samples; check coverage settings and the extracted series")
    return Samples(np.concatenate(regions), np.concatenate(years), np.concatenate(ls_all), np.concatenate(ys),
                   np.vstack(recent))


class Climatology:
    """P(Y | region, Ls) from circular Ls windows, shrunk toward the all-region seasonal rate."""

    def __init__(self, samples: Samples, mask: np.ndarray, nreg: int, s: Settings):
        bins = np.floor(samples.ls[mask]).astype(int) % 360
        reg = samples.region[mask]
        pos = np.zeros((nreg, 360))
        cnt = np.zeros((nreg, 360))
        np.add.at(pos, (reg, bins), samples.y[mask])
        np.add.at(cnt, (reg, bins), 1)
        w = s.clim_window_deg
        kernel_pos = sum(np.roll(pos, k, axis=1) for k in range(-w, w + 1))
        kernel_cnt = sum(np.roll(cnt, k, axis=1) for k in range(-w, w + 1))
        global_rate = (kernel_pos.sum(0) + 0.5) / (kernel_cnt.sum(0) + 1.0)
        self.p = (kernel_pos + s.clim_shrinkage * global_rate) / (kernel_cnt + s.clim_shrinkage)
        self.n = kernel_cnt

    def __call__(self, region: np.ndarray, ls: np.ndarray) -> np.ndarray:
        return self.p[region, np.floor(ls).astype(int) % 360]

    def count(self, region: np.ndarray, ls: np.ndarray) -> np.ndarray:
        return self.n[region, np.floor(ls).astype(int) % 360]


def _logit(p):
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return np.log(p / (1 - p))


def design(recent: np.ndarray, ls: np.ndarray, clim_p: np.ndarray) -> np.ndarray:
    a = np.radians(ls)
    return np.column_stack([_logit(clim_p), recent, np.sin(a), np.cos(a), np.sin(2 * a), np.cos(2 * a)])


class Logistic:
    """L2 logistic regression fitted by iteratively reweighted least squares (intercept unpenalised)."""

    def fit(self, x: np.ndarray, y: np.ndarray, l2: float, iterations: int = 50, tol: float = 1e-9):
        self.mean = x.mean(0)
        self.scale = np.where(x.std(0) > 0, x.std(0), 1.0)
        z = np.column_stack([np.ones(len(x)), (x - self.mean) / self.scale])
        w = np.zeros(z.shape[1])
        penalty = np.full(z.shape[1], l2)
        penalty[0] = 0.0
        for _ in range(iterations):
            p = 1 / (1 + np.exp(-np.clip(z @ w, -30, 30)))
            gradient = z.T @ (p - y) + penalty * w
            hessian = (z * (p * (1 - p))[:, None]).T @ z + np.diag(penalty)
            step = np.linalg.solve(hessian + 1e-9 * np.eye(len(w)), gradient)
            w -= step
            if np.max(np.abs(step)) < tol:
                break
        self.coef = w
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        z = np.column_stack([np.ones(len(x)), (x - self.mean) / self.scale])
        return 1 / (1 + np.exp(-np.clip(z @ self.coef, -30, 30)))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def auc(p, y):
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    for value in np.unique(p):  # average ties
        tie = p == value
        if tie.sum() > 1:
            ranks[tie] = ranks[tie].mean()
    npos = y.sum()
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return None
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def reliability(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    index = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return [{"bin": [round(edges[i], 2), round(edges[i + 1], 2)], "n": int((index == i).sum()),
             "mean_predicted": round(float(p[index == i].mean()), 4) if (index == i).any() else None,
             "observed": round(float(y[index == i].mean()), 4) if (index == i).any() else None} for i in range(bins)]


def cross_validate(samples: Samples, nreg: int, s: Settings) -> dict:
    folds = []
    pm, pc, yy = [], [], []
    for test_year in sorted(np.unique(samples.year)):
        train = samples.year != test_year
        test = ~train
        if test.sum() == 0 or train.sum() == 0:
            continue
        clim = Climatology(samples, train, nreg, s)
        x_train = design(samples.recent[train], samples.ls[train], clim(samples.region[train], samples.ls[train]))
        clim_test = clim(samples.region[test], samples.ls[test])
        x_test = design(samples.recent[test], samples.ls[test], clim_test)
        model = Logistic().fit(x_train, samples.y[train], s.l2)
        pred = model.predict(x_test)
        y = samples.y[test]
        b_model, b_clim = brier(pred, y), brier(clim_test, y)
        folds.append({"test_mars_year": int(test_year), "samples": int(test.sum()), "positive_rate": round(float(y.mean()), 4),
                      "brier_model": round(b_model, 5), "brier_climatology": round(b_clim, 5),
                      "brier_skill_score": round(1 - b_model / b_clim, 4) if b_clim > 0 else None,
                      "auc_model": _r(auc(pred, y)), "auc_climatology": _r(auc(clim_test, y))})
        pm.append(pred)
        pc.append(clim_test)
        yy.append(y)
    if not folds:
        raise DustDataError("Cross-validation needs at least two Mars years")
    pm, pc, yy = np.concatenate(pm), np.concatenate(pc), np.concatenate(yy)
    b_model, b_clim = brier(pm, yy), brier(pc, yy)
    bss = 1 - b_model / b_clim if b_clim > 0 else -1.0
    positive_folds = sum(1 for f in folds if (f["brier_skill_score"] or 0) > 0)
    skilful = bss >= s.min_bss and positive_folds > len(folds) / 2
    return {"scheme": "leave-one-Mars-year-out", "folds": folds,
            "pooled": {"samples": int(len(yy)), "positive_rate": round(float(yy.mean()), 4),
                       "brier_model": round(b_model, 5), "brier_climatology": round(b_clim, 5),
                       "brier_skill_score": round(bss, 4), "auc_model": _r(auc(pm, yy)), "auc_climatology": _r(auc(pc, yy)),
                       "folds_with_positive_skill": positive_folds},
            "reliability_model": reliability(pm, yy), "reliability_climatology": reliability(pc, yy),
            "gate": {"min_bss": s.min_bss, "requires_majority_of_folds": True, "passed": bool(skilful)},
            "status": "model_skilful" if skilful else "climatology_only"}


def _r(value, digits=4):
    return None if value is None else round(float(value), digits)


def sensitivity(series: dict, nreg: int, base: Settings) -> list[dict]:
    rows = []
    for horizon in (3, 7, 14):
        for fraction in (0.05, 0.10, 0.20):
            s = Settings(**{**asdict(base), "horizon_sols": horizon, "storm_fraction": fraction})
            result = cross_validate(build_samples(series, s), nreg, s)
            rows.append({"horizon_sols": horizon, "storm_fraction": fraction, **{k: result["pooled"][k] for k in (
                "samples", "positive_rate", "brier_skill_score", "auc_model", "auc_climatology")}, "status": result["status"]})
    return rows


def scenario_inputs(samples: Samples, s: Settings) -> dict[str, np.ndarray]:
    quiet = np.zeros(len(RECENT))
    nearby_rows = samples.recent[(samples.recent[:, 3] >= s.ring_nearby_fraction) & (samples.recent[:, 0] < s.storm_fraction)]
    nearby = np.median(nearby_rows, axis=0) if len(nearby_rows) else None
    if nearby is not None:
        nearby[[0, 1, 2, 5]] = 0.0  # core clear, ring observed
    return {"quiet": quiet, "nearby": nearby}


def build_artifact(series: dict, s: Settings, *, with_sensitivity: bool = True) -> dict:
    ids = series["region_ids"]
    nreg = len(ids)
    samples = build_samples(series, s)
    validation = cross_validate(samples, nreg, s)
    everything = np.ones(len(samples.y), dtype=bool)
    clim = Climatology(samples, everything, nreg, s)
    model = Logistic().fit(design(samples.recent, samples.ls, clim(samples.region, samples.ls)), samples.y, s.l2)
    scenarios = scenario_inputs(samples, s)
    skilful = validation["status"] == "model_skilful"
    regions = {}
    for r, region_id in enumerate(ids):
        reg = np.full(len(LS_BINS), r)
        p = clim(reg, LS_BINS)
        n = clim.count(reg, LS_BINS)
        enough = n >= s.min_bin_samples
        entry = {"climatology": [round(float(v), 4) if ok else None for v, ok in zip(p, enough)],
                 "samples": [int(v) for v in n]}
        if skilful:
            for name, recent in scenarios.items():
                if recent is None:
                    entry[name] = None
                    continue
                x = design(np.tile(recent, (len(LS_BINS), 1)), LS_BINS, p)
                entry[name] = [round(float(v), 4) if ok else None for v, ok in zip(model.predict(x), enough)]
        regions[region_id] = entry
    manifest = series["manifest"]
    artifact = {
        "schema_version": 1,
        "classification": "historical_storm_climatology_and_conditional_model",
        "target": {"horizon_sols": s.horizon_sols, "storm_fraction_of_core": s.storm_fraction,
                   "definition": f"A mapped MDAD storm covers at least {s.storm_fraction:.0%} of the region's core disc "
                                 f"on an observed sol within the next {s.horizon_sols} sols"},
        "geometry": {"core_radius_km": manifest["method"]["core_radius_km"], "ring_radius_km": manifest["method"]["ring_radius_km"],
                     "grid_convention": manifest["grid"]["convention"]["name"]},
        "source": {"doi": DOI, "dataset_version": DATASET_VERSION,
                   "mars_years": sorted(int(y) for y in series["years"]),
                   "series_sha256": manifest["series_sha256"], "files": manifest["source"]["files"]},
        "settings": asdict(s),
        "features": list(FEATURES),
        "coefficients_standardized": {"intercept": round(float(model.coef[0]), 4),
                                      **{name: round(float(c), 4) for name, c in zip(FEATURES, model.coef[1:])}},
        "scenarios": {"quiet": "No mapped storm over the core disc or the surrounding ring during the past 7 sols",
                      "nearby": f"A mapped storm covers at least {s.ring_nearby_fraction:.0%} of the surrounding ring today (training median of such sols) while the core is clear"},
        "validation": validation,
        "sensitivity": sensitivity(series, nreg, s) if with_sensitivity else [],
        "ls_bins_deg": [float(v) for v in LS_BINS],
        "status": validation["status"],
        "regions": regions,
        "limitations": [
            "MDAD maps storms of about 1e5 km2 and larger in daily global images; dust devils and small local storms are absent.",
            "Missing pixels (polar night, data gaps) are not storms; sols without coverage are excluded, which can understate storms.",
            "Water-ice clouds near the polar hood can be hard to separate from dust in visible maps.",
            "Five MARCI Mars years (MY28-32) is a short record; MY28 includes the 2007 global dust event.",
            "This is a historical and conditional estimate, not a live forecast: no observation after MY32 is used.",
        ],
    }
    body = json.dumps(artifact, sort_keys=True, allow_nan=False)
    artifact["artifact_id"] = "dust-outlook-" + hashlib.sha256(body.encode()).hexdigest()[:16]
    return artifact
