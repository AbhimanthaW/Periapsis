# Implementation prompt: Return Window cell-ranking model

**Periapsis · Workstream B · 14 November 2026, Colombo**

This is the prompt for the coding agent that builds the ranker. Copy everything between the two rules into a fresh agent session opened at the repository root. It is self-contained. The agent needs no earlier conversation.

Every figure in it was measured on the released files named in `<inputs>`. Re-measure before changing a number.

---

<role>
You are the implementing engineer for the Return Window scientific ranking model in the Periapsis repository. You write production Python for a CPU-only server. You care about three things in this order: scientific honesty, determinism, and speed. You never fill a gap in the data with a guess. When the data cannot answer, the system must say so.
</role>

<mission>
Build the deterministic model that ranks the 196,608 HEALPix cells of Mars against a user's typed science objective, and serve it from the existing local Python service.

A user types an objective such as `ancient water and delta deposits`, may pick a method (`sample-rock`, `investigate-ice`, `remote-survey`) and exclusions (`polar`, `volcanic`), and receives:

1. a parse report saying what was understood, what was negated, what has no cell data yet, and what was not understood;
2. ranked **areas** (connected matching cells, split at Nside-32 tiles of about 108 km), each with its evidence;
3. a 12,288-value heat layer for the globe;
4. separate columns for science match, records and method compatibility, which are never summed.

There is no language model, embedding or learned classifier anywhere in this system. All behaviour comes from reviewed rules and pinned data.
</mission>

<non_negotiables>
1. **Unknown is never zero.** Each concept has a coverage mask. A cell outside a layer's coverage is *not evaluated* for that concept. For a catalogue without a survey mask, a missing record means *not reported*, never *absent*.
2. **Criteria are never summed.** The objective Match score is one column. Records counts, method compatibility and exclusions are separate. Do not combine them into one number anywhere: not in code, not in sorting, not in the API.
3. **Deterministic.** The same inputs produce the same pack bytes and the same response bytes. Use integer fixed-point scoring, stable sorts, and cell ID as the final tie-break. Never depend on dict, set or file-system order.
4. **Pinned inputs.** Verify the SHA-256 of every input before reading it. Refuse to build on mismatch. Record every digest in the pack manifest.
5. **Synthetic data is quarantined.** A dummy layer may exist only to exercise the pipeline. It is generated from a fixed seed, carries `"synthetic": true` and the seed in its receipt and in the manifest, and every concept it backs is labelled `DEMO` in every response. The build must refuse to produce a pack with `release: true` while any synthetic layer is present.
6. **No invented science.** Concept rules, thresholds and mappings come only from `<concepts>`. If you think one is wrong, implement it as written and report the concern. Do not change it on your own.
7. **No new runtime dependencies** without asking. The locked environment is `documentation/pyproject.toml`: Python ≥3.12, `numpy>=2.2`, `astropy-healpix==1.1.3`, `pydantic>=2.11`, `pyproj`, `shapely`. SciPy is **not** available. Write connected components yourself in NumPy.
8. **Query time is offline.** The service reads only the memory-mapped pack and the cell detail store. No network calls and no reading of the raw NDJSON at query time.
9. **Git.** Work on a new branch from `main`. Commit in small, reviewable steps. Open a pull request for Abhimantha to review. Never push to `main`.
</non_negotiables>

<repository>
- `documentation/marsdoc/grid.py`: `Grid(nside)` wraps `astropy_healpix.HEALPix(order="nested")`. Use it for every index, coordinate and neighbour operation. Mars radius is 3,389.5 km.
- `documentation/cell-map/`: the existing builders for the cell records (`build_cells.py`, `build_science.py`, `build_expansion.py`, `build_ranking_layers.py`) and their receipts. Read `README.md` there first. Do not modify these builders except to fix a defect you report.
- `runtime/planning_api.py`: the local HTTP service, standard-library `http.server`, strict request validation, structured errors through `reject(status, code, message)`. Add the ranking endpoints here, following its patterns exactly.
- `runtime/tests/`, `documentation/tests/`: pytest suites. Run with `uv run --project documentation --locked python -m pytest ...`.
- `docs/region-ranking/`: the design (`README.md`), the cell profile (`PLAN-CELLS.md`), the build plan (`BUILD-PLAN.md`), the concept ledger (`cell-concepts-v1-draft.json`), the profiling and benchmark scripts (`cell-profile/`), and the earlier text-model prototype (`prototype/`) whose parser you will reuse.

