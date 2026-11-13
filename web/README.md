# Return Window Architecture

A local engineering workspace for Periapsis’s proposed NASA Space Apps 2026 submission. The default document contains 152 components and 319 connections across the workspace. Its Data Pipeline overview has twelve subsystems and seven views. It records the operational design and the evidence required to build it. Algorithm and parameter edits change the blueprint and its exports.

## Run locally

Use Node.js 22.12 or newer and a current desktop browser. From this directory:

```sh
npm ci
npm run dev
```

Open the local address printed by Vite. For a compiled build, run `npm run build`, then `npm run preview`. Both serve only on the local machine. Installation requires the package registry once. The installed editor uses bundled assets, no credentials, and no network services.

## Mars Research Atlas

Open **Mars Atlas** from the Architecture Workspace, or visit `/atlas` on the same local server. The Atlas packages the Viking and MOLA global views, a bounded Jezero CTX optical subset, the 56-region index, and the original survey. It runs from local files while the server is running. See the [Atlas data and methodology](docs/mars-research-atlas.md) for source credits, limits and regeneration. Run `npm run check:atlas` to validate the packaged registry and assets.

## Mission (in progress)

`/mission` is the astronaut workflow entry point. It currently shows the selected site and the planning service health. See the [mission frontend plan](docs/mission-frontend.md) for screens, API bindings and unavailable capabilities.

Start the loopback planning service from the repository root, then the dev server from `web/`:

```sh
uv run --project documentation --locked --offline python -m runtime.planning_api
npm run dev
```

Vite proxies `/api` and `/healthz` to `http://127.0.0.1:8000` in both `dev` and `preview`, so the browser uses same-origin requests. Set `RW_PLANNING_API_ORIGIN` to point the proxy elsewhere. `VITE_RW_SITE` selects the mission site. Leave it empty (the default) until the primary site is approved. `VITE_RW_SITE=jezero-control` selects the Jezero engineering control.

## Explore and edit

- **Complete system** follows external archives through the offline build, local pack, routing, decision and crew interface. Expand any subsystem or select it and choose **Focus subsystem**.
- **Data pipeline** has seven views for the full pipeline, global atlas, region evaluation, regional processing, terrain, science evidence and release checks. Select a summary arrow to inspect the underlying editable connections. **All links** reveals secondary dependencies.
- **Scientific models** includes ten views of 14 model families. Inspect formulations, valid inputs, parameter sources, evidence, validation status and research decisions. The views share the canonical pipeline, runtime and scientific model records. **Corridor closure** retains the eight-step Jezero reference case.
- Select a component to edit its details, I/O, model, parameters, dataset record, quality gate or links. Text fields commit when you leave the field. Enter commits a single-line field. Model parameters include units, provenance and constraints.
- Drag components or whole subsystems to rearrange the current view. Shift-drag to box select. Add components from the palette and connect them from the toolbar or by dragging from a component’s right port to another component’s left port.
- The browser saves the document automatically for its current origin. **Export editable JSON** creates a portable backup. **Import architecture JSON** checks the schema and references before replacing the open document. SVG and PNG capture the displayed diagram without editor controls. **Reset layout** clears positions for the current view. **Restore default architecture** restores the source blueprint. Undo and redo are available during the current session.

## Document format

| Field | Purpose |
| --- | --- |
| `schemaVersion`, `architectureVersion` | Import format and editable blueprint version. |
| `groups` | Subsystem names, phases, summaries and descriptions. |
| `components` | Stable IDs, group membership, category, status, evidence class, I/O, parameters, algorithm and dataset records, quality gates, model family projections, research decisions, editable workstream ownership, dependencies and citations. |
| `connections` | Directed source and destination IDs, interface kind, payload, format, protocol, units, CRS, resolution, required metadata, failure policy, dependencies and validation. |
| `decisionSteps` | Ordered component IDs, captions and the underlying connection IDs for each walkthrough transition. |
| `layout`, `viewSettings` | Per-view and per-pipeline-view positions, active view, expansion, focus, filters and viewport. Grouped child positions are relative to their subsystem. |

The [default architecture JSON](public/default-architecture.json) is an importable snapshot. The source specification is in `src/initial.ts` and the TypeScript types and import validator are in `src/schema.ts`. Run `npm run check:data` to validate IDs, references, the JSON round trip, all pipeline views, gate metadata and saved-document migration. Regenerate the snapshot after editing the seed with `npm run check:data -- --write`.

## Planetary documentation engine

The [scientific core](../documentation/README.md) implements the footprint-index and availability boundary as an installable Python package. It reads a versioned evidence sidecar and provides HEALPix documentation summaries and local model evidence checks. Run the archive-verified Jezero example from the engine directory. The architecture diagrams and atlas continue to display their source blueprint and survey assessments.

## Data pipeline boundaries

- **Planetary mapping** uses MOLA topography, separately rendered relief, CTX optical context and selected geology and mission overlays. CTX has published polar limits and internal gaps. The proposed display strategy uses precomputed levels and a bounded local subset. [NASA PDS MOLA](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) · [Murray Lab CTX V01](https://murray-lab.caltech.edu/CTX/V01/TilePages/)
- **Regional evaluation** supports an extensible registry for the current 56-region research effort. Availability, scientific value and processing suitability are separate records. The ranking specification is provisional and has no default weights or fabricated region entries, scores or rankings.
- **Detailed routing** depends on native terrain support, declared Mars reference and explicit regional quality checks. The original Jezero source examples remain useful. Exact regional products, thresholds, projection parameters and target positions depend on build evidence. [USGS planetary projections](https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/learning-about-map-projections/) · [USGS stereo DTM quality comparison](https://www.usgs.gov/publications/evaluating-stereo-dtm-quality-jezero-crater-mars-hrsc-ctx-and-hirise-images)
- **Release** separates a versioned global atlas subset from immutable regional packs. Pack capabilities and omissions are explicit. G1–G10 start at **Not evaluated**. The workspace documents proposed methods and contracts. It contains no processed Mars assets, recorded gate passes or operational routing results.
- **Ownership** uses Workstream A for geospatial and terrain data, Workstream B for scientific context and regional intelligence, and shared ownership for region, coordinates, release and provenance contracts. The Owner field is editable.

## Upgrading existing documents

Architecture 3.0 uses additive fields in JSON schema version 1. On the same browser origin, recognized legacy Return Window saves upgrade on load. Legacy starter exports upgrade on import. The merge carries forward edited fields, custom components and links, removed legacy items and saved positions. New scientific views have independent layouts. Prior coordinates remain in JSON under their legacy layout keys. The active scientific viewport refits once on upgrade; Data Pipeline layouts and settings carry forward. Exporting JSON remains the portable backup.

## Scientific model design

See the [Scientific Model Design Review](docs/scientific-model-design-review.md) for the 56-region audit, primary references, formulas, model inventory and implementation priorities. The proposed runtime sequence is directed route candidates → resource ledger and hard gates → finite-set Pareto comparison → mission priorities → explanation. Parameter edits update this architecture document. They do not run a mission model. All model validation statuses start at **Not evaluated**.

## Editor stack

React, TypeScript, Vite, React Flow, Zod, Lucide and local CSS. React Flow owns canvas gestures and keyboard selection. The diagram and image exporter share box and edge geometry. The operational technologies appear inside the architecture as specifications.
