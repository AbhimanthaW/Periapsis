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
The immutable pack stores compressed arrays. At service startup they are
verified, decoded into a content-addressed local cache and memory-mapped;
workers using the same pack share those decoded pages. The detail database
compresses 1,024 cell records per indexed block. A separate compressed
catalogue-context file is loaded for area labels and evidence. The manifest
binds every runtime file, including the ledger, lexicon, source receipt and
detail database. The local service exposes `POST /api/v1/rank`
and `GET /api/v1/cell/HPX128:<index>`. With the service running, open
Ranked areas in the local Atlas to query the release pack. Each result's
`terrain_screening` reports the percentage of evaluated cells mapped as either
mass-wasting or polar dunes in USGS SIM 3292. Unmapped cells are excluded
from the denominator. The screening describes mapped units at regional scale.

The published group totals count each cell's **first** geologic unit. Four
boundary cells have two unit records; counting both group associations gives
different totals. The input gate reports the number of two-unit cells so this
choice stays explicit.

`concepts.json` lists 72 concepts: 25 live, 2 flagged live, 28 catalogue,
10 demo and 7 unsupported. Release packs report stratigraphy, hydrothermal,
climate, ocean, groundwater, periglacial and layered deposits as unsupported.
A DEMO pack provides opt-in software fixtures for those seven concepts. The
parser uses `lexicon.json` forms and reports
negated, unsupported, demo and unknown words. Catalogues without survey masks
report missing detections as `Not reported`. MOLA, measured TES and SWIM each
keep their own coverage. Records and method compatibility stay separate from
Match.

The demo pack reuses the repository's 28-cell `synthetic-science-v1` fixture
and adds fixed-seed spatial software controls. Six extra synthetic delta
centres on mapped old terrain make the headline objective large enough to
exercise a top-20 ranking; all eight delta control coordinates are in the
manifest. Alluvial fan, valley network, clays, sulfates, carbonates, silica
and olivine retain their original centre and use the primary stream to
place seven additional centres. Glacial landforms and the seven added
fixtures draw eight centres each from a second stream, `[20261114, 2]`.
Each added centre is at least 500 km from its layer's other centres and
600 km from each delta control. The headline delta query retains its Direct
area membership and order. Indirect support can still change Match scores,
coverage counts and the heat map.

For visual plausibility, the seeded glacial footprint uses 30–50° absolute
latitude, inspired by [Levy et al. (2014)](https://doi.org/10.1002/2014JE004685).
The ocean footprint uses lowland units, hydrothermal uses Noachian or
Hesperian units and periglacial uses 35–58° absolute latitude, with centres
below 55°. These masks are software controls.

Magnetism uses 16 seeded positive kernels on Noachian terrain. Each adds
`K h^3 / (d^2 + h^2)^1.5` with a scale of `h = 150 km`. The 99th percentile
scales the dimensionless values to full support before quantization. Small
values can round to zero in this globally evaluated fixture. The existing
28-cell fixture also supplies local magnetic values, combined by taking the
larger of the two normalized supports. The manifest records the seeded
centres, magnetic source parameters, fixture digest, seed and `synthetic: true`.
Demo support is separate from real
support, including propagated and derived concepts; the API requires
`include_demo: true` to use it. If synthetic support changes which eligible
cells a negation filters out, the returned ranking areas carry `demo: true`.
`--release --with-demo` fails.

Run the backend tests and benchmark:

```sh
uv run --project documentation --locked python -m pytest tests/ranking runtime/tests/test_planning_api.py -q
uv run --project documentation --locked python -m tests.ranking.bench_ranking
uv run --project documentation --locked python -m tests.ranking.check_sensitivity
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
  [SWIM4MIM products](https://swim.psi.edu/SWIM4MIMProducts.php). The published
  refined-map positive-indicator thresholds differ by depth (0.3, 0.4 and
  0.5 for 0–1 m, 1–5 m and >5 m). Those are map classification cutoffs, not
  automatically replacements for this model's ramp endpoint. See
  [Morgan et al. 2025](https://doi.org/10.3847/PSJ/ad9b24).
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
The base-record, catalogue and DEMO joins have independent content-addressed
caches keyed by source digests, rule version and relevant thresholds. Changing
the structure threshold leaves the base join cached; a warm compilation of
the concept arrays took 0.29 s here versus 15.28 s cold. The release pack is
17.8 MB and the DEMO pack 18.3 MB, each including its detail database. The
decoded arrays are larger and stay memory-mapped outside the immutable pack.
Pyramid pruning is optional under the current implementation prompt.

The DEMO headline objective now returns 39 Direct areas, with 20 pinned in
the golden fixture. Sensitivity still fails: moving the shallow-ice ramp
endpoint by ±20% retains 9–10 of 20 areas; reducing the structure endpoint
20% retains 14 of 20 young-volcanism and lava-flow areas. These are real
geographic tile changes, not an artefact of comparing cell memberships.
Trial baselines of 0.3, 0.4 and 0.5 for shallow ice and 10, 20 and 27 km for
structures did not satisfy both perturbation directions; changing one draft
number is not a defensible fix.

The 10 km structure endpoint is provisional; SIM 3292 describes a 100 km
minimum mapped line length, which does not establish a 10 km per-cell support
threshold. The two-stage NumPy grouping path collapses fully selected tiles
before connecting them across tile boundaries. With the locked Python 3.12
runtime, the five-concept uncached query took 40.6 and 41.1 ms in two
benchmark runs; `ancient ice` took 20.9 and 21.1 ms. Both meet the 50 ms
target on this Windows machine. Keep the PR in draft pending scientific
threshold review.