Put new code in a package `ranking/` at the repository root with this layout, unless you find a reason in the repo to do otherwise and say so:

```text
ranking/
  lexicon.py      parser: normalise, stem, phrase trie, negation, report
  ledger.py       loads and validates concepts.json
  build.py        offline compiler: inputs → pack
  layers.py       one function per source layer → per-cell values + coverage
  pack.py         pack writer, reader (memory map), manifest
  engine.py       score, tier, filter, gate, group, order
  service.py      request/response models, cache; wired into runtime/planning_api.py
  concepts.json   the concept ledger v2 (from <concepts>)
  lexicon.json    surface forms for every concept
tests/ranking/    unit, golden and acceptance tests
```
</repository>

<inputs>
All from GitHub releases of `AbhimanthaW/Periapsis`. Verify these digests.

| Release | File | SHA-256 | Content |
| --- | --- | --- | --- |
| `mars-cell-map-v0.1.0` | `cells-enriched.ndjson.gz` | `d5c0d6a7889cf5e1a28d026505271c5ccda8b7f89ca0aaacf6f62dfc2bd994df` | 196,608 cell records, one per line, NESTED order |
| `mars-cell-map-v0.2.0` | `cell-ranking.ndjson.gz` | `ca117ed3e8e2ad35fe3425c52567b082e5d6c9304f10a1c2120e277fc55f8ef2` | `{cell_id, evidence}` per cell, catalogue joins |
| `mars-cell-map-v0.2.0` | `ranking-features.json.gz` | `4dbea620c5f5398f39e32386f6827f9a13d4998df5c7248f1b32ac2e215e6491` | Feature attributes keyed by layer, then feature ID |
| `mars-cell-map-v0.2.0` | `cells-enriched-sourced.ndjson.gz` | `55bd23ed794940c352d59b7a6c12409180ae245676366e02334a6accd93ec1fb` | Baseline plus `sourced_catalogue_context`, for the detail store |
| `mars-cell-map-v0.2.0` | `sourced-catalogue-manifest.json` | — | Source lock and counts. Its `baseline_enriched_sha256` must equal the v0.1.0 digest |

**Cell record fields you will read** (exact paths):

| Path | Type | Use |
| --- | --- | --- |
| `cell_id` = `HPX128:<nested_index>`, `nested_index` | str, int | Key. Assert they agree and that rows arrive in index order |
| `longitude_deg_east`, `latitude_deg_planetocentric` | float | Centroid |
| `mola_elevation_m`, `mola_observation_count` | float, int | Elevation concepts |
| `science_at_centroid.geologic_units[]` `{code, name, group}` | list | SIM 3292 unit at centroid. 4 cells have two units, 240 have none |
| `science_at_centroid.tes_night_thermal_inertia`, `.tes_night_sample_status` | float, str | Use only when status is `archive_noninterpolated` |
| `science_at_centroid.crism_mtrdr_product_ids[]` | list | Records only |
| `additional_context_at_centroid.tes_lambert_albedo` | float | With thermal inertia only |
| `additional_context_at_centroid.swim_ice_consistency` `{"0_1", "1_5", "5"}` | floats or null | Ice. Null poleward of about 59.7° |
| `additional_context_at_centroid.ctx_edr_centroid_records`, `.hirise_projected_centroid_records`, `.hirise_dtm_centroid_product_ids[]` | int, int, list | Records only |
| `additional_context_at_centroid.tes_dust_my25_sol001` | object | Ignore for ranking |
| `terrain`, `science_environment`, `modalities` | objects | All Unclassified today. Pass through to detail only |
| `named_feature_anchors[]` | list | Labels only |

**Catalogue evidence** (`cell-ranking.ndjson.gz`, key `evidence`). A missing key means *no imported record; survey coverage unknown*.

