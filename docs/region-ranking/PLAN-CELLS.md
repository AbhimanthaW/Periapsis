# Plan: objective ranking over the 196,608 cell records

**Periapsis · Workstream B · 14 November 2026, Colombo**

**Verdict.** The cell records are structured measurements, not survey text. Each cell has one geologic unit, thermal inertia, albedo, ice consistency, elevation and image-catalogue counts. The ranking model therefore becomes a set of reviewed rules that turn those fields into concepts, scored with dense arrays in the local Python service. 25 concepts pass on the current data, 3 pass with a flag, and 26 cannot be supported until more layers are joined. The largest gap is water history: the records hold nothing on deltas, lakes, rivers or alteration minerals, so *ancient water and delta deposits* cannot be answered from cells yet.

This replaces the earlier 200k plan, which assumed text records. Parser, tiers and never-summed criteria carry over from the [design](README.md).

[Concept decisions](cell-concepts-v1-draft.json) · [Profile scripts](cell-profile/)

## What the records contain

Profiled file: `cells-enriched.ndjson.gz` from release `mars-cell-map-v0.1.0`, SHA-256 `d5c0d6a7…` (matches the manifest), 196,608 rows, 543 MB uncompressed, one identical key set in every row.

| Field | Coverage | What it can support |
| --- | --- | --- |
| SIM 3292 geologic unit at centroid | 196,368 cells (99.88 %), 44 units in 8 groups, 4 cells with two units | Age, terrain type, volcanism, outflow, polar, apron |
| TES night thermal inertia | 181,782 measured, 14,577 interpolated, 249 no sample | Rocky, dust-mantled and coarse surfaces |
| TES Lambert albedo | 196,608 | Only together with thermal inertia |
| SWIM ice consistency, three depths | 170,040, null poleward of 59.7° | Ice |
| MOLA elevation and count | 196,608 (71 cells with zero observations) | Elevation bands |
| CTX record count | 196,367 cells above zero, median 4 | Records column |
| HiRISE, HiRISE DTM, CRISM products | 7,425, 114 and 1,962 cells | Records column |
| TES dust, one window in 2000 | 184,760 | Context only |
| Documentation tiers (`marsdoc`) | All 196,608 Unclassified | Nothing yet |
| Named feature anchors | 56 cells | Labels only |

The eight unit groups cover Highland 86,397 cells, Volcanic 42,505, Lowland 25,776, Transition 18,972, Impact 10,732, Polar 6,403, Basin 3,325 and Apron 2,258.

## Concept decisions

Decided under the delegated approval. Full rules, forms and cell counts are in the JSON ledger.

**Passed (25).** Ages: Noachian, Hesperian, Amazonian. Terrain: highland, massif, lowland, transition, basin, impact. Water-related: outflow. Volcanic: volcanic, edifice, field, young volcanic. Polar: deposits, cap, dunes. Ice: ice, shallow ice, deep ice. Surface: rocky, dust-mantled, dark coarse. Elevation: low, high.

**Passed with a flag (3).**
- *Glacial apron* (units ANa and lAa, 901 cells). ANa lies at 37–49° latitude, where debris aprons occur. Confirm the glacial reading in the SIM 3292 unit text.
- *Mass wasting* (unit Aa, 1,357 cells, around Olympus Mons and Valles Marineris). Confirm in the same source.
- *Water*. It has no layer of its own. It is supported only through outflow and ice.

**Not passed, no layer (26).**

| Concepts | Layer that would unlock them |
| --- | --- |
| delta, alluvial fan, lake, river, valley network, inverted channel | Valley-network map and a delta and paleolake catalogue |
| clays, sulfates, carbonates, chlorides, silica, olivine, hydrated minerals, alteration, mineralogy | Mineral-detection catalogue with mineral classes |
| tectonic, canyon, chaos, periglacial, layered deposits, lava tube | Gazetteer feature footprints or SIM 3292 structure lines |
| seismic, magnetism, geophysics | Magnetic field map, marsquake locations |
| habitability, stratigraphy, sedimentary, groundwater, hydrothermal, climate, ocean | Reviewed combination rules or curated site lists |

The parser still recognises these words. It reports them as *no cell data yet* and ranks on the rest.

**Rejected uses (7).** CRISM product presence as mineral evidence (it is coverage, not detection). The single TES dust window as dust activity. Albedo alone as composition. The `marsdoc` tiers as a ranking. Image counts as science interest. Named anchors as region evidence. Interpolated thermal inertia as a measurement.

## Sparse threshold

