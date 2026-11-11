# Validation and performance

## Software and integration

**47 automated checks passed.** Unit coverage includes grid counts and IDs, centroid round trips, Mars latitude/longitude conversions, deterministic seam and pole handling, overlapping and partial coverage, duplicates, malformed topology, missing CRS and footprints, scoped catalogue absence, readiness, provenance, score intervals, tier equality and sensitivity. Capability tests cover imagery without DTM, independent resolution and time requirements, a single compatible support set, partial route coverage, and explicit fallbacks.

Integration tests validate all five generated JSON schemas, run the public CLI, and exercise the schema-backed Jezero sidecar, score and corridor against the existing Atlas region registry. The unchanged architecture checks also passed with `npm run check:data`, `npm run check:atlas` and `npm run build`. The Atlas validated 56 regions, and the blueprint validated 152 components and 319 connections. The build emitted its module-directive and bundle-size warnings. The existing dependency audit reported three advisories.

## Archive verification

The packaged fixture comes from the USGS Mars 2020 Science Investigation CTX DEM mosaic. The verifier read source rows 1978–3001 and columns 732–1755, checked the 20 m posting, affine origin, Mars 2000 sphere, prime meridian and nodata mask, and compared every little-endian Float32 value to the prepared Jezero terrain file. **All 1,048,576 source samples matched, with zero masked cells.** The fixture represents the checked support inset one source posting from the window boundary, with densified edges transformed through the source WKT. Its provenance stores both the elevation-window and prepared-manifest SHA-256 digests. [USGS product catalogue](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic) · [USGS source raster](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif)

Recreate the fixture from the original neighboring team bundle and the live source:

```sh
uv run --locked --group archive-check python -m examples.verify_jezero \
  "../../Yumeth Martian Map/data" > /tmp/jezero-evidence-check.json
cmp /tmp/jezero-evidence-check.json examples/jezero-evidence.json
```

The example is a proof of one regional elevation contract. Global evidence coverage, other source product classes, feature-scale validity and route model release gates remain unverified.

## Scientific and numerical controls

- Total exact spherical area equals `4πR²` across the tested grid resolutions. Centroid-to-cell round trips and exact pole coordinate normalization are checked independently of geometry.
- Spherical overlay area matches an analytic polar triangle using L'Huilier's formula. A symmetry case has exactly half the query area inside the footprint. An oblique line with overlapping observations preserves the same unique length.
- Six representative cells per grid cover equatorial, midlatitude, Jezero, near-seam and both pole cases. For an intersecting test footprint at each cell, compare the configured 16 samples per edge to a 256-sample refinement.

| Maximum across six cases | Nside 64 | Nside 128 |
| --- | ---: | ---: |
| Relative polygon area error versus exact cell area, step 16 | 0.04678% | 0.04680% |
| Relative polygon area error versus exact cell area, step 256 | 0.000183% | 0.000183% |
| Absolute coverage change between step 16 and 256 | 0.00115 percentage points | 0.00156 percentage points |

The measured deviations describe these cases. Grazing or much smaller footprints and unusual edges can have different errors. Scoring intervals quantify evidence availability under the chosen boundary approximation. The exact HEALPix cell area, its chord approximation, and footprint positional uncertainty are separate. Modality weights, spacing ramps and tiers are engineering policy and still need scientific validation.

## Benchmark

Measured on an Apple M1 Pro with 16 GiB RAM, Python 3.12.15 and the locked dependencies. Each row is a median of three runs within a fresh process for that Nside, except the Jezero route median of 11. Both levels used 384 simulated overlapping swaths across six regions, including seam and higher-latitude subsets. The 256 distinct regional cells per level were sampled from the same seeded workflow. Their footprint intersections differ with cell size and sample positions. Only the single Jezero route uses archive-verified source support.

| Operation | Nside 64 | Nside 128 |
| --- | ---: | ---: |
| Total grid cells | 49,152 | 196,608 |
| All centroid coordinates | 3.79 ms | 13.82 ms |
| Batch 100,000 coordinate lookups | 12.08 ms | 12.00 ms |
| Build 384-footprint index | 29.09 ms | 28.87 ms |
| Generate boundaries for 256 cells | 1.36 ms | 1.07 ms |
| Build 256 local charts | 83.18 ms | 82.91 ms |
| Intersect indexed footprints with 256 cells | 36.81 ms | 19.08 ms |
| Positive product/cell intersections | 540 | 217 |
| Union partial coverage and score 256 matched cells | 73.18 ms | 47.44 ms |
| End-to-end 256 cell summaries | 235.37 ms | 183.10 ms |
| Serialize 256 full cell summaries | 5.28 ms | 4.18 ms |
| Cell JSONL bytes (gzip bytes) | 1,666,323 (69,799) | 1,132,546 (43,528) |
| All centroids as Float64 array | 786,432 B | 3,145,728 B |
| Buffer and resolve 128 synthetic routes | 159.35 ms | 151.67 ms |
| Resolve the verified Jezero route | 0.76 ms | 0.75 ms |
| Process peak resident memory, including interpreter | 121.78 MiB | 131.38 MiB |

Nside 128 is viable for this query workload. Its smaller cells matched fewer products in the selected sample, so the lower subset time cannot establish relative whole-planet throughput. Runtime and memory will depend on catalogue size, footprint complexity, the number of unresolved products, overlap and provenance volume. The engine indexes bounding caps and generates cell boundaries lazily. A production Atlas should store compact cell summaries with references to a shared provenance table instead of repeating full footprint geometry in each display record.

Reproduce with `uv run --locked python -m examples.benchmark 64` and again with `128`. Raw results are in [Nside 64](examples/benchmark-nside64.json) and [Nside 128](examples/benchmark-nside128.json).

## Acceptance and dependencies

| Scope | Verified status |
| --- | --- |
| Mars coordinate and indexing foundation | Deterministic coordinate, count, IDs, area and hierarchy controls pass |
| Footprint math and scoring | Spherical partial/overlap cases, readiness, interval and classification tests pass |
| Independence from traversal and interest | The resolver consumes product evidence and requirements. Scores have no route-cost output |
| Reproducible pipeline interface | Generated schemas, checksums, quarantine and archive-checked demo pass. Production producer adoption pending |
| Integration with Return Window | Blueprint and Atlas smoke checks pass. Live pack-loader and UI integration pending |
| Planetary evidence release | Production catalogues, scope attestations and full-run coverage have yet to be processed |
