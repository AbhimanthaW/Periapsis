# Stage 1 correction acceptance · 0.1.1

**PASS for the corrected Stage 1 MOLA handoff. BLOCKED for regional pack/runtime acceptance.** The original delivery is preserved. This copy includes the unchanged PDS files, a new source-record v2 and its exact SHA-256 receipt.

| Finding | Before, reproduced on 0.1.0 | After, verified on 0.1.1 | Status |
|---|---|---|---|
| H1 · Spatial metadata | A 350° east label bound, wrong configured frame, wrong longitude domain and wrong vertical reference were accepted. A same-radius CRS with a 10° prime meridian passed. | Product adapter rejects independent config/label conflicts and checks the decoded conversion and affine against an analytical MEG004 grid. CRS validation rejects nonzero meridians and unsupported axes. Transform rejects unmatched datums. | **PASS** for the supported adapter and tested CRS operations |
| H2 · Offline record integrity | Editing cached vertical-reference metadata while leaving source bytes intact was accepted. | v2 validates a canonical record digest and the expected spec/member pins, then recomputes the scientific interpretation from verified bytes. A recomputed embedded digest cannot make altered scientific metadata pass. An independently trusted exact-record receipt also detects rehashed retrieval-metadata changes. | **PASS** with the stated trust boundaries |
| H3 · Count companion | Altered count-frame metadata was accepted. An aligned raster with raw counts `[0, 1]`, metre units and a +1 offset was interpreted as one observed bin. | Adapter checks the matching product and frame, grid, byte/axis encoding, count declaration, scale, offset and mask/nodata policy. Regressions reject conflicting frame, units, scale, offsets, order, byte type and zero/positive nodata. | **PASS** for the supported MOLA companion |
| Verified HTTPS and reproducibility | Fresh CLI acquisition failed certificate verification on the audit Mac. Native GDAL/PROJ versions were absent. | Fresh installed CLI acquired all eight pinned PDS members via verified HTTPS using native trust. Certificate and hostname verification stay enabled, and downgrade attempts fail. Record captures GDAL and both PROJ versions. | **PASS** on the tested macOS environment |
| Valid zero | Legacy header says to ignore zero. PDS4 already provided the appropriate mask for this source. | Strict XML adapter verified no nodata and all 147 zero elevation cells valid. Independent control compares the full decoded arrays to raw big-endian Int16 samples. | **PASS** |
| H4 · Pack and loader contract | Blueprint only in the supplied tree. | Requirements and open interfaces documented in [Stage 2 checklist](STAGE2_HANDOFF.md). | **BLOCKED** pending the real consumer and shared fixture |

This report describes the original corrected delivery. See the [monorepo setup](../../docs/development.md#mola-ingestion) for the external data layout.

## Reproduce and inspect

- Baseline tests ran against the untouched delivery with `python -m unittest discover -s tests -q`. **38/38** passed even though the reproduced H1–H3 inputs were accepted. The negative controls used copies of the real labels and a two-cell GeoTIFF.
- Corrected tests ran the same suite plus **10** regression tests, **48/48** passed. The original checksum test now checks the correctly named pin-verification field. Label-policy tests repin deliberately contradictory copies so a checksum failure alone cannot pass the test.
- Clean installed CLI verified fresh HTTPS acquisition, eight archive pins, bundled offline reuse, exact-record receipt, and coordinate normalization. The independent script checked both 720 × 1440 arrays, four coordinate controls per array, **1,036,800** valid elevation samples, **1,027,663** positive count bins, **9,137** zero bins, and **0** missing count bins. See [independent measurements](../../evidence/mola/mola-independent-check.json) and the [exact record receipt](../../evidence/mola/mola-record.sha256).
- Tested environment was macOS ARM64, Python 3.11.17, Rasterio 1.4.4 with GDAL 3.10.3 and PROJ 9.7.1, pyproj 3.7.2 with PROJ 9.5.1, and truststore 0.10.5. See [reproduction commands](../../docs/development.md#mola-ingestion).
- Architecture `check:data` and `check:atlas` passed against the supplied baseline. The documentation engine's locked suite passed **47/47** on a fresh copy. Its Jezero query rejected the 2 m elevation posting requirement and accepted the 20 m elevation fallback. This establishes an evidence contract check. No Stage 1 runtime pack or terrain processing was added.

## Remaining limits

The supplied MEG004 labels and the eight independently retrieved files define the qualified input scope. Generic GeoTIFF inspection leaves configured frame and vertical reference unverified. A new product or different encoding requires its own policy and controls. Native trust, dependency wheels and reader interpretation must be checked on additional platforms. The optional full-record receipt depends on a trusted copy outside the mutable cache. Archive hashes are reviewed content pins. They carry no publisher signature.

MOLA elevation validity includes interpolated cells and count coverage does not establish feature accuracy. No regional gradient, slope mask, terrain co-registration, pack loading, or tactical suitability is asserted. Formal G1–G10 release statuses remain `Not evaluated`.

[NASA PDS maintained product archive](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
