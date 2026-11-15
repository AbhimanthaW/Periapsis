# Return Window data pipeline

## Corrected MOLA Stage 1

Run the [monorepo setup and validation commands](../docs/development.md#mola-ingestion).
The source registry and reviewed results are under [evidence/mola](../evidence/mola).

The existing Stage 1 API and source record v2 are unchanged. The external workspace replaces the original bundled data directory. See [original results](../reference/pipeline/STAGE1_RESULTS.md) and the [Stage 2 handoff](../reference/pipeline/STAGE2_HANDOFF.md).

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

Use the MOLA MEG004 global elevation and observation-count grids as the planet-wide source. The atlas covers all longitudes and latitudes at the native 4 pixels per degree. Both GeoTIFF layers use east-positive longitude from −180° to 180°, with the native samples reordered to match the atlas map and no resampling. The manifest records source identity, grid, coverage and artifact checksums. The region index uses every entry in the uploaded [Periapsis region catalog](../web/src/atlas/regions.json), preserving its ID, name and point. Each entry reports the MOLA elevation and observation count for the cell containing that point. The catalog provides Gazetteer centers and representative anchors, so these samples describe point locations.

Run these PowerShell commands from `pipeline/` after installing the pipeline. The first command prepares the source cache. The last two run offline.

```powershell
$work = Join-Path $env:TEMP "return-window-whole-mars"
.\.venv\Scripts\return-window.exe ingest configs\mola-global-4ppd-topography.json --workspace "$work\data"
.\.venv\Scripts\return-window.exe build-global-atlas configs\mola-global-4ppd-topography.json --workspace "$work\data" --output "$work\atlas" --regions ..\web\src\atlas\regions.json
.\.venv\Scripts\return-window.exe validate-global-atlas configs\mola-global-4ppd-topography.json --workspace "$work\data" --directory "$work\atlas" --regions ..\web\src\atlas\regions.json
```

Choose a new output directory for each rebuild. Validation checks the pinned source, manifest, hashes, projection, bounds, every elevation and observation-count cell, and every region index entry against the supplied catalog. A zero observation count is distinct from a missing value. The atlas provides coarse elevation and sampling context. Browser tile integration and formal atlas release acceptance are pending.

## Stage 4 atlas release candidates

The local registry stores each candidate at `<registry>/mars-mola-meg004/<version>/`. Run these PowerShell commands from `pipeline/` after preparing the MOLA cache above.

```powershell
$repo = git rev-parse --show-toplevel
$catalogPaths = @(git -C "$repo" ls-files -- web/src/atlas/regions.json reference/engineering-workspace/src/atlas/regions.json evidence/regions/regions.json)
if ($LASTEXITCODE -ne 0 -or $catalogPaths.Count -ne 1) { throw "Expected one tracked Periapsis region catalog" }
$regions = Join-Path $repo ($catalogPaths[0])
.\.venv\Scripts\return-window.exe build-atlas-release configs\mola-global-4ppd-topography.json --regions "$regions" --workspace "$work\data" --registry "$work\registry" --version 0.1.0-rc.1
.\.venv\Scripts\return-window.exe verify-atlas-release configs\mola-global-4ppd-topography.json --regions "$regions" --workspace "$work\data" --registry "$work\registry" --version 0.1.0-rc.1
```

Each candidate contains the global GeoTIFFs, point index, atlas manifest, exact source configuration and region catalog, and a release manifest with file receipts, software versions and offline validation status. Use the source configuration and catalog from a trusted checkout when verifying. Verification compares the packaged inputs with that checkout, then checks all raster cells and catalog entries against the pinned MOLA source. Builds reject an existing release version. To reproduce a version, use the same inputs and software in an empty registry.

The software versions are producer-reported. For a release handoff, record the builder commit and the SHA-256 of the original `release-manifest.json` separately from the candidate. Pass that trusted lowercase digest to `verify-atlas-release --expected-manifest-sha256 <digest>` in addition to the arguments above to check the exact manifest, including the recorded software versions.

Candidates record browser runtime compatibility (G10) as unevaluated until the Atlas consumes the package offline.

## Dust outlook (MDAD storm masks)

The Explore region panel shows a dust outlook for each region: the historical chance that a mapped dust storm covers the configured share of observed pixels in the region's 100 km core disc within the next 7 sols, by season, and a model estimate for a quiet week and for a storm in the surrounding 800 km ring. The model is a numpy logistic regression on the seasonal baseline plus current and recent storm coverage. It is validated leave-one-Mars-year-out. The browser shows model values only when pooled Brier skill over the baseline is at least 0.02 and positive in most held-out years; otherwise it shows the baseline and says the model was withheld. The record ends at MY32, so this is not a live forecast.

Source: [MDAD v1.1](https://doi.org/10.5281/zenodo.7480334), MY28–32. Download the five `MYxx.tar.gz` files and extract each into its own folder, for example `MY28/`. Install the extra with `pip install -e ".[dust]"`. Then run from `pipeline/`:

```powershell
$work = Join-Path $env:TEMP "return-window-dust"
.\.venv\Scripts\python.exe -m return_window_pipeline.dust inspect "$work\MY29"
.\.venv\Scripts\python.exe -m return_window_pipeline.dust extract "$work\MY28" "$work\MY29" "$work\MY30" "$work\MY31" "$work\MY32" --regions ..\web\src\atlas\regions.json --output "$work\series"
.\.venv\Scripts\python.exe -m return_window_pipeline.dust train "$work\series" --artifact ..\web\mission-preview\src\data\dust-outlook.json
```

`inspect` checks the embedded NetCDF coordinate arrays and reports whether storm-outline CSVs independently agree. `extract` uses validated embedded axes when available, otherwise it requires the outline check or an explicit convention. All years must agree. Keep the generated artifact outside the web source during review. Record source digests, coordinate checks, any outline disagreements and per-year skill before approval of a bundled historical outlook. Fixture tests: `python -m pytest tests/test_dust_outlook.py`.
