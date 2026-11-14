# Return Window Mission

Mission opens at `/` or `/mission`. Site investigation displays evidence for the configured site. **Enter simulated Marswalk** opens a synthetic scenario where closures and remaining time change the return and science decisions. See the [frontend implementation notes](docs/mission-frontend.md).

## Run locally

Use Node.js 22.12 or newer, Python 3.12 and uv. From the repository root, provision the Python environment and start the planning service.

```sh
uv sync --project documentation --locked --python 3.12
uv run --project documentation --locked --offline python -m runtime.planning_api
```

In a second terminal, run these commands from `web/` and open the printed URL.

```sh
npm ci
npm run dev
```

For a built preview, run `npm run build` followed by `npm run preview`. Both servers forward `/api` and `/healthz` to `http://127.0.0.1:8000`. Set `RW_PLANNING_API_ORIGIN` to use another local planning service.

## Jezero engineering control

To open Jezero site investigation, start the planning service from the repository root with its committed package and query.

```sh
uv run --project documentation --locked --offline python -m runtime.planning_api \
  --evidence-package evidence/jezero/jezero-evidence.json \
  --evidence-query evidence/jezero/jezero-route.json
```

From `web/`, use `VITE_RW_SITE=jezero-control npm run dev`, or set the same variable when running `npm run build`. The API reports this as operator-configured evidence with unverified provenance. Jezero is the engineering control. The primary site is still unqualified.

The [development workspace](../reference/engineering-workspace/README.md) provides the separate editor and Atlas.
