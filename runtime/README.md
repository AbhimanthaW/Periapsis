# Navigation and local pack runtime

## Integrated routing drill

`runtime.final_routing` evaluates the following six components against one revision of the synthetic
Marswalk site. Dijkstra searches the directed terrain graph after spatial closures are applied.

| Component | What goes into the planner |
| --- | --- |
| Station forecast | Learned pressure, temperature, wind and dust at 1, 3 and 6 Mars hours, from timestamped station observations. Published at one station, with model or fallback status. Learned wind/dust threshold advisories within the current planning window are flagged for review. |
| Objective classification | The existing lexicon plus a supervised Naive Bayes classifier fitted to [12 labelled simulation examples](examples/objective-training-simulated.json). A learned suggestion can nominate an existing task from previously unmatched text. The operator confirms its ID. Novel and low-scoring text can abstain. Scores are uncalibrated. |
| Trade-offs | The existing deterministic acceptance envelope plus a Bayesian oxygen burn-rate update from one fresh qualified telemetry window per astronaut. The upper estimate can increase the oxygen multiplier used in resource checks. A missing reading retains any multiplier already applied. Priors and observation noise are illustrative. |
| Human cost | The personalized pace and slope limits constrain routing. Route phases price the consumables. Reported current stores supply balances, and initial stores define the reserve floors. |
| Rover cost | Directed travel time, gross electrical energy, battery state and supply through the route and dwell. The crewed rover also requires a walkback at every breakdown point under the human pace, slope and consumables limits. |
| Spatial hazard mapping | The team's `LiveFeed` validates storm positions and raster alignment and publishes the current map. During planning an observed storm's moving footprint is swept over the remaining window and rasterized conservatively, including the cell half-diagonal. Observed radiation and stale spatial inputs stop science. |

The objective classifier and Bayesian update were added for this drill. The published team
objective and trade-off implementations were deterministic. This comparison tests software
integration with labelled simulation inputs and assumed rates. Site qualification,
held-out objective accuracy and burn-rate calibration remain open.

From the repo root, prepare the synthetic station artifact in PowerShell and start the local API.

```powershell
$env:PYTHONPATH = 'pipeline/src'
$routingDemo = Join-Path ([System.IO.Path]::GetTempPath()) 'periapsis-routing-demo'
New-Item -ItemType Directory -Path $routingDemo -Force | Out-Null
uv run --project documentation --locked python -m return_window_pipeline.forecast synth --sols 1050 --out "$routingDemo/station.csv"
uv run --project documentation --locked python -m return_window_pipeline.forecast train "$routingDemo/station.csv" --station pipeline/examples/weather/synthetic-station.json --artifact "$routingDemo/model.json" --report "$routingDemo/report.md"
uv run --project documentation --locked python -m runtime.planning_api --final-routing-model "$routingDemo/model.json"
```

In another PowerShell terminal, initialize the map and compare the return routes before and after a closure.

### Automatic mission feed

With the planning API running, start the feeder from the repo root. It handles the request IDs,
site identity and revision checks. The bundled [simulation log](examples/routing-feed-simulated.jsonl)
sends weather history and a science objective, introduces a moving storm with suit and rover telemetry,
lets the readings expire, and then sends a new position and a clear report.

```powershell
uv run --project documentation --locked python -m runtime.routing_feed
```

Replay runs as fast as responses arrive by default. With `--rate 60`, 60 seconds of simulated
time pass in one second of playback. Each line of output summarizes the published revision and
the new return routes. Read the full plan from `GET /api/v1/routing/plan`.

For an ongoing producer, use `--follow` and have the producer append one complete UTF-8 JSON
object followed by a newline per report. Use one writer and retain the append-only file.
Each report includes `time_utc` and `current_cell`. Include `objective`, `confirmed_task_ids`
and `completed_task_ids` to carry the current mission state. The same optional weather, hazard,
suit, rover and telemetry fields as the plan endpoint are supported. The feeder binds the reports
to the site's pack and processes them in nondecreasing source time.

```powershell
New-Item -ItemType File -Path incoming-mission.jsonl
uv run --project documentation --locked python -m runtime.routing_feed incoming-mission.jsonl --follow
```

While the log is idle, the feeder sends a clock-only request at a reported weather expiry using
the last known position and task state. A restarted feeder can resume against the same running
API by matching the previously accepted log prefix. Starting a new scenario requires a fresh
API session. The included producer is a simulation replay. A simulator or telemetry service can
use the same log format to supply its own reports.

