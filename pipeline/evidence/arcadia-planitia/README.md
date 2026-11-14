# Arcadia Planitia evidence handoff

**Candidate for team review.** Periapsis region `03`, centred at 171.85°W, 49.02°N. The evidence query covers a roughly 4 × 4 km area near that catalog point. The area of interest is a working selection for this demo. [Periapsis region catalog](https://github.com/AbhimanthaW/Periapsis/blob/0a9f2ecc705a96625d79980c801bcb44bc64f289/web/src/atlas/regions.json) · [IAU/USGS Gazetteer](https://planetarynames.wr.usgs.gov/Feature/348)

## Crew decision

**Objective:** Record broad elevation context for the selected area and determine whether the supplied products can support a local 20 m-posted elevation calculation. The expected artifact is an elevation context map with the evidence status. Use the MOLA context layer for orientation and request a verified local DTM before running the finer calculation.

- **Supported:** Coarse MOLA elevation context. The central cell is −4,036 m relative to the MOLA areoid and has 555 recorded observations. The cropped display uses 121 valid native cells at 0.25° spacing. Its enlarged pixels retain the original grid values. [NASA PDS MOLA archive](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
- **Refused:** Local 20 m-posted stereo elevation. The sidecar contains no qualified stereo DTM for the Arcadia query. The same acquisition search bounds formula and USGS collection returned 0 intersecting records at the candidate and 24 catalog matches at the well-studied Jezero control. The control query uses the repo’s already verified 20 m CTX product. Catalog matches indicate discovery; usable pixels and effective feature scale need separate checks. [USGS CTX DTM collection documentation](https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/)

The catalog searches were captured on 14 November 2026. The result is limited to the saved search, collection, and selected bounds. MOLA elevation values can include interpolation. The observation count measures sampling support. Tactical terrain and local slope remain unqualified.

## Files

| File | Purpose |
| --- | --- |
| `source-manifest.json`, `source-config.json`, `source-record.json` | Archive asset ID and version, original checksums, configuration, attribution, native CRS and vertical datum. |
| `evidence.json`, `evidence-query.json` | Evidence sidecar v1 and the Arcadia capability query. |
| `control-query.json` | Same calculation and fallback, with the matched search bounds at the existing Jezero control. |
| `arcadia-mola-context.png`, `arcadia-mola-elevation.i16le`, `display-metadata.json` | Offline context image, exact signed elevation samples, bounds, affine reference, and mask summary. |
| `catalog-search/`, `verification.json`, `SHA256SUMS.txt` | Saved USGS search results, resolver and API verification, and exact file hashes. |
| `build_arcadia_handoff.py`, `verify_handoff.py` | Rebuild and schema/decision verification scripts. |

## Rebuild and verify

From a Periapsis checkout containing the merged Phase 3 atlas tools, install the pipeline dependencies and prepare the pinned MOLA cache using the pipeline README. Supply the built atlas directory, the catalog from the repo, and the saved catalog search folder. Write to a new output directory. [Pipeline instructions](https://github.com/AbhimanthaW/Periapsis/blob/0a9f2ecc705a96625d79980c801bcb44bc64f289/pipeline/README.md)

```text
python build_arcadia_handoff.py --atlas <atlas-directory> --workspace <MOLA-cache> --source-config <repo>/pipeline/configs/mola-global-4ppd-topography.json --regions <repo>/web/src/atlas/regions.json --search catalog-search --output <new-directory>
```

With the repository’s documentation dependencies installed, from the repository root on `main`:

```text
uv run --project documentation --locked --offline python <handoff>/verify_handoff.py <handoff> --repo .
uv run --project documentation --locked --offline python -m runtime.planning_api --evidence-package <handoff>/evidence.json --evidence-query <handoff>/evidence-query.json
```

The API’s `GET /api/v1/evidence` exposes the result as operator-configured evidence. Isath should review the science objective and scope. Abhimantha should approve the candidate before it is added to the mission site registry. Browser integration and disconnected second-machine acceptance are pending.
