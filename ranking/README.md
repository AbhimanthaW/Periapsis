# Cell ranking backend

The ranker targets all 196,608 `HPX128:<nested_index>` cells. It does not
read the 56-entry atlas registry. Place these release assets in the ignored
`data/ranking-inputs/` directory:

- `mars-cell-map-v0.1.0`: `cells-enriched.ndjson.gz`
- `mars-cell-map-v0.2.0`: `cell-ranking.ndjson.gz`,
  `ranking-features.json.gz`, `cells-enriched-sourced.ndjson.gz`,
  `sourced-catalogue-manifest.json`

From the repository root:

```sh
uv run --project documentation --locked python -m ranking.inputs data/ranking-inputs
uv run --project documentation --locked python -m ranking.build --inputs data/ranking-inputs --output data/ranking-pack --release
# Separate nonrelease software demonstration:
uv run --project documentation --locked python -m ranking.build --inputs data/ranking-inputs --output data/ranking-demo --with-demo
uv run --project documentation --locked python -m runtime.planning_api --ranking-pack data/ranking-pack
```

The verifier checks every SHA-256 before parsing, checks the sourced
manifest's baseline digest, enforces NESTED row order and prints observed
counts. The compiler writes a versioned, memory-mapped support pack and a
compressed SQLite detail store. The local service exposes `POST /api/v1/rank`
and `GET /api/v1/cell/HPX128:<index>`. No frontend changes are included.

The published group totals count each cell's **first** geologic unit. Four
boundary cells have two unit records; counting both group associations gives
different totals. The input gate reports the number of two-unit cells so this
choice stays explicit.

`concepts.json` lists 72 concepts: 25 live, 2 flagged live, 28 catalogue,
10 demo and 7 unsupported. The parser uses `lexicon.json` forms and reports
negated, unsupported, demo and unknown words. Catalogues without survey masks
report missing detections as `Not reported`. MOLA, measured TES and SWIM each
keep their own coverage. Records and method compatibility stay separate from
Match.

The demo pack reuses the repository's 28-cell `synthetic-science-v1` fixture
and adds fixed-seed spatial software controls. Its manifest records the
fixture digest, seed and `synthetic: true`. Demo support is separate from real
support, including propagated and derived concepts; the API requires
`include_demo: true` to use it. `--release --with-demo` fails.

Run the backend tests and benchmark:

```sh
uv run --project documentation --locked python -m pytest tests/ranking runtime/tests/test_planning_api.py -q
uv run --project documentation --locked python -m tests.ranking.bench_ranking
```

The input data leaves 240 cells without a geologic unit; no neighbouring unit
is imputed. The four two-unit boundary cells use their first unit for the
published group totals. The glacial-apron and mass-wasting readings and draft
thresholds need scientific review. The 72-concept release pack is about
30.6 MB, exceeding the plan's 20 MB target; its support matrix and neighbour
table already exceed 20 MB together. The compressed detail store is separate.
