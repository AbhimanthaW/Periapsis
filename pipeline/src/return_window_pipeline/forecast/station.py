"""Canonical station table and the sol x local-time grid the forecaster trains on.

Canonical CSV columns (empty cell = missing):

    sol, ltst_h, ls_deg, pressure_pa, air_temp_k, wind_ms, dust_tau

``sol`` is a monotonic local sol counter. Rows may come from archive files with UTC timestamps
(converted here with Mars24) or from products that already give sol, local time and Ls (Viking binned
data). ``ingest`` maps source columns onto these names; it never guesses a column.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ..errors import PipelineError
from .marstime import mars_time, parse_utc

VARIABLES = {
    "pressure_pa": {"unit": "Pa", "valid": (50.0, 1500.0), "label": "pressure"},
    "air_temp_k": {"unit": "K", "valid": (100.0, 320.0), "label": "air temperature"},
    "wind_ms": {"unit": "m/s", "valid": (0.0, 100.0), "label": "wind speed", "weather_variable": "wind_speed"},
    "dust_tau": {"unit": "1", "valid": (0.0, 15.0), "label": "dust optical depth", "weather_variable": "dust_optical_depth"},
}
CANONICAL = ("sol", "ltst_h", "ls_deg", *VARIABLES)


class StationDataError(PipelineError):
    """Station records do not match the declared mapping."""


@dataclass
class Grid:
    """Values on (sol, bin) for each variable; ``ls`` per sol; ``sols`` are consecutive integers."""
    sols: np.ndarray
    ls: np.ndarray
    bins: int
    values: dict  # variable -> (n_sols, bins) float array, NaN = missing
    meta: dict

    @property
    def flat_ls(self) -> np.ndarray:
        return np.repeat(self.ls, self.bins)

    def flat(self, variable: str) -> np.ndarray:
        return self.values[variable].reshape(-1)


def _number(text):
    if text is None:
        return math.nan
    text = str(text).strip()
    if text == "" or text.lower() in ("nan", "na", "null", "none", "-"):
        return math.nan
    try:
        value = float(text)
    except ValueError:
        return math.nan
    return value if math.isfinite(value) else math.nan


def ingest_rows(path: Path, mapping: dict, *, lon_east: float | None = None, scale: dict | None = None,
                delimiter: str | None = None) -> tuple[list[dict], dict]:
    """Read one source CSV into canonical rows. ``mapping`` maps canonical names (or ``time_utc``) to source columns."""
    scale = scale or {}
    text = Path(path).read_text(errors="replace")
    sample = text[:4096]
    dialect_delim = delimiter or (";" if sample.count(";") > sample.count(",") else ",")
    reader = csv.DictReader(text.splitlines(), delimiter=dialect_delim, skipinitialspace=True)
    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    missing = [col for col in mapping.values() if col not in header]
    if missing:
        raise StationDataError(f"{Path(path).name}: columns {missing} not in header {header[:20]}")
    use_utc = "time_utc" in mapping
    if not use_utc and not all(k in mapping for k in ("sol", "ltst_h", "ls_deg")):
        raise StationDataError("Map either time_utc (with --lon-east) or all of sol, ltst_h and ls_deg")
    if use_utc and lon_east is None:
        raise StationDataError("time_utc mapping needs the station east longitude")
    rows, rejected = [], {name: 0 for name in VARIABLES}
    for raw in reader:
        row = {}
        if use_utc:
            try:
                when = parse_utc(raw[mapping["time_utc"]])
            except (ValueError, TypeError):
                continue
            t = mars_time(when, lon_east)
            row["sol"] = t["local_sol"]
            row["ltst_h"] = t["ltst_h"]
            row["ls_deg"] = t["ls_deg"]
        else:
            row["sol"] = _number(raw[mapping["sol"]])
            row["ltst_h"] = _number(raw[mapping["ltst_h"]])
            row["ls_deg"] = _number(raw[mapping["ls_deg"]])
            if not all(math.isfinite(row[k]) for k in ("sol", "ltst_h", "ls_deg")):
                continue
        for name, spec in VARIABLES.items():
            value = _number(raw[mapping[name]]) * scale.get(name, 1.0) if name in mapping else math.nan
            lo, hi = spec["valid"]
            if math.isfinite(value) and not lo <= value <= hi:
                rejected[name] += 1
                value = math.nan
            row[name] = value
        rows.append(row)
    return rows, {"file": Path(path).name, "rows": len(rows), "out_of_range_rejected": rejected}


def read_canonical(path: Path) -> list[dict]:
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in ("sol", "ltst_h", "ls_deg") if c not in (reader.fieldnames or [])]
        if missing:
            raise StationDataError(f"{path} is not a canonical station table (missing {missing})")
        return [{k: _number(r.get(k)) for k in CANONICAL} for r in reader]


def write_canonical(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CANONICAL)
        for r in sorted(rows, key=lambda r: (r["sol"], r["ltst_h"])):
            writer.writerow([int(r["sol"])] + ["" if not math.isfinite(r[k]) else f"{r[k]:.3f}" for k in CANONICAL[1:]])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def to_grid(rows: list[dict], bins: int = 24, meta: dict | None = None) -> Grid:
    """Average rows into (sol, local-time bin) cells. Ls per sol is the circular mean of its rows."""
    if not rows:
        raise StationDataError("No station rows")
    sols = np.array([int(r["sol"]) for r in rows])
    first, last = sols.min(), sols.max()
    n = int(last - first + 1)
    index = (sols - first) * bins + np.clip(np.floor(np.array([r["ltst_h"] for r in rows]) % 24 / 24 * bins), 0, bins - 1).astype(int)
    values = {}
    for name in VARIABLES:
        v = np.array([r[name] for r in rows], dtype=float)
        ok = np.isfinite(v)
        total = np.bincount(index[ok], v[ok], minlength=n * bins)
        count = np.bincount(index[ok], minlength=n * bins)
        with np.errstate(invalid="ignore", divide="ignore"):
            values[name] = np.where(count > 0, total / np.maximum(count, 1), np.nan).reshape(n, bins)
    angle = np.radians([r["ls_deg"] for r in rows])
    s = np.bincount(sols - first, np.sin(angle), minlength=n)
    c = np.bincount(sols - first, np.cos(angle), minlength=n)
    seen = np.bincount(sols - first, minlength=n) > 0
    ls = np.where(seen, (np.degrees(np.arctan2(s, c)) + 360) % 360, np.nan)
    # Fill Ls for empty sols by linear interpolation on the unwrapped series (Ls advances ~0.5 deg/sol)
    idx = np.nonzero(seen)[0]
    unwrapped = np.degrees(np.unwrap(np.radians(ls[idx])))
    ls = np.interp(np.arange(n), idx, unwrapped) % 360
    present = [name for name in VARIABLES if np.isfinite(values[name]).any()]
    return Grid(np.arange(first, last + 1), ls, bins, values, {**(meta or {}), "variables_present": present})