- **No metadata: 0 cells.** Every record has elevation and albedo.
- **Sparse: 3,304 cells (1.68 %).** Rule: no geologic unit, or neither a measured thermal-inertia sample nor a SWIM value. Median latitude of these cells is 69°.
- Of three concept-bearing layers (geology, measured thermal inertia, SWIM), 158,117 cells have all three, 35,372 have two, 3,095 have one and 24 have none.
- Each concept also carries an *evaluated* mask. A cell outside a layer is not evaluated for that concept and never scores zero. Ice is not evaluated for 26,568 polar cells, and 6,318 of the 6,403 polar-unit cells fall there.
- 240 cells have no unit because the centroid misses every polygon. 229 of them touch a mapped neighbour. Fix this in `build_science.py` with a nearest-polygon tolerance. Do not infer units from neighbours at query time.

## Grouping

- Neighbouring cells are strongly alike. Neighbour correlation is 0.99 for elevation, 0.98 for albedo, 0.96 for SWIM and 0.67 for thermal inertia. 85 % of neighbour pairs share a geologic unit.
- Same-unit probability falls with distance: 0.82 at 42 km, 0.70 at 79 km, 0.59 at 136 km, 0.46 at 259 km.
- Raw matches therefore form huge blobs. Noachian-only cells form one patch of 84,575 cells. A test objective (ice consistency above 0.25 in Noachian units) matched 22,182 cells in 1,897 patches, the largest 12,495 cells.
- **Rule.** Join matching cells with 8-neighbour connectivity, then split each patch at Nside-32 parent tiles (16 cells, about 108 km across). The test objective becomes 3,964 areas, 600 of them full tiles. 8-neighbour is chosen because 4-neighbour leaves 297 single-cell unit patches against 21.
- CRISM, HiRISE and DTM hits are points: 1,401 of 1,621 CRISM clusters are single cells. Attach them to areas. Do not group them.
- Use `astropy_healpix` exact neighbours, already a pinned dependency. The profile used a nearest-centroid approximation.

## Model

1. **Concept matrix, built offline.** One `uint8` support array and one evaluated bitmask per concept, in nested order. About 30 concepts × 196,608 cells is 6 MB as `.npy`, memory-mapped by the service. Support is graded where the source is graded: ice rises from 0 at SWIM 0 to 1 at 0.5, rocky from 350 to 500 tiu, mixed-age units count 0.6.
2. **Parse.** Same rule-based parser. Forms map to the passed concepts. Unsupported and unknown words are reported separately.
3. **Score.** `Match(cell) = Σ weight(q) · idf(q) · support(q, cell)`, with idf from cell counts. Cells are equal-area, so rarity is area. Age keeps weight 0.35. The test query scored all cells in 2 ms.
4. **Tier.** Direct when every supported concept has support of at least 0.5, Partial for some, Not evaluated when a needed layer is missing.
5. **Filter and gate.** Polar exclusion: latitude of 60° or more, or a polar unit (26,653 cells). Volcanic exclusion: volcanic unit group (42,505 cells). Method gates use rocky and ice support as listed in the ledger.
6. **Group and rank.** Areas by the rule above, ordered by tier, mean Match, cell count, then lowest cell ID.
7. **Separate columns.** Records shows CTX count, HiRISE, DTM and CRISM presence. 8,655 cells (4.4 %) have any targeted product. Traversal stays with the route model. Nothing is summed.
8. **Less-documented shortlist.** Direct match, no targeted product and at most two CTX records. The test objective leaves 5,533 such cells.

## Work plan

| Step | Work | Size |
| --- | --- | --- |
| 1 | Confirm the two flagged unit readings in SIM 3292. Fix the 240 unit gaps in the build. | Half a day |
| 2 | Write `build_concepts.py`: records → concept matrix, masks, idf table, manifest with input digests. | Half a day |
| 3 | Port the parser and scorer into the Python service behind `POST /api/v1/rank`. Return the parse report, areas, tiers and per-concept support. | One day |
| 4 | Join the missing layers, in order: mineral detections, valley networks and deltas, gazetteer footprints. Each adds concepts through the same ledger. | One day each |
| 5 | Tests: digest pinning, determinism, ±20 % threshold sensitivity, about 25 objectives with expected areas. | Ongoing |

## Decisions for Abhimantha

1. Whether to join the water and mineral layers before the event build. Without them the Explore example objective cannot rank.
2. Whether polar exclusion at 60° is acceptable. It matches the SWIM limit.
3. Whether the Nside-32 area size suits the Explore globe, or Nside 16 reads better.

## Reproduce

```sh
python3 -I docs/region-ranking/cell-profile/load.py cells-enriched.ndjson.gz cells.pkl
python3 -I docs/region-ranking/cell-profile/profile.py cells.pkl neigh.pkl
python3 -I docs/region-ranking/cell-profile/concepts.py cells.pkl neigh.pkl
```

Needs NumPy and SciPy. The scripts read the release file and write only the two cache files named on the command line.
