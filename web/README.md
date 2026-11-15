# Return Window web app

The Return Window frontend supports Mars cell exploration, evidence review and simulated mission planning.

## Run the frontend locally

Use Node.js 22.12 or newer and a current desktop browser. Run these commands in `web/`:

```sh
npm ci
npm run dev -- --port 4175 --strictPort
```

Open [Explore Mars](http://127.0.0.1:4175/#globe). Its entry point is `web/src/main.tsx`. Install dependencies once before working offline.

Use `npm run check:atlas` to verify the bundled map layers and regional source registry used by Explore.

## Connect the mission backend

Build the release once using the [offline runbook](../docs/offline-readiness.md#build-once-with-network-access). From the repository root, start the release service before running Vite in a second terminal.

```sh
uv run --project documentation --locked --offline python -m runtime.release serve data/offline-release
```

Vite forwards API, health and packaged rehearsal requests to `http://127.0.0.1:8000`. Set `RW_PLANNING_API_ORIGIN` when starting Vite if the backend uses another port. For API-only development, start `runtime.planning_api` with `--engine marswalk` and provide the sourced pack with `--ranking-pack`. The packaged service also supplies the hazard replay interface and model.

Explore resolves locations to HEALPix Nside 128 cells through the backend. Named features provide approximate orientation. Set a Mars base, inspect evidence, and enter the labeled synthetic Marswalk to use the selectable-base planner. **Demo** selects Arcadia's reviewed footprint and prefills the objective. Entering the simulation submits its preset route for operator review. The legacy fixed-fixture regression opens at `/mission?view=simulation`.