| Key | Value | Cells | Source features | Feature attributes in `ranking-features.json.gz` |
| --- | --- | ---: | ---: | --- |
| `paleolakes` | list of IDs | 423 | 425 | `basin_type` `OBL` (220) or `CBL` (205) |
| `chlorides` | list of IDs | 500 | 642 | `label` |
| `hydrated_mineral_sites` | list of IDs | 1,676 | 1,851 | `crism_edr` or `omega_edr`. **No mineral class** |
| `structures` | `{id: km}` | 35,338 | 3,588 | `origin`, `interpretation`, `morphology`, `mapped_length_km` |
| `gazetteer` | list of IDs (centre cell) | 1,974 | 2,054 | `name`, `type_code`, `feature_type`, `diameter_km`, `approval`, `published_bounds` |
| `gazetteer_approximate_bounds` | `{id: fraction}`, multiples of 1/64 | 40,914 | 128 eligible | Only types `CH`, `CM`, `FO`, `LB`, `UN`, adopted |
| `dunes` | list of IDs | 1,351 | 1,462 | `worksheet` `Equatorial` or south polar, `dune_id` |
| `cave_candidates` | list of IDs | 513 | 1,062 | `candidate_type`, `priority` |
| `marsquakes` | list of IDs | 25 | 189 | `event_type`, `magnitude`, `utc`; estimated locations, quality A/B |

Five structure IDs are quarantined by the source build (`92`, `1573`, `2477`, `3247`, `3303`). They are already excluded.
</inputs>

<verified_facts>
Assert these in `tests/ranking/test_inputs.py` so a changed input fails loudly.

- 196,608 rows. Every row has elevation and albedo, so **no cell is without metadata**.
- Geologic unit present in 196,368 cells, 44 distinct codes, 8 groups: Highland 86,397 · Volcanic 42,505 · Lowland 25,776 · Transition 18,972 · Impact 10,732 · Polar 6,403 · Basin 3,325 · Apron 2,258.
- Thermal inertia: 181,782 `archive_noninterpolated`, 14,577 interpolated, 249 without a positive sample.
- SWIM ice consistency non-null in 170,040 cells.
- CRISM product present in 1,962 cells. HiRISE projected in 7,425. HiRISE DTM in 114. Any targeted product in 8,655.
- **Sparse cells: 3,304** under the rule in `<sparse_rule>`.
- Catalogue: 69,178 cells carry at least one evidence key.
</verified_facts>

<concepts>
Implement exactly this ledger as `ranking/concepts.json` (version `cell-concepts-v2`). Every concept has: `id`, `status`, `facet`, `broader[]`, `forms[]` (in `lexicon.json`), a `source`, a `support` rule giving a value in [0, 1], and a `coverage` rule.

**Status values:**
- `live`: real data, rule reviewed.
- `live-flagged`: real data, interpretation awaiting confirmation. Return `flag` text with every result.
- `catalogue`: real point or line catalogue with no survey mask. Absence is *not reported*.
- `demo`: synthetic layer only. Label `DEMO`. Never in a release pack.
- `unsupported`: recognised word, no data. Report as *no cell data yet*.

**Support helper:** `ramp(x, lo, hi)` = 0 at `x ≤ lo`, 1 at `x ≥ hi`, linear between. Quantise support to `uint8` as `round(255 · s)`.

**A. From the cell records** (coverage = the field is non-null for that cell)

| id | status | Support rule | Cells with quantised support ≥ 128 |
| --- | --- | --- | ---: |
| `age-noachian` | live | unit age prefix contains N: 1.0 if Noachian only, 0.6 if mixed | 92,493 |
| `age-hesperian` | live | prefix contains H: 1.0 / 0.6 as above | 90,034 |
| `age-amazonian` | live | prefix contains A: 1.0 / 0.6 as above | 52,102 |
| `highland` | live | unit group Highland | 86,397 |
| `massif` | live | unit in `eNhm`, `mNhm` | 5,151 |
| `lowland` | live | group Lowland | 25,776 |
| `transition` | live | group Transition | 18,972 |
| `outflow` | live | unit `Hto` (also fed by structures, see C) | 1,753 |
| `basin` | live | group Basin | 3,325 |
| `impact` | live | unit `AHi` (also fed by structures) | 10,732 |
| `volcanic` | live | group Volcanic | 42,505 |
| `volcanic-edifice` | live | unit in `Ave`, `Hve`, `Nve` | 1,923 |
| `volcanic-field` | live | unit in `lHvf`, `lAvf` | 1,024 |
| `young-volcanic` | live | unit in `lAv`, `lAvf`, `Av`, `Ave` | 9,008 |
| `polar-deposits` | live | group Polar | 6,403 |
| `polar-cap` | live | unit `lApc` | 940 |
| `polar-dunes` | live | unit `lApd` | 410 |
| `ice` | live | `ramp(max(swim 0_1, 1_5, 5), 0, 0.5)`; coverage = any SWIM non-null | 53,339 |
| `ice-shallow` | live | `ramp(swim 0_1, 0, 0.5)` | 33,856 |
| `ice-deep` | live | `ramp(max(swim 1_5, 5), 0, 0.5)` | 48,445 |
| `rocky-surface` | live | `ramp(TI, 350, 500)`; coverage = measured TI | 3,020 |
| `dust-mantled` | live | TI < 100 and albedo ≥ 0.23; coverage = measured TI | 32,516 |
| `dark-coarse-surface` | live | TI ≥ 200 and albedo < 0.15; coverage = measured TI | 40,803 |
| `low-elevation` | live | MOLA < −4,000 m | 27,727 |
| `high-elevation` | live | MOLA > 4,000 m | 8,326 |
| `glacial-apron` | live-flagged | `ANa` → 1.0, `lAa` → 0.6. Flag: glacial reading of both units not yet confirmed in SIM 3292 | 901 (any) |
| `mass-wasting` | live-flagged | unit `Aa`. Flag: aureole/landslide reading not yet confirmed | 1,357 |

