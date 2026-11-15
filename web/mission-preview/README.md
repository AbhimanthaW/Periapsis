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
