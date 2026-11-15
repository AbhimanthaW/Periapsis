# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

Arcadia Planitia is the primary demo region. Its pinned MOLA handoff supports regional context and an evidence decision. Keep tactical routing gated until a qualifying local terrain pack is available. Jezero is the comparison control and the setting for separate simulation rehearsals.

For Explore, Ranked Areas, and Investigation, launch unselected. Named landmarks orient the operator; ranking and investigation use HEALPix Nside 128 cells. Keep a user-entered Mars base separate from the science target. The base is the starting location passed to the simulated Marswalk workspace.

In the saved-base Marswalk workspace, open Route on the Mars imagery with separate access to the computed rehearsal route. Use the demo's comparison layout for Analysis and its map, playback bar, and status strip for Monitor. Keep synthetic path geometry separate from georeferenced Mars imagery.
