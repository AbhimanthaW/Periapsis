"""Mars time from UTC (Allison & McEwen 2000 / Mars24), matching runtime/marswalk/environment.py.

Adds a TT-UTC table back to 1972 so archived records (InSight 2018+, MEDA 2021+, REMS 2012+)
can be placed on a continuous local true solar time axis. The table is accurate to the leap second;
an error of one second is irrelevant for hourly bins.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

# (UTC date from which it applies, TAI-UTC seconds)
_LEAP = ((1972, 1, 1, 10), (1972, 7, 1, 11), (1973, 1, 1, 12), (1974, 1, 1, 13), (1975, 1, 1, 14), (1976, 1, 1, 15),
         (1977, 1, 1, 16), (1978, 1, 1, 17), (1979, 1, 1, 18), (1980, 1, 1, 19), (1981, 7, 1, 20), (1982, 7, 1, 21),
         (1983, 7, 1, 22), (1985, 7, 1, 23), (1988, 1, 1, 24), (1990, 1, 1, 25), (1991, 1, 1, 26), (1992, 7, 1, 27),
         (1993, 7, 1, 28), (1994, 7, 1, 29), (1996, 1, 1, 30), (1997, 7, 1, 31), (1999, 1, 1, 32), (2006, 1, 1, 33),
         (2009, 1, 1, 34), (2012, 7, 1, 35), (2015, 7, 1, 36), (2017, 1, 1, 37))
_PBS = ((0.0071, 2.2353, 49.409), (0.0057, 2.7543, 168.173), (0.0039, 1.1177, 191.837),
        (0.0037, 15.7866, 21.736), (0.0021, 2.1354, 15.704), (0.0020, 2.4694, 95.528),
        (0.0018, 32.8493, 49.095))
SOL_S = 88775.244
MARS_HOUR_S = SOL_S / 24.0


def parse_utc(text: str) -> datetime:
    when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def tt_minus_utc(when: datetime) -> float:
    tai = 10
    for y, m, d, value in _LEAP:
        if (when.year, when.month, when.day) >= (y, m, d):
            tai = value
    return tai + 32.184


def mars_time(when: datetime, lon_east_deg: float) -> dict:
    """Ls, local true solar time and a continuous local true solar hour count (sol*24 + LTST)."""
    jd_tt = when.timestamp() / 86400.0 + 2440587.5 + tt_minus_utc(when) / 86400.0
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
    local_hours = msd * 24.0 + lon_east_deg / 15.0 + eot_deg / 15.0
    return {"ls_deg": ls, "ltst_h": local_hours % 24.0, "local_hours": local_hours, "local_sol": math.floor(local_hours / 24.0)}