### Manual API requests

With a fresh API session, the equivalent manual update is:

```powershell
$routingApi = 'http://127.0.0.1:8000/api/v1/routing'
$site = Invoke-RestMethod "$routingApi/site"
$body = @{
    schema_version = 1
    request_id = 'initial'
    pack_id = $site.pack_id
    pack_version = $site.pack_version
    expected_revision = 0
    time_utc = $site.start_time_utc
    current_cell = $site.current_cell
    objective = 'stratigraphy'
    confirmed_task_ids = @('transect')
    weather_readings = @(
        @{ variable = 'wind_speed'; value = 8; unit = 'm/s'; time_utc = $site.start_time_utc }
        @{ variable = 'dust_optical_depth'; value = 0.72; unit = '1'; time_utc = $site.start_time_utc }
    )
}
$open = Invoke-RestMethod "$routingApi/plan" -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 10)
$body.request_id = 'ramp-closure'
$body.expected_revision = $open.revision
$body.time_utc = '2021-02-18T20:48:19Z'
$body.weather_readings = @(@{ variable = 'dust_optical_depth'; value = 2.4; unit = '1'; time_utc = $body.time_utc })
$body.hazard_events = @(@{
    hazard_id = 'north-ramp'
    revision = 1
    action = 'close'
    observed_utc = $body.time_utc
    cells = $site.demo_footprints.'north-ramp'
})
$closed = Invoke-RestMethod "$routingApi/plan" -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 10)
$open.human.direct_return | Select-Object length_m, seconds
$closed.human.direct_return | Select-Object length_m, seconds
```

`GET /api/v1/routing/site` provides the elevation grid, affine, permanent exclusions, unsupported cells,
and the synthetic task catalogue. `POST /api/v1/routing/plan` consumes the current position, objective,
confirmed and completed tasks, weather observations and hazard events at a given simulation time.
It returns both platforms' candidates, ordered route cells, travel time, distance, elapsed sols and
ledgers. `shortest_distance_return` is the geometric reference on the same admissible terrain graph.
It has its own distance-based search and requires separate resource checks before use.

The API returns 409 for a superseded mission or hazard revision. An exact retry of the latest accepted
request returns the same result. `GET /api/v1/routing/plan` reads the latest committed plan and revision.
Restarting the API resets the drill. To advance the clock, send a new plan request, including at
`weather_recheck_utc` when a reading expires. A closed footprint stays in force until a newer
`clear` event for the same manual hazard. `live_hazards` also accepts the team's
[spatial format](docs/live-hazard-map.md) with incremental `storms`, `layers` and `alerts` within
one `feed_id`. Send only observations issued by the current report time. Storm centre and radius
are in local metres, velocity in m/s, wind in m/s and optical depth dimensionless. Rasters use the
site's exact shape and affine. Spatial observations and forecasts are tracked separately.
`spatial_hazards.blocked_now` is the current display mask. `blocked_for_plan` contains the larger
swept mask used by both planners and their walkback routes. This window-wide mask can exclude an
otherwise usable crossing during a brief clear interval. Caution exposure is reported in metres.
Pressure history in adjacent Mars-hour bins exercises learned inference, as shown in
`runtime/tests/test_final_routing.py`.

`crew_stores` can report the remaining `oxygen` [g], `cooling_water` [kg], `drinking_water` [L]
and `battery` [Wh] per walking astronaut. `rover_charge_wh` updates the rover battery within its
configured reserve and capacity. Omitted readings reuse the previous simulated balances.
Supplying the envelope's simulated `telemetry`, `decision_window_s` and `one_way_light_time_s`
lets the planner surface AMBER options. Recommendations require a GREEN walking option with a GREEN
direct return, or a rover option that passes its energy and walkback checks. Operator acceptance
and control of the crew or rover are outside the drill API. During the rover leg, the model
uses the flat walking burn rate as a proxy for seated travel and science dwell. From every
breakdown point it uses the directed walking leg's duration and ascent.

```powershell
uv run --project documentation --locked python -m pytest -q runtime/tests/test_final_routing.py
```

The integration uses a local, in-memory planning session and simulated inputs. The log persists
input reports on disk and can rebuild the session by replay. Dashboard wiring, physical telemetry
adapters and qualification for source-backed terrain remain separate work.

`python_engine/` and its six original tests are byte-preserved from the delivered Senula routing source. Its A* uses dimensionless synthetic cell costs, eight neighbours and diagonal corner checks. It does not use elevation differences or directed travel seconds. Its plotting demo requires Matplotlib in a separate environment. The original server file is empty.

