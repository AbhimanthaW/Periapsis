# Return Window

Return Window is a local React + TypeScript walkthrough of the 24 exploration, planning, analysis, and monitoring references. The app uses bundled optical basemaps and deterministic sample scenarios.

## Launch

Use Node 22 or later. In the repository's `web/mission-preview` directory, run:

```sh
npm ci
npm run dev -- --host 127.0.0.1 --port 4173
```

Open [Return Window](http://127.0.0.1:4173/). [The visual gallery](qa/gallery.md) links all 24 original PNGs, matching app states, fresh browser captures, side-by-side views, focused crops, and pixel diffs.

## Primary demo · Arcadia Planitia

Open [the Arcadia demo](http://127.0.0.1:4173/#demo/arcadia) or choose **Arcadia demo** from Explore. The walkthrough loads the pinned approximately 4 × 4 km evidence query, displays the regional MOLA context, and explains why local 20 m stereo elevation and routing are withheld. For the editable objective and method exclusions, use **Review methods** in Explore and load the Arcadia scenario. [Arcadia evidence and replay guide](../../docs/objective-methods/README.md)

## Synthetic mission rehearsals

- **Astronaut** — Choose Astronaut in Explore, submit an objective, select a region, and investigate. Inspect Data and Science, then choose a science task. Run the plan and use it to open Monitor. Open Contingency to report a closure. Compare the three outcomes and confirm the admissible option to create a mission revision.
- **Rover** — Open Route from a region or the mission navigation. Compare candidates, select a route, and use it to open Monitor. Dismiss the module library to see the playback controls. Report a change, review the obstruction or component scenario, recheck, and switch to the new route or hold position.
- **Review states** — Click the timing control beside the planning model status to see loading, unavailable, infeasible, and failed cases. Open Returns or Crew constraints in astronaut planning to inspect the limit violation. Open Analysis to inspect model runs, provenance, and revisions. The report supports selected-section JSON export, trace CSV, and the browser's PDF print dialog.
- **Layout** — Open Edit layout beside the mission navigation tools. Place or drag modules into the drop area, collapse or remove modules, switch presets, and save a custom preset during the session. At 768 px the planning menu provides access to the compact view's secondary controls.

Mission state and custom presets live in the current page session. Direct links in a fresh tab open the reference fixtures. The ranking starts with five sample rows, and the full-registry count is retained from the reference. This pass uses no backend. Jezero supplies the detailed local imagery control. Route paths, criteria, faults, and telemetry are scenario fixtures. The no-footage state is intentional.

## Reproduce verification

```sh
npm run build
npx playwright install chromium --only-shell
npm run test:ui
python3 qa/compare.py
```

The comparison step requires Pillow. Pass the reference directory as the first argument if it has moved. [See verification and remaining differences](design-qa.md).

## Map assets

The globe and Jezero terrain imagery came from the offline atlas assets in commit `ed9fe79`. The desktop, inset, and compact views use registered crops or projected samples, resampled and color graded for display. Map routes, markers, and labels are rendered separately and remain interactive.

- Viking MDIM 2.1 colorized mosaic, NASA Ames and USGS. [USGS catalog](https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m)
- MOLA color shaded relief, NASA MGS, the MOLA Science Team, and USGS. [USGS catalog](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_global_color_shaded_relief_463m)
- Jezero CTX mosaic, NASA, JPL-Caltech, MSSS, and USGS. [NASA Mars Trek catalog](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars)

## Hazard drill

Open **Hazard drill** in Explore or on Jezero's Route, Analysis, or Monitor page.
**Play drill** advances the six recorded simulation updates every 10 seconds.
**Next update** steps through them manually. Playback continues while you change
mission pages. Use **Analysis** for data provenance and **Monitor** to approve
a route or hold position. Rover and astronaut decisions are independent and last
for the current page session. **New drill** resets the simulation and decision log.

The bundled frames come from Marswalk and run without network access once the
local app is loaded. The map uses the Marswalk demo's synthetic 5 m terrain grid
in local metres. The drill stages a dust advisory, expands it into a corridor
exclusion, expires the station reading, and eventually reopens the corridor.
A stale reading suspends approvals and preserves the last closure. A caution
prompts a detour review if it removes at least 20 m of scripted footprint
exposure. The plotted paths keep their identities and a previously approved route
stays selected when the corridor reopens.

The rover comparison uses Marswalk energy, time reserve, and emergency walkback
checks. Walking EVA alternatives also use the deterministic Trade-off Envelope
and its simulated crew budgets. Dust exposure is distance inside the scripted
area. Its effects on pace, traction, health, and accident likelihood are
unquantified. Travel times and margins are drill estimates. The station
forecast uses the existing synthetic-trained weather model, reports its
empirical P10/P50/P90 bands and climatology fallback, and supplies point guidance
only. Jezero MEDA is an archived reference reading, independent of the drill and
forecast. Jezero pack qualification is tracked in Site Pack Readiness.

### Regenerate the offline bundle or run on-demand calculations

From the repository root, with the documentation environment installed:

```sh
PYTHONPATH=pipeline/src uv run --project documentation --locked python -m return_window_pipeline.forecast synth --out /tmp/return-window-station.csv
PYTHONPATH=pipeline/src uv run --project documentation --locked python -m return_window_pipeline.forecast train /tmp/return-window-station.csv --station pipeline/examples/weather/synthetic-station.json --artifact /tmp/return-window-forecast.json
uv run --project documentation --locked python -m runtime.hazards.replay --model /tmp/return-window-forecast.json --out web/mission-preview/src/hazards/replay.json
```

The optional loopback API computes the same drill frames when queried and caches
them for the session. From the repository root, start it with:

```sh
uv run --project documentation --locked python -m runtime.planning_api --engine marswalk --hazard-model /tmp/return-window-forecast.json
```

Start Vite from `web/mission-preview` with `VITE_HAZARD_RUNTIME=1 npm run dev`.
Set `HAZARD_RUNTIME_PORT` to match `--port` if the planning API uses a port other
than 8000. The client checks that each response matches the bundled scenario and
uses the local bundle if the service times out, is unavailable, or returns a
different scenario. If the service can assess routes but its model artifact
cannot be used, the forecast is shown as unavailable.