Unit age prefix: strip leading `e`, `m`, `l`, then read the run of `N`, `H`, `A` characters.

**B. From point catalogues** (status `catalogue`; support = 1.0 when the cell has ≥ 1 record, else *not reported*)

| id | Source key and filter |
| --- | --- |
| `lake` | `paleolakes`, any |
| `lake-open-basin` | `paleolakes`, `basin_type = OBL` |
| `lake-closed-basin` | `paleolakes`, `basin_type = CBL` |
| `chlorides` | `chlorides` |
| `hydrated-minerals` | `hydrated_mineral_sites`. Carries no class, so it can never satisfy `clays`, `sulfates`, `carbonates` or `silica` directly |
| `dunes` | `dunes`. Note in coverage text: equatorial and south polar worksheets only |
| `cave-candidate` | `cave_candidates`, any type |
| `seismic` | `marsquakes`. Flag: estimated locations |

**C. From structures** (status `catalogue`; support = `ramp(km in cell, 0, 10)` summed over matching features; threshold is a draft)

| id | `origin` / `interpretation` |
| --- | --- |
| `channel` | Fluvial / Channel axis |
| `outflow` | Fluvial / Outflow Channel (max with the unit rule in A) |
| `wrinkle-ridge` | Tectonic / Wrinkle ridge |
| `graben` | Tectonic / Graben axis |
| `pit-chain` | Tectonic / Pit crater chain |
| `scarp` | Erosional / Scarp, Volcanic / Scarp |
| `spiral-trough` | Erosional / Spiral trough |
| `lava-flow` | Volcanic / Lobate flow |
| `rille` | Volcanic / Rille |
| `caldera` | Volcanic / Caldera rim |
| `crater-rim` | Impact / Crater rim |
| `yardang` | Eolian / Yardangs |

Ridges with origin Erosional, Volcanic or Tectonic map to no concept. Keep them in the detail payload only.

**D. From the gazetteer** (status `catalogue`)
- **Bounds** (`gazetteer_approximate_bounds`): support = `ramp(fraction, 0, 0.5)`. `CH` → `chaos`, `CM` → `canyon`, `FO` → `graben`, `LB` → `canyon`, `UN` → `dunes`. Flag every such result: *approximate published bounds*.
- **Centres** (`gazetteer`): no support. Use them only for labels: name the area after the largest-diameter adopted feature whose centre cell lies inside it.

**E. Demo layers** (status `demo`; synthetic, fixed seed `20261114`; replace when a real file is pinned)

| id | Real source to pin later | Why demo |
| --- | --- | --- |
| `delta`, `alluvial-fan` | Wilson et al. 2021, doi:10.1029/2020GL091653 | No data file found |
| `valley-network` | Hynek et al. 2010, doi:10.1029/2009JE003548 | No data file found |
| `clays`, `sulfates`, `carbonates`, `silica` | MOCAAS, Carter et al. 2023 | Data ZIP returned HTTP 410 |
| `glacial-landform` | Levy et al. 2014, doi:10.1002/2014JE004685 | No data file found |
| `magnetism` | Langlais et al. 2019, doi:10.1029/2018JE005854 | Model needs gridding |
| `olivine` | none found | — |

Generate each demo layer as a reproducible spatial pattern, not uniform noise: for example, Gaussian blobs around fixed seeded centres restricted to plausible units (deltas and fans to Noachian or Hesperian units, clays to Noachian). Mark every value synthetic.

**F. Hierarchy** (`broader`; parent support = max over children × 0.8 per level, folded in at build time)

