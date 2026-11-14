# Expanded Return Window Mars map

Open `mars-cell-map-expanded.html` in a current browser. The map embeds its data and runs offline. `expansion/cells-enriched.ndjson.gz` contains all 196,608 records joined by HEALPix ID. `expansion/enriched-manifest.json` gives the exact file digest and identifies the source manifests. The baseline was built from GitHub main at `fa2bfce44315faa10d339409ea3146ca784fc4a8`. The new joins and preview are local artifacts.

| Added source | Data and spatial support |
|---|---|
| [NASA PDS ODE CTX EDR](https://ode.rsl.wustl.edu/mars/coverage/ODE_Coverage.aspx) | Acquisition-footprint counts at each centroid. The snapshot contained 167,196 rows. 166,093 unique, validated product outlines match 196,367 centres. |
| [NASA PDS ODE HiRISE RDRV11 and RDR4](https://ode.rsl.wustl.edu/mars/coverage/ODE_Coverage.aspx) | Projected image catalogue counts at 7,425 centres. The two archives contribute 188,763 and 16,503 accepted records respectively. Counts are catalogue product records and can count an acquisition represented in both releases. |
| [NASA PDS ODE HiRISE DTM](https://ode.rsl.wustl.edu/mars/coverage/ODE_Coverage.aspx) | 1,370 accepted product outlines yield catalogue product IDs at 114 centres. This centroid join uses a separate archive and spatial test from the original fractional stereo layer. |
| [SWIM for International Mars Ice Mapper](https://swim.psi.edu/SWIM4MIMProducts.php) | Published 0–1 m, 1–5 m, and deeper than 5 m composite ice-consistency grids. Values from −1 to +1 describe agreement among indicators within the archive's approximately ±60° latitude domain. The actual GeoTIFF affine and Mars CRS control the join. |
| [NASA PDS MGS TES dust maps](https://pds.nasa.gov/ds-view/pds/viewCollection.jsp?identifier=urn%3Anasa%3Apds%3Amgs_tes_atmos_dust-ice%3Adata_derived_maps) | One historical reconstructed 9.3 μm column dust optical depth map, MY25 sol 001, Ls 359.93°. The source retrieval window is 27 May–4 June 2000 UTC. The native grid is 6° longitude by 3° latitude. Missing samples remain null. The metadata includes the supplied retrieval count, reliability, and uncertainty. |
| [ASU MGS TES Lambert albedo](https://www.mars.asu.edu/data/tes_albedo) | Numerical WMS export at 4 pixels per degree. The dimensionless albedo records are surface reflectivity. |

The previous MOLA elevation and counts, scoped stereo/HiRISE coverage, SIM 3292 geology, TES nighttime thermal inertia and CRISM catalogue metadata remain in the combined rows. The cell-centre joins use native raster bins or published catalogue polygons. They supply discovery and scientific context. Exact-area fractions, local usable terrain, and route eligibility still come from the original documentation engine and validated product support. The new atmosphere and ice data do not enter route costs.

The loader checks Mars target, frame conventions, product family, raster dimensions, explicit nodata, and coverage bounds as applicable. Ambiguous catalogue footprints are excluded, with counts in `expansion/manifest.json`. The merged exporter checks file receipts, all cell IDs, and source-by-source coverage totals. Sources whose spatial or temporal scope cannot support a claim remain open.

For the mission view, the most useful remaining additions are a verified CTX optical raster and terrain support masks over the exact Arcadia and Jezero query geometries, followed by a cited science target in the chosen site. Broad climate time series, radiation and atmospheric profiles need date, altitude or site-aware interfaces. Detailed rover observations require their own locations and provenance.

## Repository layout

The scripts live in `documentation/cell-map/` alongside the documentation engine. Set `RW_CELL_MAP_WORKSPACE` to an external directory holding the existing source and output folders. The default is the ignored `data/cell-map/` directory. The committed `receipts/` describe the published snapshot. Generated artifacts are attached to the [expanded map prerelease](https://github.com/AbhimanthaW/Periapsis/releases/tag/mars-cell-map-v0.1.0).

The build stages use these workspace paths:

| Path | Role |
|---|---|
| `registry/mars-mola-meg004/0.1.0-rc.1/atlas` | Verified MOLA atlas from the pipeline release command |
| `catalogues/` | STAC snapshots written by `fetch_catalogues.py` |
| `science-sources/` and `expansion-sources/` | Source downloads matched to the snapshot receipts |
| `map/`, `science/` and `expansion/` | Generated baseline, science and combined data |

Use the [MOLA atlas release instructions](../../pipeline/README.md) to prepare the registry. Run `build_cells.py . "$RW_CELL_MAP_WORKSPACE/map"` from the repo root with the documentation environment and archive-check dependencies. Run `build_science.py` and `build_expansion.py` with the dependencies below. The acquisition scripts cover STAC, CTX EDR, and the TES nighttime raster pair. The remaining inputs come from the published sources listed above and in the science receipts. A fresh catalogue snapshot may produce different coverage totals and hashes.

```sh
export RW_CELL_MAP_WORKSPACE="/absolute/path/to/cell-map"
uv sync --project documentation --locked --python 3.12 --group archive-check
uv run --project documentation --locked --group archive-check python documentation/cell-map/build_cells.py . "$RW_CELL_MAP_WORKSPACE/map"
uv run --project documentation --locked --group archive-check --with pyshp==3.0.3 python documentation/cell-map/build_science.py
uv run --project documentation --locked --group archive-check --with pyshp==3.0.3 python documentation/cell-map/build_expansion.py
python3 documentation/cell-map/merge_metadata.py
RW_SCIENCE_VIEW=1 RW_EXPANDED_VIEW=1 uv run --project documentation --locked python documentation/cell-map/build_viewer.py
```

## Sourced catalogues for the cell-ranking workstream

Open `mars-cell-map-sourced.html` for the additional offline layers. The map highlights cells containing imported records. Dark cells have unknown survey coverage.

| Catalogue | Retained records | Cells with evidence | Interpretation |
|---|---:|---:|---|
| [Goudge et al. paleolakes](https://www.jsg.utexas.edu/goudge/shared-data/) | 425 | 423 | Published open- and closed-basin locations |
| [Leask and Ehlmann chloride sites](https://data.caltech.edu/records/kasms-vp209) | 642 | 500 | Published Osterloo site points as cross-referenced in the 2021 archive |
| [NASA PDS hydrated-mineral sites](https://pds-geosciences.wustl.edu/mex/mex-m-omega-5-ddr-global-maps-v1/mexomg_2000/data/hydrous/) | 1,851 | 1,676 | Carter et al. 2013 OMEGA and CRISM detection points with source product IDs |
| [USGS SIM 3292 structures](https://pubs.usgs.gov/sim/3292/) | 3,588 | 35,338 | Approximate line length in each cell, with the source interpretation |
| [IAU/USGS Gazetteer](https://planetarynames.wr.usgs.gov/GIS_Downloads) | 2,054 | 1,974 centres and 40,914 approximate bounds | Published centres and selected adopted feature bounds for chaos, chasmata, fossae, labyrinthi and undae |
| [USGS dune database](https://pubs.usgs.gov/publication/ofr20181164) | 1,462 | 1,351 | Equatorial and south polar Stability Index worksheet locations |
| [USGS Cushing cave candidates](https://astrogeology.usgs.gov/search/map/mars_global_cave_candidate_catalog_v1_cushing) | 1,062 | 513 | Candidate entrances and published candidate type |
| [InSight Marsquake Service](https://www.insight.ethz.ch/en/seismicity/catalog/v14/) | 189 | 25 | Estimated event locations from the EarthScope A/B location-quality query |

[MOCAAS](https://www.ias.universite-paris-saclay.fr/moccas/) describes the aqueous mineral product. Its linked data ZIP returned HTTP 410 during retrieval, so this snapshot has no MOCAAS mineral-class values. The older NASA PDS point catalogue includes four duplicate rows that are collapsed. It records hydrated-mineral detections and supplies neither individual mineral classes nor the area surveyed. The datasets marked Dummy in the workstream request are outside this build.

The loader maps catalogue coordinates to Nside 128 NESTED. It normalizes signed east longitude into [0, 360). The Goudge table labels longitude as east and latitude as north. The table leaves the latitude type unspecified, so the point join assumes the Mars planetocentric convention at this grid scale. Point rows establish a cell association at the supplied location. A candidate entrance, dune site or estimated event origin carries its original observational meaning. The Gazetteer export contains an identical duplicate feature ID that is collapsed. Dune worksheet row numbers disambiguate a published ID repeated at different coordinates.

For the SIM 3292 `Global_Structure` layer, the archive service returns projected lines with a 100 m generalization parameter. The loader subdivides each projected edge into pieces of at most 2 km, inverse-projects to Mars, and bins each geodesic length at its midpoint using the engine's 3,389.5 km sphere. Cell-edge allocation is approximate. Five lines have samples outside the published Mars Robinson projection domain and are quarantined by feature ID. Gazetteer bounds are approximate longitude/latitude rectangles. Their overlap uses 64 equal-area HEALPix child centres per cell, so fractions are multiples of 1/64 and narrow intersections may be missed. The rectangles provide named context and can extend beyond physical features.

The downstream files are in `ranking/`. The full export preserves the original fields and adds `sourced_catalogue_context`. The smaller `cell-ranking.ndjson.gz` contains one `{cell_id, evidence}` object per cell in NESTED order. Point-layer keys hold source ID arrays. `structures` maps IDs to kilometres. `gazetteer_approximate_bounds` maps IDs to sampled fractions for individual published bounds. The feature IDs resolve through `ranking-features.json.gz`, which is keyed by source layer. The Gazetteer centre and bounds fields share its `gazetteer` feature dictionary. The manifest identifies each input and output by SHA-256. Missing keys represent unknown survey coverage. These fields supply catalogue evidence for the separate ranker and carry no model eligibility, documentation tier or route-cost changes.

Rebuild from the repo root after preparing the baseline workspace above. `--fetch` downloads missing pinned files and rejects changed bytes. `--merge` also needs the verified expanded export and its manifest. Omit it to build the standalone supplement.

```sh
uv run --project documentation --locked --with openpyxl==3.1.5 --with pyshp==3.0.3 python documentation/cell-map/build_ranking_layers.py --fetch --merge
RW_SCIENCE_VIEW=1 RW_EXPANDED_VIEW=1 RW_RANKING_VIEW=1 uv run --project documentation --locked python documentation/cell-map/build_viewer.py
```
