# Marswalk routing algorithm

**Periapsis · Runtime · Senula · 14 November 2026, Colombo**

This is the routing algorithm as implemented in `runtime/marswalk`. Dimensions always come from the data. Every threshold marked *assumed* is a prototype value for review, not a sourced operational limit.

**Key:** 🟫 terrain · 🟦 human (Mode A) · 🟧 rover (Mode B) · 🟩 pathfinding · 🟨 environment and weather · 📐 dimension rule

There are two missions. In **Mode A** the crew walks. In **Mode B** the crew drives a rover; if the rover fails, they walk home.

## Phase 0 · Site, evidence and dimensions (`site.py`)

| Step | | Rule |
| --- | --- | --- |
| 0.1 | 🟫 | Load the sealed pack with `contracts.pack.check_pack`. |
| 0.2 | 📐 | Read dimensions from `site.json`: shape, affine `[a,b,c0,d,e,f0]`, cell Δx = a, Δy = −e, native spacing. Step lengths are Δx, Δy and √(Δx² + Δy²). |
| 0.3 | 🟫 | **Evidence gate.** Read the documentation engine's `local_elevation_20m` result. Not eligible → `NO_TERRAIN_EVIDENCE`. |
| 0.4 | 📐 | **Resolution gate.** Grid or native spacing > 20 m → `TERRAIN_TOO_COARSE`. **Size gate.** More than 1,000,000 cells → `GRID_TOO_LARGE` (the pipeline's `MAX_NATIVE_CELLS`). No analytical payload → `TERRAIN_NOT_AVAILABLE`. |
| 0.5 | 📐🟧 | **Obstacle visibility.** Report an assumed horizontal feature scale of 3 posts. Rock clearance remains unverified without obstacle footprint and vertical accuracy. |
| 0.6 | 🟦🟧 | Mission snapshot and mode. Human and rover profiles are fed as JSON (`profiles.py`). A human profile whose fastest speed exceeds the 1.16 m/s walk-to-run limit is rejected, not clamped. |

`plan_marswalk` runs 0.2–0.5 before routing and refuses with the first failing code.

## Phase 1 · Hazard map (once)

| Step | | Rule |
| --- | --- | --- |
| 1.1 | 🟫 | Valid mask and the pack's native-scale screening mask → blocked. |
| 1.2 | 🟫📐 | 3 × 3 kernel support (3Δx × 3Δy) → unknown where incomplete. |
| 1.3 | 🟫📐 | Horn slope with the real Δx, Δy; policy limit (15°, *assumed*) → blocked. |
| 1.4 | 🟫📐 | Local relief in a 3 × 3 window, used by the rover. |
| 1.5 | 🟫 | Freeze the read-only baseline. |

## Phase 2 · Price every step

| Step | | Rule |
| --- | --- | --- |
| 2.1 | 🟩📐 | 8 moves, no corner cutting, one-way edges, g = Δz / L. |
| 2.2 | 🟦 | Mode A: $v = v_\text{flat}\, e^{-3.5(\lvert g + 0.05\rvert - 0.05)}$, $t = L / v$. $v_\text{flat}$ comes from the profile (0.50 m/s default). An optional `max_slope_deg` refuses steeper edges and cells. |
| 2.3 | 🟧 | Mode B: incline, clearance, time and energy from the RoverProfile, with no regeneration. |
| 2.4 | 🟧🟦 | Mode B walkback pricing: human rules at **0.75 m/s** (Apollo planners' lunar traverse average for walkbacks over an hour, applied as a synthetic flat-speed input, *assumed*) with a **15°** limit on edges and cells. Unverified slopes are refused. |

## Phase 3 · Graph

| Step | | Rule |
| --- | --- | --- |
| 3.1 | 🟩 | Keep usable edges; build CSR and its transpose. |
| 3.2 | 🟩📐 | **Search horizon.** On grids of at least 250,000 cells (`search_horizon="auto"`), the outbound Dijkstra stops at B − R. A miss reports `outbound_search_limit`. The home field stays exact so the gate can tell "over reserve" from "no route". |
| 3.3 | 🟩🟨 | Closures from field reports and active rules apply to a copy. |

## Phase 4 · Environment and scenario weather (`weather.py`)

| Step | | Rule |
| --- | --- | --- |
| 4.1 | 🟨 | Sun, shadow and authorized scenario rules (existing). |
| 4.2 | 🟨 | Base-station messages are checked: known station, declared variable, matching unit, sane range, not in the future, age ≤ `max_age_s`. Rejected and stale messages are reported, never used. |
| 4.3 | 🟨 | Levels: forecast → **advisory** (never changes the plan); observed ≥ caution → **caution**; observed ≥ warning → **warning** (active); no fresh observation from any station → **link lost**. |
| 4.4 | 🟨🟦🟧 | Active effects: wind or SEP alert → **return now** (science fails the weather rule; direct return stays allowed). Dust → rover solar credited as zero. Link lost with `required: true` → science **unknown**. |

Default limits (*assumed*, for Isath): wind caution 15 / warning 20 m/s; dust optical depth 1.0 / 2.0; SEP alert flag 1.

## Phase 5 · Dijkstra

| Step | | Rule |
| --- | --- | --- |
| 5.1 | 🟩 | Crew → everywhere (forward) and shelter → everywhere (transposed). |
| 5.2 | 🟩🟧 | Mode B: a third run from the shelter on the transposed walking graph gives `T_walk_home`. |
| 5.3 | 🟩 | Parent pointers rebuild routes. No route → `out_of_bounds`, `endpoint_excluded`, `insufficient_terrain_evidence` or `no_path_under_constraints`. |

## Phase 6 · Plan and choose

| Step | | Rule |
| --- | --- | --- |
| 6.1 | 🟦🟩 | Direct-return gate first. |
| 6.2 | 🟦🟧 | Candidates, time ledger, rover energy ledger and energy alternatives (existing). |
| 6.3 | 🟧 | **Walkback.** For every cell x on a rover route, at elapsed time t(x) including dwell: t(x) + T_walk_home[x] ≤ B − R. A failing direct return gives `RETURN_WALKBACK_EXCEEDED`. |
| 6.4 | 🟦🟧🟨 | Hard checks now include `weather` and `walkback`, then Pareto, then priority → margin → id. |

## Phase 7 · Replan

| Step | | Rule |
| --- | --- | --- |
| 7.1 | 🟦🟧🟩 | A closure, new position, less time or weather warning → redo 3.3 → 5 → 6 on the same baseline. |
| 7.2 | 🟧→🟦 | **Rover failure** (`breakdown_snapshot`): switch to Mode A at the failure cell, subtract the elapsed time, advance the scenario clock, retain completed tasks, drop pending science and power, and walk at the walkback pace and limit. |

## Data on main

`python -m runtime.marswalk sites` runs Phase 0 on every terrain-like dataset in the repository.

| Dataset | Dimensions (from the data) | Phase 0 |
| --- | --- | --- |
| Synthetic fixture | 3 × 5 at 10 m | routable |
| Synthetic demo | 160 × 160 at 5 m (0.8 km) | routable; rock clearance unverified |
| Arcadia Planitia MOLA | 11 × 11 at 9.7 × 14.8 km | `NO_TERRAIN_EVIDENCE`; also too coarse |
| Jezero CTX control | 1,024 × 1,024 at 20 m (20.5 km) | evidence passes; `GRID_TOO_LARGE`; preview-only under contract v1 |
| HEALPix documentation cells | 196,608 at about 27.1 km | `TERRAIN_TOO_COARSE`; used to choose where to go |

With the pinned Jezero window (`--jezero-window` or `RW_JEZERO_WINDOW`), `sites` also reports slope and relief statistics for a 2 × 2 km crop. Routing there needs a contract v2 decision.

## What is still simulated or assumed

| Input | Why there is no real value | What the code uses |
| --- | --- | --- |
| Routable terrain | Contract v1 routes only synthetic packs; the Jezero window is outside the repository | Synthetic fixture and demo, labelled |
| Crew and shelter positions, closures | Real packs carry no scenario | Simulated scenario |
| Remaining time B, reserve R | Crew input; reserve unsourced | Crew input; 15 min *assumed* |
| Task cells, dwell, priority | Science layers say what is interesting, not the exact 20 m cell | Simulated stations |
| Rover profile | No real crew rover | `profile-rover-hypothetical.json` |
| Human pace and slope limit | No Mars suit data | 0.50 m/s, 15°, *assumed* |
| Walkback pace | Apollo planning figure | 0.75 m/s, *assumed* |
| Weather feed | No live Mars weather | Simulated feeds, plus one MEDA sol 36 historical replay |

Never simulated: DTM heights, MOLA context, HEALPix science layers, documentation engine verdicts, sun geometry and the MEDA record.

## Run

```sh
python -m runtime.marswalk sites
python -m runtime.marswalk demo
python -m runtime.marswalk demo --platform rover --rover-fails-at-min 12
python -m runtime.marswalk demo --weather runtime/examples/weather-wind-warning.json
python -m runtime.marswalk demo --platform rover --profile runtime/examples/profile-rover-hypothetical.json
```

## Scientific basis for the prototype

NASA's [Apollo Lunar Surface Journal](https://nasa.gov/wp-content/uploads/static/history/alsj/a11/a11.gaits.html) gives 2.7 km/h as the lunar planning average for walkbacks longer than an hour. Marswalk uses the equivalent 0.75 m/s as the flat-speed parameter of a directional pace model. The 15° edge and cell limit is scenario policy. The route check evaluates discrete cells under declared conditions.

The [USGS Jezero DTM quality study](https://pubs.usgs.gov/publication/70212659) distinguishes post spacing from effective horizontal resolution. The 20 m ceiling screens data eligibility. Terrain mechanics and obstacle detection need independently supported measurements.

NASA documents the effect of [Mars dust on solar generation and atmospheric density on wind loads](https://www.nasa.gov/wp-content/uploads/2024/01/mars-surface-power-generation-challenges-and-considerations.pdf). Setting solar credit to zero at a chosen threshold is a scenario rule. The wind limits and the supplied SEP flag exercise return logic. Crew risk depends on atmospheric conditions, equipment, terrain and exposure, including [radiation spectrum and shielding](https://www.nasa.gov/science-research/heliophysics/real-martians-how-to-protect-astronauts-from-space-radiation-on-mars/). The MEDA replay demonstrates how a historical sample enters a simulated feed.