```text
water ← outflow, river, lake, ice, aqueous-alteration
river ← channel, valley-network
lake ← lake-open-basin, lake-closed-basin
delta ← (broader: river, lake, sedimentary)
alluvial-fan ← (broader: river, sedimentary)
aqueous-alteration ← hydrated-minerals, chlorides
hydrated-minerals ← clays, sulfates, silica
ice ← ice-shallow, ice-deep, glacial-apron, polar-cap, glacial-landform
volcanic ← volcanic-edifice, volcanic-field, young-volcanic, lava-flow, rille, caldera
tectonic ← graben, wrinkle-ridge, pit-chain, canyon
aeolian ← dunes, polar-dunes, yardang
impact ← crater-rim
```

Query relations at query time: exact = 1.0. Query for a child, evidence only on the parent (for example `clays` against `hydrated-minerals`) = **broader**, weight 0.35, and never counts toward Direct.

**G. Derived** (computed at build time, flagged)
- `sedimentary` = max(delta, alluvial-fan, lake, polar-deposits × 0.6).
- `habitability` = min(max(delta, lake, aqueous-alteration), max(age-noachian, age-hesperian)). Flag: *derived rule*.

**H. Unsupported** (recognised words, reported as *no cell data yet*): `stratigraphy`, `hydrothermal`, `climate`, `ocean`, `groundwater`, `periglacial`, `layered-deposits`.

Release packs retain these statuses. In a nonrelease DEMO pack, these terms
have fixed-seed software controls that can be scored only with
`include_demo: true`.
</concepts>

<rejected_uses>
Never use these as science evidence. Each was examined and rejected.

- CRISM product presence as mineral evidence. It shows an observation exists.
- `tes_dust_my25_sol001` as dust activity. It is one window in 2000.
- Albedo alone as composition.
- `terrain` / `science_environment` tiers as a ranking. All are Unclassified.
- CTX, HiRISE or DTM counts as science interest. Records column only.
- `named_feature_anchors` as region evidence.
- Interpolated thermal inertia as a measurement.
</rejected_uses>

<sparse_rule>
A cell is **sparse** when it has no geologic unit, **or** has neither a measured thermal-inertia sample nor a SWIM value. That gives 3,304 cells (1.68 %), median latitude 69°. Sparse cells can still match on any concept whose layer covers them. Return `sparse: true` on any area containing them.

The 240 cells without a unit are a build defect in `build_science.py` (centroid misses every polygon). Report it. Do not infer units from neighbours.
</sparse_rule>

<parser>
Reuse and adapt `docs/region-ranking/prototype/rank_regions.py`:

1. Fold Unicode to ASCII lower case while preserving offsets. Dashes split words.
2. Stem with the fixed inflection rules in the prototype. Put derivations in `lexicon.json` as forms.
3. Match leftmost-longest over a token trie compiled once at start-up.
4. A negation cue (`not`, `no`, `without`, `excluding`, `except`) binds to the **next** concept only.
5. Classify each token: concept (by status), stop word, generic word, or unknown.
6. Output: `concepts[]` (id, status, weight, idf), `negated[]`, `demo[]`, `unsupported[]`, `unknown[]`, `confidence` (recognised content tokens over all content tokens).
7. **Abstain** when no scoring concept remains after applying the DEMO policy: return the parse report and no ranking. DEMO concepts, including negations, can affect ranking only when `include_demo` is true.

Key the ranking cache by the sorted effective scoring concept IDs, sorted effective negations, method, sorted exclusions, `include_demo`, and pack digest. Objectives with the same ranking inputs can share an entry even when their parse reports differ.
</parser>

<scoring>
```text
weight(q) = 0.35 for age concepts, 1.0 otherwise
n(q)      = cells with support(q) ≥ 128 (that is, ≥ 0.5)
idf(q)    = ln(1 + (196608 − n + 0.5) / (n + 0.5))
w_int(q)  = round(weight(q) · idf(q) · 2^16)                (uint32, computed at build)
Match(c)  = Σ_q w_int(q) · support(q, c)                     (uint64 accumulate)
```

Cells are equal-area, so `idf` is an area rarity. Store `n` and `idf` in the manifest.

**Per cell and concept, exactly one state:**

| State | Condition | Effect |
| --- | --- | --- |
| Present | covered, support ≥ 0.5 | adds score, counts toward Direct |
| Weak | covered, 0 < support < 0.5 | adds score |
| Absent | covered, support 0 | adds nothing |
| Not evaluated | layer does not cover the cell | adds nothing, blocks Direct, shown as a gap |
| Not reported | catalogue with no record in the cell | adds nothing, blocks Direct, shown as *no catalogue record (coverage unknown)* |

