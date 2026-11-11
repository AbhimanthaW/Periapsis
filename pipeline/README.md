# Return Window Stage 1 · corrected handoff

Version **0.1.1** prepares pinned source bytes and spatial metadata. The bundled source is the NASA PDS MOLA MEG004 1.1 topography and companion observation-count pair. The pipeline emits source records. Regional terrain, evidence packages, mission loading and route eligibility are later deliverables.

- [Acceptance and change report](STAGE1_RESULTS.md)
- [Stage 2 producer/consumer checklist](STAGE2_HANDOFF.md)
- [Independent raster and coordinate controls](reports/mola-independent-check.json)

## Install and verify

Use Python 3.11 or later. The corrected release was exercised on macOS ARM64 with Python 3.11.17 and the supplied runtime dependency pins. Windows was exercised for the original delivery. Rerun this workflow on the handoff machine before relying on it.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/return-window verify-cache --workspace data
shasum -a 256 -c reports/mola-record.sha256
receipt=$(cut -d ' ' -f 1 reports/mola-record.sha256)
.venv/bin/return-window ingest configs/mola-global-4ppd-topography.json --workspace data --offline --expected-record-sha256 "$receipt"
.venv/bin/python scripts/check-mola.py
.venv/bin/return-window normalize-position configs/mola-global-4ppd-topography.json --longitude 350 --latitude 18
```

On Windows, use `py -3.11 -m venv .venv`, then use `.venv\Scripts\python.exe` and `.venv\Scripts\return-window.exe` in place of the executable paths above. Read the first token of `reports/mola-record.sha256` for the receipt argument and use `Get-FileHash -Algorithm SHA256` on the listed registry path for an independent file check. Dependency installation requires a package index or a prepared wheel cache. Source verification and reuse run offline once dependencies are installed.

To re-acquire and verify the live archive, choose an empty workspace outside the bundled fixture:

```sh
rw_verify_dir=$(mktemp -d)
.venv/bin/return-window ingest configs/mola-global-4ppd-topography.json --workspace "$rw_verify_dir"
.venv/bin/return-window verify-cache --workspace "$rw_verify_dir"
.venv/bin/return-window ingest configs/mola-global-4ppd-topography.json --workspace "$rw_verify_dir" --offline
.venv/bin/python scripts/check-mola.py --workspace "$rw_verify_dir"
```

HTTPS uses native system trust with certificate and hostname verification. To use an additional reviewed CA, set `SSL_CERT_FILE` to the PEM file. HTTP redirects are rejected. A fresh acquisition receives new retrieval provenance and a new record receipt. For the shipped exact receipt, use the bundled registry record.

## Supported inputs

- **PDS4 MEG004 1.1.** The adapter qualifies the supplied MOLA elevation and count products. It checks the product IDs, frame, spatial conventions, native grid, encoding, units, and product-specific vertical/count semantics against their maintained PDS4 labels. It reads through the XML entrypoints. The preserved PDS3 and ENVI files are lineage attachments. Applying the ENVI zero ignore flag would drop valid elevations.
- **Unlabeled GeoTIFF.** Local and HTTPS acquisition and raster inspection remain available. Supply the reference and vertical unit/datum explicitly, and include external masks or georeferencing sidecars. Geographic extents must fit the declared domain. A generic input's datum and frame remain configured assertions. A product-specific adapter or equivalent independent validation is needed before a regional model may consume it as qualified terrain.
- **Coordinates.** Position normalization still supports west-to-east and planetographic-to-planetocentric conversion as explicit operations. CRS operations require a zero reference meridian, conventional geographic axes, and a shared geodetic datum. Unsupported cross-frame and non-spherical planetocentric CRS operations fail explicitly.

The configured member SHA-256 values pin independently fetched archive bytes. They are review pins with archive provenance. The record field `checksum_pin_verified` represents agreement with the input pin.

## Record compatibility and trust

Source config schema v1, CLI command names, Python `ingest` tuple, the source bundle layout, and original MOLA bytes remain compatible. Registry records now require **source record schema v2**. Use the included v2 record or re-ingest with the revised config into a fresh workspace. Keep the old record for history. Code reading the old `publisher_checksum_verified` field must use `checksum_pin_verified` with its corrected semantics. The new record adds an interpretation digest, product diagnostics, separate zero and missing count totals, and native GDAL/PROJ versions.

Use the config from a trusted checkout and pass `--expected-record-sha256` from a trusted receipt when verifying an exact handoff. `verify-cache` checks internal consistency using each record's embedded spec. `ingest --offline` additionally checks against the supplied spec and re-derives the scientific interpretation from the checked bytes. The independent receipt also detects deliberate edits to retrieval bookkeeping followed by recomputing the embedded digest. Keep that receipt outside the writable cache when guarding against intentional changes. Reinspection may reject records produced by readers that serialize or interpret the data differently. In that case, make a fresh reviewed record under the target environment instead of editing the cached interpretation.

All formal G1–G10 regional release gates and capabilities remain **Not evaluated**. Full-band validity and positive count bins measure different properties. MOLA MEG004 is planetary elevation context.

[Maintained NASA PDS MOLA archive](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