`mission.py` is a separate bounded consumer for pack v1. It uses the shared structural and semantic checks, including the external site hash when supplied. It loads source-backed Jezero as an elevation preview and runs the audited closure and reserve calculations in explicitly enabled fixture simulation. The fixture's four-neighbour edge model uses a fixed base of one second per metre plus two seconds per metre of ascent. These are software control values. This runtime keeps the legacy algorithm intact and leaves physical mobility and tactical routing unsupported.

From the repository root run:

```sh
uv run --project documentation --locked python -m pytest runtime/tests contracts/tests -q
uv run --project documentation --locked python -m runtime.mission inspect /path/to/preview-pack
uv run --project documentation --locked python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid
```

Add `--site-sha256` with an independently recorded digest when validating a released pack. Exit 2 reports a refused pack or request as structured JSON on stderr. A valid simulation that cannot return reports its decision state in JSON on stdout.

## Local planning HTTP foundation

From the repository root, provision the locked environment once with
`uv sync --project documentation --locked --python 3.12`, then start:

```sh
uv run --project documentation --locked --offline python -m runtime.planning_api
```

The service listens on `127.0.0.1:8000`. It validates the committed simulation
pack and resolves an evidence query at startup when explicitly configured. It requires no web
build or downloaded raster. The system architecture's loader, request
validation, response serialization and freshness boundaries apply here. Its
richer mission option fields describe future solver and UI integration.

| Endpoint | Contract |
| --- | --- |
| `GET /healthz` | HTTP 200 with `{"status":"ready"}` after startup validation. |
| `GET /api/v1/site` | Synthetic pack and scenario IDs, fixed inputs, initial remaining time, predefined closure cells, checkpoint and shelter cells, and grid shape and affine. |
| `POST /api/v1/plan` | Accepts a strict v1 JSON request. Returns the existing simulation output plus request ID, schema version and route index order. With `--engine marswalk`, the same fields come from the Marswalk planner, plus `engine` and the full `marswalk` plan. |
| `GET /api/v1/evidence` | Separate result from the documentation resolver, with reported provenance and supported fallbacks. The API returns `classification: provenance_unverified` because it does not independently verify the package's provenance. Returns HTTP 503 with `EVIDENCE_NOT_CONFIGURED` until a package and query are configured. |

### Marswalk engine behind the plan endpoint

`runtime.mission.simulate` stays the default planner. To serve the same endpoint from
`runtime.marswalk`, start the service with:

```sh
uv run --project documentation --locked --offline python -m runtime.planning_api --engine marswalk
```

The fixture uses the Marswalk control profile: 4-neighbour moves at 1 s/m plus 2 s per metre
climbed. That is the fixture's own cost rule, so every v1 field the mission view reads is
unchanged. `test_marswalk_engine_matches_mission_contract` covers all fixture closure
combinations, both orders for two closures, and representative remaining times, including
the return and science feasibility thresholds. Equal-time routes may use different cells.
The response adds `engine: "marswalk"` and `marswalk`, the full
`marswalk-plan-v1` object: candidates, ledgers, Pareto front, terrain counts, assumptions
and solver statistics. The mission view's schema ignores both fields until the UI reads them.
This engine choice does not change the pack contract. Routing remains synthetic only.

```sh
curl -sS http://127.0.0.1:8000/api/v1/site
curl -sS http://127.0.0.1:8000/api/v1/plan -H 'Content-Type: application/json' -d '{
  "schema_version": 1,
  "request_id": "closure-1",
  "pack_id": "rw-synthetic",
  "pack_version": "1.0.0",
  "scenario_id": "synthetic-closure-v1",
  "checkpoint_id": "crew",
  "shelter_id": "home",
  "closure_ids": ["mid"],
  "completed_task_ids": ["survey-done"],
  "remaining_s": 100,
  "reserve_s": 15
}'
curl -sS http://127.0.0.1:8000/api/v1/evidence
```

Only remaining time and predefined closures vary in the fixture. Time fields
are integer seconds. Pack version, checkpoint, shelter, completed tasks and
reserve must match site metadata. The result carries ordered `[row, col]` cell
pairs in `direct_return.cells` and the reverse-direction control. The affine
maps the center of cell `[r,c]` from `[c+0.5,r+0.5]` to local metres. Keep
fixture geometry off real Mars geography.