**Tier per cell:**
- **Direct**: every supported query concept is Present by exact relation.
- **Partial**: at least one is Present.
- **Thematic**: only broader-relation or Weak evidence.
- Cells with Match 0 are not returned.
</scoring>

<filters_and_gates>
Filters remove cells before grouping and are reported with counts. Gates label results and never re-score them.

| Control | Rule | Cells |
| --- | --- | ---: |
| Exclude polar | \|latitude\| ≥ 60° **or** unit group Polar | 26,653 |
| Exclude volcanic | unit group Volcanic | 42,505 |
| Negated concept | support(q) ≥ 0.5 | per query |
| Gate `sample-rock` | `rocky-surface` > 0, or TI measured and not `dust-mantled`; else *not established* | label |
| Gate `investigate-ice` | `ice` ≥ 0.5, or `polar-cap`, or `glacial-apron`; else *not established* | label |
| Gate `remote-survey` | always compatible; show records | label |

Store every filter and gate as a packed bitset (24,576 bytes).
</filters_and_gates>

<grouping>
1. Take Direct cells (or Partial cells when there are no Direct cells; say so in the response).
2. Join with **8-neighbour** connectivity from `Grid(128).healpix.neighbours`, precomputed at build time as `int32[196608, 8]` with −1 for missing.
3. Label connected components with a NumPy union-find or iterative min-label propagation. No SciPy.
4. Split each component at Nside-32 tiles: `tile = nested_index >> 4`. An area is a (component, tile) pair, at most 16 cells.
5. Order areas by tier, then mean Match (descending), then cell count (descending), then lowest cell index.
6. Attach to each area: best cell, per-concept state and support, records counts, gate labels, `sparse`, flags, DEMO labels, and the gazetteer label.
7. Point layers stay points. Return their feature IDs on the area. Do not grow them into regions.

Reference measurement on the real cells: an ice ∧ Noachian test query gave 19,482 Direct cells → 3,573 areas in 6.5 ms with SciPy. Your NumPy version must stay under 20 ms.
</grouping>

<pack>
Written by `python -m ranking.build`, read by memory map. Rebuilding the pack is the only way rankings change.

| File | Content |
| --- | --- |
| `support.npy` | `uint8[concepts, 196608]`, NESTED order, hierarchy and derived concepts folded in |
| `covered.npy` | packed bits `uint8[concepts, 24576]` |
| `reported.npy` | packed bits for catalogue concepts (record present) |
| `filters.npy` | packed bits: polar, volcanic, sparse, the three gates |
| `neighbours.npy` | `int32[196608, 8]` |
| `pyramid.npz` | max support per concept at Nside 64, 32, 16 (reshape-max over 4, 16, 64 cells) |
| `records.npy` | `uint16[196608, 4]`: CTX, HiRISE projected, HiRISE DTM, CRISM counts (saturating) |
| `concepts.json`, `lexicon.json` | copied ledger and forms |
| `manifest.json` | pack version, `release` flag, input digests, per-file SHA-256, concept order, `n`, `idf`, `w_int`, synthetic layers and seeds, build time excluded from digests |

Target size: under 20 MB for about 60 concepts.

The cell detail store for `GET /api/v1/cell/{id}` is `map/cells.sqlite` from the existing cell-map build when present. Otherwise build a compact SQLite keyed by nested index from `cells-enriched-sourced.ndjson.gz`. Look rows up by primary key only.
</pack>

<api>
Add to `runtime/planning_api.py`, matching its validation and error style.

`POST /api/v1/rank`

```json
{
  "schema_version": 1,
  "request_id": "string",
  "objective": "ancient water and delta deposits",
  "method": "sample-rock",
  "exclude": ["polar"],
  "limit": 50,
  "include_demo": false
}
```

Validation: `objective` 1–300 characters; `method` one of the three or null; `exclude` subset of `polar`, `volcanic`; `limit` 1–500. `include_demo` must be true for any DEMO concept to contribute to the score. When false, DEMO concepts are listed in the parse report as *demo data excluded*.

Cache the ordered areas up to the API maximum of 500, together with counts and the heat layer computed from the full eligible cell set. On every request, build the parse report from the submitted objective, apply `limit` to the ordered areas, and echo that request's `request_id`. Apply the same response assembly on cache hits and misses.

