# Live hazard map (builds on #30)

This adds the parts the scripted replay in `runtime/hazards/replay.py` does not cover yet:

1. A **per-square live hazard map** on the same grid as the terrain baseline.
2. **Wind and dust on the map**, from moving storms or from full raster layers.
3. A **radiation (SEP) alert** that applies to the whole map.
4. **Moving storms with an arrival-time check**: each route square is checked at the time the crew reaches it, not just at the current time.
5. A **background monitor** that replans every tick from the crew's current position: continue → warn → reroute.
6. An **emergency mode** for when no safe route home exists: hold on the nearest square that stays clear.
7. **Live data input** as a JSON feed. All example feeds are **simulated**.

Nothing in `replay.py`, `forecast.py` or `tradeoff/` changes. The terrain baseline is never edited: live closures are applied to a copy.

## Files

| File | What it does |
|---|---|
| `runtime/hazards/live.py` | Feed format, validation, per-square `hazard_state`, `HazardTimeline` (blocked squares for each minute ahead) |
| `runtime/hazards/route.py` | `plan_live`: arrival-time checked plan, radiation return, emergency hold square |
| `runtime/hazards/monitor.py` | `Monitor`, `simulate`, and the CLI |
| `runtime/examples/live-hazards-*.json` | Four simulated feeds: dust devil, SEP, trapped, stale |
| `runtime/tests/test_live_hazards.py` | 25 tests |

## Grid and dimensions

- The live map uses the **exact grid of the terrain baseline**: same shape, same affine.
- A raster layer with a different shape or affine is refused with `HAZARD_GRID_MISMATCH`. It is never resampled silently.
- Storms are given in **map metres** (`centre_m`), or in squares (`centre_cell`), which is converted with `support.center_xy`.
- Demo map: 160 × 160 squares at 5 m. Jezero: 1024 × 1024 at 20 m. Both work because the code reads the grid from the baseline.

## Hazard rules (`LivePolicy` defaults; thresholds are placeholders for Isath to source)

| Input | Caution | Blocked |
|---|---|---|
| Wind | ≥ 15 m/s | ≥ 20 m/s |
| Dust optical depth τ | ≥ 1.0 | ≥ 2.0 |
| Radiation alert | — | whole map: return now, science off |
| Data older than 10 min | `link_lost`: the last footprint stays in force, science off | — |

- **Forecasts are advisory.** A storm with `kind: "forecast"` only gives caution. Radiation forecasts remain advisory as well. Expired forecasts are dropped, and observed rasters replace older rasters for the same variable.
- **Moving storms**: centre = observed centre + velocity × time. Extrapolation stops after 30 min, so it never runs away. The newest observation of each storm wins.
- **No looking into the future**: an observation is only used once its `observed_utc` has passed.

## Arrival-time check (how `plan_live` works)

1. Apply current closures to the graph. The current cell may be used to depart. The arrival check rejects a hazardous shelter.
2. Plan with the normal Marswalk planner (Dijkstra out + Dijkstra home, Tobler pace).
3. Walk the chosen route and get the arrival time at each square.
4. For each square, check whether a storm will be on it at that time, plus or minus a buffer of `max(60 s, 0.2 × arrival time)`. The buffer grows the further ahead we look, because predictions get less certain.
5. If there is a conflict, close the storm's footprint around that time and plan again (up to 8 times).
6. If it still conflicts, close everything that will be blocked in the next 2 hours (the safe fallback).
7. If there is no route at all: **EMERGENCY**. Find a timed path to a reachable square that stays clear. The rehearsal advances along that path before holding.

Results: `GO`, `RETURN_NOW` (radiation or stale data), or `EMERGENCY`.

## Monitor (background replanning)

Every tick (default 60 s), the monitor:

- moves the crew along the current route,
- replans from where they are now,
- decides what to do:

| Action | When |
|---|---|
| `continue` | current route is still safe |
| `caution` | route crosses caution squares |
| `suggest` | a route at least 5 min faster exists. It is only shown, not imposed (prevents flip-flopping) |
| `reroute` | current route is no longer safe. A **WARNING** is sent first, then the new route |
| `return_now` | radiation alert, or a route home has opened after an emergency |
| `emergency` | no safe route home: hold square given |
| `link_lost` | feed is stale |
| `arrived` | crew is at the shelter |

## How to run it

```bash
python -m runtime.hazards.monitor runtime/examples/live-hazards-dust-devil.json
python -m runtime.hazards.monitor runtime/examples/live-hazards-dust-devil.json --platform rover
python -m runtime.hazards.monitor runtime/examples/live-hazards-sep.json
python -m runtime.hazards.monitor runtime/examples/live-hazards-trapped.json
python -m runtime.hazards.monitor runtime/examples/live-hazards-stale.json
python -m pytest runtime/tests/test_live_hazards.py -q
```

Expected results on the demo map:

| Feed | Result |
|---|---|
| dust devil, walking | GO 14.4 min → minute 5 storm turns → WARNING + reroute (17.8 min) → arrived minute 23 |
| dust devil, rover | home by minute 5 |
| SEP | science walk → minute 4 return now → arrived minute 17 |
| stale | minute 11 link lost → arrived minute 26 |
| trapped | emergency hold → minute 30 route opens → return now → arrived minute 45 |

## Real data vs simulated data

| Data | Status |
|---|---|
| Terrain grid (demo 160 × 160 @ 5 m) | from the repo demo |
| Background wind 9.08 m/s, pressure 737.47 Pa, temperature 238.71 K | **real**: MEDA, Jezero, sol 36 (already in the repo) |
| Radiation background 0.21 ± 0.04 mGy/day | **real**: MSL RAD, Gale (already in the repo); context only |
| Storm tracks, SEP alert times, the trapped storm | **SIMULATED**: there is no live Mars storm feed in the repo |
| Wind and dust thresholds | **placeholders**: need sources |

## Open questions for review

- Threshold values (wind 15/20 m/s, τ 1/2): who sources them?
- Should `replay.py` be moved onto this feed format, or should both stay?
