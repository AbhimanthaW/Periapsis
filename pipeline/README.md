# Return Window data pipeline

## Corrected MOLA Stage 1

Run the [monorepo setup and validation commands](../docs/development.md#mola-ingestion).
The source registry and reviewed results are under [evidence/mola](../evidence/mola).

The existing Stage 1 API and source record v2 are unchanged. The external workspace replaces the original bundled data directory. See [original results](STAGE1_RESULTS.md) and the [Stage 2 handoff](STAGE2_HANDOFF.md).

## Stage 2 terrain producer draft

The terrain producer builds a provisional western Jezero elevation GeoTIFF from a checksum-pinned USGS CTX TRN mosaic. The configured crop uses the native 20 m grid and keeps the source vertical reference. The engine calculates slope and aspect with a buffered native stencil before coarsening and preserves elevation validity and gradient support.

The `build-preview` command writes a producer-only `site.json` and GeoTIFF. The [mission pack v1 loader](../contracts/README.md) accepts the separately pinned Float32 Jezero window built by `scripts/build_jezero_preview.py`. Use that workflow for the runtime preview. The new crop's formal release gates remain unevaluated.

From `pipeline/`, after setting up the environment as described above, use these PowerShell commands to acquire the raster once and then build and verify the draft offline. Keep the cache and generated pack in your external workspace.

```powershell
$work = Join-Path $env:TEMP "return-window-stage2"
.\.venv\Scripts\return-window.exe ingest configs\jezero-ctx-trn-dtm-20m.json --workspace "$work\data"
.\.venv\Scripts\return-window.exe build-preview configs\jezero-west-preview.json --workspace "$work\data" --output "$work\jezero-preview"
.\.venv\Scripts\return-window.exe verify-preview "$work\jezero-preview"
```

Choose a new output directory for each rebuild. See the [Windows verification report](reports/stage2-verification.json) and the [USGS data release](https://www.usgs.gov/data/mars-2020-terrain-relative-navigation-ctx-dtm-mosaic).

## Stage 3 whole-Mars validation

Use the MOLA MEG004 global elevation and observation-count grids as the planet-wide source. The atlas covers all longitudes and latitudes at the native 4 pixels per degree. Both GeoTIFF layers use east-positive longitude from −180° to 180°, with the native samples reordered to match the atlas map and no resampling. The manifest records source identity, grid, coverage and artifact checksums. The region index uses every entry in the uploaded [Periapsis region catalog](../reference/engineering-workspace/src/atlas/regions.json), preserving its ID, name and point. Each entry reports the MOLA elevation and observation count for the cell containing that point. The catalog provides Gazetteer centers and representative anchors, so these samples describe point locations.

Run these PowerShell commands from `pipeline/` after installing the pipeline. The first command prepares the source cache. The last two run offline.

```powershell
$work = Join-Path $env:TEMP "return-window-whole-mars"
.\.venv\Scripts\return-window.exe ingest configs\mola-global-4ppd-topography.json --workspace "$work\data"
.\.venv\Scripts\return-window.exe build-global-atlas configs\mola-global-4ppd-topography.json --workspace "$work\data" --output "$work\atlas" --regions ..\reference\engineering-workspace\src\atlas\regions.json
.\.venv\Scripts\return-window.exe validate-global-atlas configs\mola-global-4ppd-topography.json --workspace "$work\data" --directory "$work\atlas" --regions ..\reference\engineering-workspace\src\atlas\regions.json
```

Choose a new output directory for each rebuild. Validation checks the pinned source, manifest, hashes, projection, bounds, every elevation and observation-count cell, and every region index entry against the supplied catalog. A zero observation count is distinct from a missing value. The atlas provides coarse elevation and sampling context. Browser tile integration and formal atlas release acceptance are pending.