A valid scenario produces HTTP 200, including `NO_RETURN_ROUTE` and
`RETURN_OVER_RESERVE`. Both have a null recommendation. An over-reserve result
may still contain a computed return path for inspection. Malformed input or
unknown closures return 400. A mismatch with fixed scenario state returns
409. Errors use `{schema_version,request_id,error,message}`, with a null
request ID when unavailable. The eventual client must discard superseded
request IDs, clear stale recommendations and key session state by pack version.

### Integration handoffs

- **Senula:** Use the four HTTP replay outcomes in
  [test_planning_api.py](tests/test_planning_api.py) as regression controls.
  Keep the routing computation behind the adapter. Review any changes to
  route geometry, units, feasibility or refusal semantics before wiring a
  new solver. The fixture's travel times are test values.
- **Yumeth:** For a real site, hand over a schema-valid evidence package,
  capability query, source manifest, local display assets and checksums.
  Start with `--evidence-package PATH --evidence-query PATH` to test the
  approved pair through the same resolver. The response identifies this as
  operator-configured evidence. The primary demo targets a less-documented
  site and remains unqualified. Jezero is used as an explicit test control.
  Site qualification remains a scientific review. Changes to routing pack capabilities require producer/consumer
  review under [mission pack v1](../contracts/README.md).
- **Isath:** Use `site`, `plan` and `evidence` responses as inputs to the UI
  design. The service is ready for local contract checks. Same-origin web
  wiring, rendering, browser replay and second-machine offline rehearsal
  remain release work.

Run the headless acceptance checks with
`uv run --project documentation --locked --offline python -m pytest runtime/tests/test_planning_api.py -q`.

## Human Marswalk pipeline (`runtime/marswalk/`)

A deterministic implementation of the **Human Marswalk** architecture view:
Mission configuration (01) → Human traversal time (04) + Traversability (03)
→ Terrain routing (09) → Resource budgets (07) → Mission optimization (10).
It is a separate module. `mission.py`, `planning_api.py` and their regression
outputs are unchanged, and the planning API is not wired to it yet. That
integration needs the route-geometry, units and refusal review described in
the Senula handoff above.

| Module | Architecture boxes |
| --- | --- |
| `config.py` | Mission snapshot, Human operating profile, Authorized operating limits |
| `mobility.py` | Human traversal time: asymmetric, illustrative pace (`tobler_scaled`), plus the fixture `control_linear` model |
| `traversability.py` | Terrain scale and support, Coverage and support masks, Scale-aware roughness (P1), Characterize surface evidence (P1), Slope screening, Obstacles and exclusions, Baseline routing inputs |
| `routing.py` | Shared mobility contract, Directed terrain graph (CSR, 4/8 neighbours, no corner cutting), two directed Dijkstra runs, Route reconstruction, Diverse candidate routes |
| `resources.py` | Compute return-time margin (B − R − travel), Route resource ledger with prefix checks |
| `optimization.py` | Compose candidate plans, Reevaluate science tasks, Enforce hard constraints, Compare Pareto alternatives, Select next action, Bounded multi-stop planning (P1), Excluded from core |
| `plan.py` | Orchestration and the `marswalk-plan-v1` JSON output |

Dijkstra runs in SciPy when it is importable and otherwise uses an equivalent
pure-Python implementation over the same CSR arrays. The locked environment
has no SciPy, so CI exercises the fallback. Both produce identical times.
With exact ties they may choose different but equally fast cells. Each plan
reports the backend it used. A 1.6 km × 1.6 km grid at 5 m runs a full plan
in about 0.1 s with SciPy and 0.3 s without it.

```sh
# synthetic scenario, no pack needed: decision table before and after a closure
uv run --project documentation --locked --offline python -m runtime.marswalk demo
# add --png marswalk-demo.png from an environment that has Matplotlib (it is not in the lock)
# the pack v1 fixture with the human profile (8 neighbours, illustrative pace). At this
# 10 m toy scale it reports RETURN_OVER_RESERVE after the closure; that is expected
uv run --project documentation --locked --offline python -m runtime.marswalk plan contracts/fixtures/synthetic-v1 --closure mid
# reproduce runtime.mission's control model exactly (4 neighbours, 1 s/m + 2 s per m ascent)
uv run --project documentation --locked --offline python -m runtime.marswalk plan contracts/fixtures/synthetic-v1 --closure mid --pace-model control_linear --neighbours 4
# tests, including a cross-check against runtime.mission.simulate for every closure set
uv run --project documentation --locked --offline python -m pytest runtime/tests/test_marswalk.py -q
```

