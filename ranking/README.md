# Cell ranking model

The ranking population is all 196,608 Nside-128 NESTED HEALPix cells. The old
56-entry atlas registry is not an input. Before building, place the pinned
release assets in the ignored `data/ranking-inputs/` directory:

- `mars-cell-map-v0.1.0`: `cells-enriched.ndjson.gz`
- `mars-cell-map-v0.2.0`: `cell-ranking.ndjson.gz`,
  `ranking-features.json.gz`, `cells-enriched-sourced.ndjson.gz`,
  `sourced-catalogue-manifest.json`

From the repository root, with the locked documentation environment:

```sh
uv run --project documentation --locked python -m ranking.inputs data/ranking-inputs
uv run --project documentation --locked python -m ranking.build --inputs data/ranking-inputs --output data/ranking-pack --release
# For a separate, nonrelease software demonstration:
uv run --project documentation --locked python -m ranking.build --inputs data/ranking-inputs --output data/ranking-demo --with-demo
uv run --project documentation --locked python -m runtime.planning_api --ranking-pack data/ranking-pack
```

With the service running, open `/explore` in the Vite frontend. It queries
`POST /api/v1/rank`, displays a Nside-32 heat overlay, table, parse report,
source-product counts and selected cell detail. The heat map displays tile
centres rather than full cell boundaries. The service does no network work at
query time.

`concepts.json` lists all 72 concepts in the supplied implementation prompt:
25 live, 2 flagged live, 28 catalogue, 10 demo and 7 unsupported. The
`lexicon.json` forms adapt the repository's prototype vocabulary to the new
IDs. Unsupported terms remain in the parse report and cannot trigger a
ranking. Missing catalogue detections have unknown survey coverage and appear
as `Not reported`; SWIM coverage and measured TES thermal inertia have their
own masks. Records counts never enter Match.

The optional demo pack reuses the repository's 28-cell
`synthetic-science-v1` fixture and adds seeded spatial software controls where
needed. The fixture digest and seed are in the manifest. Its support matrix is separate
from real support, including propagated parents and derived concepts. An API
request must set `include_demo: true` for synthetic values to contribute.
Affected area concepts carry `DEMO` status and `Synthetic support` flags.
`--release --with-demo` fails before reading inputs.

Checks:

```sh
uv run --project documentation --locked python -m pytest tests/ranking runtime/tests/test_planning_api.py -q
uv run --project documentation --locked python -m tests.ranking.bench_ranking
cd web && npm ci && npm run build
```

Scientific limits: 240 cells have no geologic unit; no neighbouring unit is
imputed. Four boundary cells have two unit records, and the published group
totals count the first. The `glacial-apron` and `mass-wasting` readings are
flagged. Structure-length, mixed-age and approximate-bound thresholds remain
draft rules from the supplied prompt. The ten demo concepts are spatial
software fixtures, not Mars detections. The full pack currently exceeds the
proposed 20 MB target because 72 concept rows, a second demo matrix, three
pyramids and an eight-neighbour table are stored separately. The generated
SQLite detail store is additional to the pack-size figure.