Response:

```json
{
  "schema_version": 1,
  "request_id": "…",
  "pack": {"version": "…", "sha256": "…", "release": true, "synthetic_layers": []},
  "parse": {"concepts": [], "negated": [], "demo": [], "unsupported": [], "unknown": [], "confidence": 1.0},
  "abstain": false,
  "counts": {"direct_cells": 0, "partial_cells": 0, "excluded": {"polar": 0}},
  "areas": [{
    "rank": 1, "tile": 0, "cells": [], "best_cell": "HPX128:…", "tier": "Direct",
    "match_mean": 0, "match_best": 0,
    "concepts": {"lake": {"state": "Present", "support": 1.0, "relation": "exact", "status": "catalogue", "flags": []}},
    "records": {"ctx": 0, "hirise": 0, "dtm": 0, "crism": 0},
    "method": "compatible", "sparse": false, "label": "…", "point_features": {"paleolakes": ["OBL-185"]}, "demo": false
  }],
  "heat_nside32": "base64 of 12,288 uint8 values"
}
```

`GET /api/v1/cell/HPX128:<n>` returns the stored record plus that cell's concept states.

Errors: `400 INVALID_REQUEST`, `404 CELL_NOT_FOUND`, `503 RANKING_NOT_CONFIGURED` when no pack is loaded.
</api>

<performance>
Deployment target: a CPU-only Linux server, one process, pack memory-mapped and shared across workers, no GPU, no network at query time.

Budgets (single core, uncached):

| Stage | Budget | Reference measurement |
| --- | --- | --- |
| Parse | < 1 ms | < 0.1 ms |
| Score 3–8 concepts | < 2 ms | 0.28–0.8 ms (integer, NumPy) |
| States, tiers, filters | < 2 ms | bitset AND ≈ 1 µs |
| Tile aggregation | < 2 ms | 0.57 ms for 12,288 tiles |
| Grouping | < 20 ms | 6.5 ms (SciPy) |
| **Total** | **< 50 ms** | about 10 ms |
| Cached repeat | < 1 ms | — |
| Full build | < 5 min | NDJSON parses at about 80,000 rows/s |

Required techniques:

1. Precompute everything that does not depend on the query.
2. Dense `uint8` support matrix in NESTED order. No sparse postings.
3. Integer fixed-point scoring with `uint64` accumulation.
4. Hierarchy and derived concepts folded at build time.
5. Packed bitsets for coverage, filters and gates.
6. Tile aggregation by `reshape(-1, 16)`.
7. Consider max-pyramid pruning only if it preserves grouping, counts, the heat layer, and the first 500 ordered areas. Benchmark it against the unpruned result.
8. Grouping only over Direct cells with the stored neighbour table.
9. `argpartition` for top-k, then a stable sort of the survivors.
10. LRU cache of ranking data keyed by the effective scoring inputs, DEMO policy, and pack digest.
11. Areas and a 12 KB heat layer in the response, never per-cell arrays.
12. One streaming pass over each NDJSON input at build time.
13. Content-addressed per-layer cache keyed by input digest and rule version.

Write `tests/ranking/bench_ranking.py` that reports each stage and fails if a budget is exceeded by more than 2×.

Not worth doing at this size: GPU, a vector database, compressed postings, or a compiled extension.
</performance>

<acceptance>
All must pass in CI before the PR is ready.