Options: `--pace-scenario slow` (speed × 0.7), `--crew-status issue`
(no science; return now), `--multistop` (ordered two-task plans),
`--alternatives K` (diverse outbound routes for the recommendation),
`--slope-limit-deg` (runtime slope policy on top of the pack screen) and
`--backend scipy|python`.

Outcome codes: `OK`, `NO_RETURN_ROUTE`, `RETURN_OVER_RESERVE` and
`INSUFFICIENT_TERRAIN_EVIDENCE`. A direct return that violates a hard limit yields
`NO_RETURN_ROUTE` when it otherwise fits the time budget. The candidate retains
the evaluated leg and the failed rule for inspection. Insufficient terrain
evidence means only unverified terrain could connect the crew to the shelter,
so no route is drawn. Each leg reports `ok`,
`no_path_under_constraints`, `insufficient_terrain_evidence`,
`endpoint_excluded` or `out_of_bounds`. Each constraint reports
`pass`/`fail`/`unknown`, and an unknown required value blocks the plan.
Science requires a passing direct return. Each published outbound alternative
passes the mission constraints with the same remaining legs and dwell phases.
For in-memory terrain, provide `TerrainSupport.pack_version` matching the
snapshot. Checked packs supply it automatically. The supported authorized
limit is mission-wide `max_leg_s`, expressed in seconds (`s`).

Limits: pace parameters and thresholds are illustrative assumptions, not
calibrated Mars-suit data or proof of safety. Only time is budgeted. The
return check assumes no rescue. Closures are simulated field reports. The
following are deliberately excluded: AI/ML decisions, live telemetry, suit
forecasts, safety scores, medical suitability or crew ranking, and assumed
vehicle rescue.

### Rover mobility (05) and environmental models (06)

| Module | Architecture boxes |
| --- | --- |
| `config.py` | Rover operating profile (`RoverProfile`): hypothetical or cited vehicle record. Refuses a sourced record without a citation, efficiency outside (0, 1], reserve > charge > capacity and non-finite values |
| `rover.py` | Rover traversal time (incline, local tilt and clearance checked first; unsupported terrain fails closed), Rover drive energy (uphill work + rolling resistance + drivetrain losses + auxiliary load, no regeneration credit, stationary science load), Traction/slip/sinkage reported `not_calibrated` |
| `environment.py` | Historical weather & RAD (`Observation`, context only), Solar geometry & shadow (Mars24 sun position and terrain ray-march: `lit`/`shadow`/`unresolved`/`night`), Power availability scenario (`declared_curve`, `solar_derived`, `non_solar`, `none`), Environmental activation, Comms and forecast research reported `not_modelled` |
| `resources.py` | Battery energy ledger: checks discharge power and reserve on each drive edge and each dwell. Applies consumption before charging and caps charge at capacity. |

An explicit operating scenario needs a declared purpose, authorization,
matching scenario ID and, if time-limited, coverage for the full planning
window. An active `return_now` prevents science and allows the shelter
return. An active `block_cells` behaves like a closure. Historical records
are context only, and predictions stay unverified until a qualified
prediction product is integrated. A required operating input that is
unverified leaves science `unknown` (`unverified_environment`). A required
unverified closure also prevents a return recommendation
(`RETURN_ENVIRONMENT_UNVERIFIED`).

Rover plans require a declared `PowerScenario` and battery charge and
discharge ratings. A power curve must identify its source and cover the
evaluated timeline. Battery-only operation uses `PowerScenario("none")`.
If the fastest feasible-by-time legs fail energy, the planner checks a
bounded set of alternatives built from minimum-energy, power-admissible
and mixed time/energy routes. `RETURN_ENERGY_SEARCH_EXHAUSTED` preserves the
evaluated geometric return and identifies the bounded search result.
`RETURN_ENERGY_UNVERIFIED` indicates missing energy inputs.

The sun position uses Mars24 (Allison & McEwen 2000) with TT − UTC pinned at
69.184 s, which is valid from 2017. It reproduces the start of Mars Year 36
(Ls 0 on 7 Feb 2021), Perseverance's touchdown at about 15:53 LMST, the
±25.4° declination range and the 1.381–1.666 AU distance range. It stands in
for pinned SPICE kernels. Packs carry no site coordinates, so a plan must
declare `time_utc`, `site_lat_deg` and `site_lon_east_deg` for solar geometry.
Solar generation is credited only during stationary dwell with resolved
illumination, based on samples no more than 60 seconds apart. It needs a
separately declared upper bound on intervening terrain, including terrain
outside the grid, in the same vertical datum. Unresolved visibility,
shadow, night and driving receive zero solar credit. These are synthetic
planning assumptions.

