# Synthetic science fields for Return Window

This fixture exercises six output fields across the five workstream rows previously marked Dummy. One invented scene straddles 0° east near 36° north. The algorithms use the same Mars geometry and HEALPix coordinates as the documentation engine. This scene produces values for 28 of the 196,608 Nside 128 cells. The fixture is an opt-in software demonstration and carries `data_status: synthetic`.

| Field | Research and input to qualify | Implemented calculation and synthetic input |
|---|---|---|
| Deltas | Use Morgan et al. (2022) deposit outlines and retain each published origin/classification. The scarp-fronted deposits are putative deltas. Establish depositional context and confidence from published imagery interpretation or stratigraphy when available. Wilson et al. (2021) provides a crater-focused comparison. [Morgan data and field definitions](https://doi.org/10.25573/data.19952486) · [Wilson study](https://doi.org/10.1029/2020GL091653) | An invented scarp-fronted polygon. Intersect with the surveyed cell and union same-class pieces. Emit feature IDs, area in km², fraction of the cell mapped and survey fraction. |
| Alluvial fans | Use the same Morgan outlines with the published alluvial-fan class. Preserve equivocal fans separately during production qualification. Keep fan apexes as point context. Associated catchment polygons describe upstream drainage. [Morgan data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9385538/) | Two overlapping, invented fan polygons test partial coverage and union area across the seam. Use the same algorithm as the delta field, independently by class. |
| Valley networks | Prefer published centreline mapping using the Hynek, Beach and Hoke catalogue and the archived Goudge et al. classification where applicable. Preserve network and segment IDs, mapping scale and valley class. Check tributaries, incised valleys, outlet channels, and possible subglacial origins against the source fields before promoting any subtype. [Hynek study](https://doi.org/10.1029/2009JE003548) · [Goudge archive](https://doi.org/10.18738/T8/STRFZH) | An invented trunk and tributary. Clip to the surveyed cell, union coincident segments and measure Mars great-circle length. Return km and km per surveyed km². These are preserved-valley metrics. Discharge, active flow, chronology and network completeness remain unknown. |
| Mid-latitude glacial landforms | Use the Levy et al. supporting polygons for lobate debris aprons, lineated valley fill and concentric crater fill. The study mapped roughly ±30–50° using CTX mosaics and THEMIS-VIS. It used flow lineations, profile shape and surface textures. Treat the actual survey scope and any radar-confirmed ice as separate inputs. [Levy study and supporting data](https://doi.org/10.1002/2014JE004685) | Three invented polygons represent the mapped types. Return union area and feature types. Latitude defines the fixture setting. Ice content, depth, volume and periglacial landform classification require separate evidence. |
| Crustal magnetism | Evaluate Langlais et al. (2019) MGS/MAVEN internal spherical harmonics using the published coefficient normalization, reference radius and vector convention. Set a reporting altitude and verify sampled components against the authors' reference output. The published effective horizontal resolution is about 160 km at the surface. [Langlais model](https://doi.org/10.1029/2018JE005854) · [Author's coefficients](https://doi.org/10.5281/zenodo.3876714) | Sum fields from two invented equivalent dipoles 20 km below a 3,389.5 km reference sphere, at centres near the seam. At each supported centroid emit magnitude, outward component and Mars-fixed Cartesian components in nT at 150 km above that sphere. This exercises vector superposition, distance decay and coordinate signs. The production harmonic synthesis is pending. |
| Olivine | Prefer published OMEGA OSP rasters or calibrated reflectance from quality-screened observations. Use the Ody et al. instrument-specific band substitutions around orbit 7768 and keep each spectral index and the observed-pixel mask. Grain size, iron content, abundance, dust and mixed spectra affect detection. [Ody method, table 1](https://doi.org/10.1029/2012JE004149) · [NASA PDS OSP rasters and labels](https://pds-geosciences.wustl.edu/mex/mex-m-omega-5-ddr-global-maps-v1/mexomg_2000/data/olivine/) | Three non-overlapping tiles carry invented corrected reflectance spectra, including a positive candidate, a flat spectrum and a missing band. Calculate OSP1 and OSP2 from the weighted band ratios. A value strictly above 1.04 is a spectral candidate. Return valid area, candidate fractions and area-weighted index means. OSP3 requires a cube-specific background and remains pending. The output does not estimate abundance. |

## Numerical conventions

- Uses east-positive planetocentric coordinates and the existing Mars spherical charts. Source line segments and polygon edges follow shorter great-circle arcs. Upstream sources with different edge semantics need densification in their native coordinates. The cell uses the existing 16 samples per HEALPix edge.
- The surveyed fraction is independent of feature overlap. A field is `null` outside its synthetic support. Within the synthetic survey, zero means the fixture was evaluated with no mapped feature. The dipole field is available where the cell centre lies inside the fixture. Olivine uses only tiles with every required band available. Candidate area can also be expressed as a fraction of valid spectral area.
- Each dipole contributes `B = K / d³ [3(a·d̂)d̂ − a]`, with `a` the dipole axis, `d` the source-to-observer distance in km, and `d̂` the corresponding unit vector. The invented sources are at (359.4° E, 36.0° N) and (0.5° E, 36.6° N), with axes (350° E, 65° N) and (150° E, 20° S) and scale factors `K` of 1.4×10⁹ and 1.1×10⁹ nT·km³. Sum vectors before taking the magnitude. The Cartesian frame uses +X at 0° east on the equator, +Y at 90° east and +Z at the north pole.
- Spectral means weight the clipped valid tile areas. Duplicate or overlapping spectral tiles must be normalized to one prepared mosaic beforehand. Feature outlines union within each class. Linework unions geometrically coincident segments at overlay precision. Nearly coincident catalogue traces still need review upstream. Aggregate glacial area is a union across the three mapped types.
- Reported fractions use the sampled cell boundary. The fixture does not calibrate model confidence, survey sensitivity or thresholds for scoring.

## Use in the engine and map

From the repository root:

```sh
uv run --project documentation --locked marsdoc evidence/jezero/jezero-evidence.json \
  --cell HPX128:81858 --synthetic-context
```

The command returns the original `documentation` record and a sibling `synthetic_science_context` record with the recipe ID, method versions and fields. The Python entry point is `DocumentationEngine.synthetic_context(cell_id)`. Without the flag the CLI emits its normal output. The capability API reads the verified catalogue only and refuses synthetic context as a capability-query flag.

```sh
export RW_CELL_MAP_WORKSPACE="/absolute/path/to/cell-map"
uv run --project documentation --locked python documentation/cell-map/build_synthetic_context.py
RW_SCIENCE_VIEW=1 RW_EXPANDED_VIEW=1 RW_RANKING_VIEW=1 RW_SYNTHETIC_SCIENCE_VIEW=1 \
  uv run --project documentation --locked python documentation/cell-map/build_viewer.py
```

The first command creates `synthetic-science/synthetic-science-context.json` with records only for cells touched by the fixture. The viewer command uses the existing verified map exports and creates `mars-cell-map-synthetic-science.html` with a labeled test layer group, a zoomed view of the synthetic scene and a separate output filename. Start at `HPX128:81858` for valley length and use `HPX128:81856` for the olivine example. The published map, documentation scores, calculation eligibility and ranker inputs keep their existing source-backed contracts.

## Production qualification

1. Pin each published asset, licence, version, size and checksum. Verify source CRS, spatial validity, coverage masks and fields with the data-pipeline owner. A catalogue of positive hits alone does not close the inventory.
2. Validate representative real cases with catalogue feature IDs. Include Jezero or Eberswalde with a verified deposit ID, a manually checked valley and glacial landform, published magnetic control points at a stated altitude, and a Nili Fossae olivine detection alongside a valid low-index pixel and a masked pixel. Confirm them in the pinned dataset before adding gold assertions.
3. Check input and output dimensions and geometry canonicity. Compare length conservation and area convergence when increasing cell boundary samples, and record which survey scopes support zero detections. For real flux, ice, magnetization or mineral abundance, require the corresponding product and separate scientific decision rules.
4. Publish source-backed context only after those checks and explicit review. Keep modelled physical values and interpreted landforms traceable to their input products. Promote observational coverage or model eligibility only through the existing evidence contract with appropriate variable and support metadata.

## Verified fixture results

At Nside 128, cell `HPX128:81858` contains 50.45 km of synthetic valley linework and 16.45% synthetic putative-delta overlap. Cell `HPX128:81856` has 72.94% synthetic olivine candidate overlap. The exported fixture reproduced byte for byte on this checkout. The offline preview was exercised in Chromium with networking disabled. The rebuilt default map retained the existing embedded source data and offered only its source layers.