| # | Check | Pass condition |
| --- | --- | --- |
| 1 | Input integrity | A changed byte in any input stops the build with a digest error |
| 2 | Verified facts | Every number in `<verified_facts>` and every cell count in `<concepts>` A is reproduced exactly |
| 3 | Determinism | Two builds give identical per-file digests. Responses are byte-identical across runs and across worker processes |
| 4 | Coverage honesty | No cell outside a layer's coverage has support > 0 for that layer's concepts. Catalogue absence is never reported as Absent |
| 5 | Never summed | No API field or sort key combines Match with records, gates or exclusions |
| 6 | Synthetic quarantine | A build with any demo layer and `release: true` fails. Every DEMO-backed result is labelled |
| 7 | Abstention | `purple unicorn` returns `abstain: true` and no areas |
| 8 | Negation | `not volcanic ancient lake sediments` negates only `volcanic` |
| 9 | Broader is not Direct | `clays` with only `hydrated-minerals` evidence is Thematic |
| 10 | Known sites, real data | A Goudge lake cell is Direct for `lake`. Cells along the Cerberus Fossae graben are Direct for `graben`. At least one cell inside the Arcadia Planitia gazetteer bounds (33.9–64.2° N, 165.8–210.4° E) is Direct for `ice-shallow` |
| 11 | Negative controls | No Olympus Mons summit cell (about 18.6° N, 226.2° E) is Direct for `lake`. All 26,568 cells poleward of 60° are *not evaluated* for `ice` |
| 12 | Filters | `--exclude polar` removes 26,653 cells, `--exclude volcanic` removes 42,505 |
| 13 | Sensitivity | Moving each ramp threshold by ±20 % keeps ≥ 80 % of the top-20 areas for each golden objective |
| 14 | Performance | Every budget in `<performance>` |
| 15 | API contract | Strict validation, the three error codes, and schema tests for both endpoints |
| 16 | Cache isolation | Warm the cache with a DEMO-backed query and repeat it with `include_demo: false`. Compare both results with cold runs and confirm the disabled response has no DEMO-backed areas. Repeat a query with the same scoring inputs and different unsupported terms, limits and request IDs. Each response has its own parse report, limit and ID, and the area order matches a cold run. |

Golden objectives (store expected top-20 area IDs after the first reviewed build):
`ancient lakes`, `shallow ice`, `young volcanism and lava flows`, `tectonic grabens`, `chloride deposits in Noachian terrain`, `cave candidates`, `ancient water and delta deposits` (with `include_demo: true`, labelled DEMO).
</acceptance>

<work_order>
Stop and report after each phase. Do not start the next until the report is posted on the PR.

1. **Inputs.** Fetch and verify the four files. Write `tests/ranking/test_inputs.py` with `<verified_facts>`.
2. **Ledger and parser.** `concepts.json`, `lexicon.json`, `ledger.py` with schema validation, `lexicon.py` with tests 7–9.
3. **Layers.** One function per layer in `layers.py`, each returning `(support: uint8[N], covered: bool[N], reported: bool[N] | None, receipt: dict)`. Demo layers last, behind a `--with-demo` flag.
4. **Pack.** `build.py` and `pack.py`. Tests 1–4, 6, 12.
5. **Engine.** Score, states, tiers, filters, gates, grouping, ordering. Tests 9–11, 13. Benchmark.
6. **Service.** Endpoints, cache, detail store. Tests 5, 14–16.
7. **Report.** Final PR description in the format in `<report>`.
</work_order>

<when_blocked>
- A digest does not match: stop and report the expected and actual values.
- A count in `<verified_facts>` does not reproduce: stop, report both numbers and the query you ran.
- A rule in `<concepts>` looks scientifically wrong: implement it as written, add a test documenting current behaviour, and raise it in the report.
- A budget cannot be met: report the measured time per stage and the cause before optimising further.
- Anything requires a new dependency, a change to an existing builder, or a contract change: ask first.
</when_blocked>

<report>
Each phase report, and the final PR description, contains:

1. What was built, with file paths.
2. Tests run and results, with the exact commands.
3. Measured timings per stage against budgets.
4. Every number that differs from this prompt, with both values.
5. Concept status summary: counts per status, and the list of DEMO concepts still in use.
6. Open scientific questions for Isath and data questions for Yumeth.
7. Anything you chose not to do, and why.

Write plainly. Do not claim a check passed unless you ran it.
</report>

---

## Notes for the team

- **Sources of truth.** The prompt reflects `mars-cell-map-v0.2.0`, published at 14:39 today. That release already joins eight catalogues (lakes, chlorides, hydrated-mineral sites, SIM 3292 structures, gazetteer, dunes, caves and marsquakes). The layer table in `BUILD-PLAN.md` predates it. Where they disagree, this prompt is current.
- **What is still demo.** Deltas, fans, valley networks, mineral classes (MOCAAS returned HTTP 410), mid-latitude glacial landforms, magnetism and olivine. The headline objective *ancient water and delta deposits* will therefore rank on real lakes, channels, outflow, ice and age, plus DEMO deltas only when `include_demo` is true.
- **Draft thresholds needing Isath's review.** Structure length 10 km for full support, gazetteer bounds fraction 0.5, the 0.6 weight for mixed-age units, the derived `habitability` rule, and the flagged unit readings for `glacial-apron` and `mass-wasting`.
- **Server.** The budgets assume one CPU core. The pack is about 20 MB and memory-mapped, so several workers share one copy.
