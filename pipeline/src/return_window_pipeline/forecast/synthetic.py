"""SYNTHETIC example station (for tests, demos of the pipeline and UI wiring only; never for skill claims).

The generator gives a mid-latitude northern site plausible structure so the code paths are exercised:
a seasonal CO2 pressure cycle, diurnal tides, multi-sol travelling pressure waves, a diurnal temperature
cycle damped by dust, an afternoon wind peak that strengthens with pressure tendency, and occasional dust
events. Amplitudes are illustrative round numbers, not fitted to any mission record.
"""
from __future__ import annotations

import math

import numpy as np

SOLS_PER_YEAR = 668.6


def synthetic_rows(n_sols: int = 1050, *, seed: int = 20261115, start_ls: float = 150.0, bins: int = 24,
                   missing_fraction: float = 0.03) -> list[dict]:
    rng = np.random.default_rng(seed)
    hours = n_sols * bins
    wave = np.zeros(hours)        # travelling pressure wave, period ~3 sols (baroclinic-like)
    temp_anom = np.zeros(hours)
    tau = np.zeros(n_sols)
    tau[0] = 0.5
    for d in range(1, n_sols):
        storm = 0.6 if rng.random() < 0.03 else 0.0
        tau[d] = 0.5 + 0.85 * (tau[d - 1] - 0.5) + storm + 0.03 * rng.normal()
    phase = 0.0
    for k in range(1, hours):
        phase += 2 * math.pi / (3.1 * bins) * (1 + 0.1 * math.sin(k / 400))
        wave[k] = 9.0 * math.sin(phase) + 0.8 * rng.normal()
        temp_anom[k] = 0.92 * temp_anom[k - 1] + 0.9 * rng.normal()
    rows = []
    for k in range(hours):
        sol, b = divmod(k, bins)
        ltst = (b + 0.5) * 24 / bins
        ls = (start_ls + sol * 360 / SOLS_PER_YEAR) % 360
        lsr = math.radians(ls)
        t_day = 2 * math.pi * ltst / 24
        dust = tau[sol]
        pressure = (720 + 55 * math.sin(lsr - 1.2) + 8 * math.cos(t_day - 2.6) + 4 * math.cos(2 * t_day - 0.4)
                    + wave[k] + 0.5 * rng.normal())
        amp = 32 / (1 + 0.6 * dust)
        temp = 205 - 8 * math.cos(lsr) + amp * math.cos(t_day - 2 * math.pi * 14.5 / 24) + temp_anom[k] + 0.4 * rng.normal()
        tendency = wave[k] - wave[k - 1] if k else 0.0
        wind = max(0.0, 4.5 + 3.5 * max(0.0, math.sin(t_day - 1.6)) + 1.4 * abs(tendency) + 0.4 * abs(wave[k]) / 3
                   + 0.8 * rng.normal())
        row = {"sol": sol + 1, "ltst_h": ltst, "ls_deg": ls, "pressure_pa": pressure, "air_temp_k": temp,
               "wind_ms": wind, "dust_tau": dust + 0.02 * rng.normal() if 9 <= ltst <= 16 else math.nan}
        for name in ("pressure_pa", "air_temp_k", "wind_ms"):
            if rng.random() < missing_fraction:
                row[name] = math.nan
        rows.append(row)
    return rows