```sh
# Choose a new output directory for the rover fixture.
uv run --project documentation --locked --offline python -m contracts.fixtures.generate /tmp/marswalk-rover-pack --rover
uv run --project documentation --locked --offline python -m runtime.marswalk plan /tmp/marswalk-rover-pack --platform rover --power battery-only --closure mid

uv run --project documentation --locked --offline python -m runtime.marswalk demo --platform rover
uv run --project documentation --locked --offline python -m runtime.marswalk demo --sep-alert
uv run --project documentation --locked --offline python -m pytest runtime/tests/test_marswalk_rover_env.py -q
```

The pack CLI also accepts `--power demo-solar` with `--time-utc`,
`--site-lat-deg` and `--site-lon-east-deg`. Provide
`--horizon-upper-bound-m` only when that bound is declared for the scenario.

The demo rover is a hypothetical record (`hypothetical_crew_rover`). It is
not a NASA vehicle specification. The demo solar array, dust transmittance
and the simulated solar-particle-event drill are declared assumptions, and
no radiation dose is inferred.

Demo output (synthetic terrain, before and after the simulated north-ramp
closure). Regenerate with `python -m runtime.marswalk demo [--platform rover] --png PATH`
from an environment that has Matplotlib:

![Human Marswalk demo](docs/marswalk-demo-human.png)
![Rover Marswalk demo](docs/marswalk-demo-rover.png)

### Site gates, profiles as data, rover walkback and weather

The full algorithm, with dimensions and the remaining simulated inputs, is in
[docs/marswalk-algorithm.md](docs/marswalk-algorithm.md).

| Module | What it adds |
| --- | --- |
| `site.py` | Phase 0. Reads grid dimensions from the data and refuses before routing: no eligible local DTM (`NO_TERRAIN_EVIDENCE`), grid or native spacing above 20 m (`TERRAIN_TOO_COARSE`), more than 1,000,000 cells (`GRID_TOO_LARGE`) or no analytical payload (`TERRAIN_NOT_AVAILABLE`). It reports rock clearance as unverified and includes an assumed horizontal feature scale. It includes loaders for the Arcadia MOLA handoff, the Jezero CTX control and the HEALPix cells on main. |
| `profiles.py` | Human and rover profiles from JSON, with strict field names and optional kWh battery fields. Example files are in `runtime/examples/`. `HumanProfile` gains `v_flat_mps` (rejected above the 1.16 m/s walk-to-run limit) and an optional `max_slope_deg`. |
| `walkback.py` | Mode B. A third Dijkstra from the shelter on the walking graph (0.75 m/s, 15°). Every rover route cell must satisfy elapsed + walk home ≤ B − R. `breakdown_snapshot` replans on foot after a rover failure. A failing direct return gives `RETURN_WALKBACK_EXCEEDED`. |
| `weather.py` | Base-station messages are validated and classified as advisory (forecast), caution, warning (active) or link lost. Active wind and SEP alerts force a return. Dust removes rover solar credit. A required feed that loses its link leaves science unknown. |

On grids of at least 250,000 cells the outbound search stops at B − R. The
home search stays exact. With `--engine marswalk`, `POST /api/v1/plan` accepts an
optional `profile` object and an optional `weather` feed, which needs `now_utc` as the plan time.
The feed uses the same shape as `runtime/examples/weather-*.json`. Results appear under
`marswalk.weather`. An active wind or SEP warning blocks science. The planner recommends `direct_return`
when the direct return passes its own checks. The `mission` engine refuses both fields (`PROFILE_UNSUPPORTED`, `WEATHER_UNSUPPORTED`).

```sh
uv run --project documentation --locked --offline python -m runtime.marswalk sites
uv run --project documentation --locked --offline python -m runtime.marswalk demo --platform rover --rover-fails-at-min 12
uv run --project documentation --locked --offline python -m runtime.marswalk demo --weather runtime/examples/weather-wind-warning.json
uv run --project documentation --locked --offline python -m runtime.marswalk demo --platform rover --profile runtime/examples/profile-rover-hypothetical.json
uv run --project documentation --locked --offline python -m pytest runtime/tests/test_marswalk_site_walkback_weather.py -q
```
