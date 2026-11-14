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
counts. Build to a new directory, then point the service at the complete pack.
The immutable pack includes a versioned, memory-mapped support matrix and a
compressed SQLite detail store. Its manifest binds every runtime file,
including the ledger, lexicon, source receipt and detail database. The local service exposes `POST /api/v1/rank`
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

## Scientific scope and release checks

The ranker is a global science discovery tool. It has no operational role in
mission feasibility, local terrain qualification, route costs or instrument
access. A Direct match meets the selected concept thresholds in the same
~27 km cell. It does not date a catalogue feature by the cell's mapped unit
age. Method labels are screening rules. Records counts describe catalogue
coverage and do not contribute to Match.

- SWIM measures consistency among subsurface ice indicators in three depth
  bands. Only SWIM contributes to those rows, including broad `ice`. Geologic
  evidence such as polar caps and glacial aprons has separate concepts. The
  26,568 cells poleward of 60° stay Not evaluated for SWIM. See
  [SWIM4MIM products](https://swim.psi.edu/SWIM4MIMProducts.php).
- SIM 3292 supports interpreting `lAa` as glacial moraines and `Aa` as including
  gravity-spreading, landslide and slump deposits. `ANa` is a composite map
  unit with ice-rich Amazonian materials and older terrain. The draft glacial
  interpretation of all `ANa` cells and the 0.6 mixed-age coefficient
  remain provisional. The 240 geologic gaps stay unknown. Four boundary
  cells contribute to the published counts through their primary unit.
  See [SIM 3292](https://pubs.usgs.gov/sim/3292/pdf/sim3292_pamphlet.pdf).
- Apparent thermal inertia is a surface texture proxy. Water-related
  evidence plus old terrain is a screening proxy for habitability interest.
  See [Putzig and Mellon](https://doi.org/10.1016/j.icarus.2007.05.013) and
  [Grotzinger et al.](https://doi.org/10.1126/science.1242777).
- Gazetteer rectangles are approximate named context. Catalogue detections
  provide cell associations. An uncovered concept can have separate broader
  thematic affinity without changing its evidence state.
- All 27 record-derived threshold counts reproduce. Folded support raises the
  counts for outflow (1,753 → 2,265), impact (10,732 → 14,205), and volcanic
  (42,505 → 42,559) through structure and hierarchy evidence.

The ranking CI job builds and tests both packs from the pinned release assets.
Use `python -m tests.ranking.check_sensitivity` in the locked environment to
perturb each nonzero ramp threshold by ±20% and compare the top 20 areas.
The release arrays and metadata occupy 30.6 MB against a 20 MB target, with
206 MB for SQLite. The required dense support and int32 neighbour arrays
alone occupy 20.4 MB. The content-addressed layer build cache is outstanding.
Pyramid pruning is optional under the current implementation prompt.
At the draft thresholds, changing the shallow ice ramp endpoint by ±20%
retained only 9–10 of its top 20 areas. Reducing the structure ramp endpoint
by 20% retained 14 of 20 young-volcanism and lava-flow areas. The DEMO delta
objective supplies eight Direct areas, so its top-20 robustness remains
unqualified. An uncached five-concept query with zero Direct matches also
exceeded 50 ms. Keep the ranker in draft while these gates are open.
