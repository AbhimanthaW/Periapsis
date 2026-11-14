# Mars Research Atlas

Open `/atlas` on the local [engineering workspace server](../README.md). The root and `/architecture` open the existing architecture editor. From the Atlas, choose **Research** to read the complete selected section or **Compare** to sort and inspect regions side by side. The traversal and science modes and the geographic feature type mode share the same location registry. Region IDs, research panel, profile and comparison choices have shareable URLs. Camera, layers and the last view persist on the browser origin.

## Geographic products

| Layer | Source and scope |
| --- | --- |
| Viking color | NASA Mars Trek rendition of the USGS Viking MDIM 2.1 public-domain global colorized mosaic. Local 512, 1024 and 2048 pixel-wide WebP display levels. The cited source mosaic is nominally 232 m/pixel. [USGS source](https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m) |
| MOLA relief | NASA Mars Trek rendition of the global MGS MOLA color shaded relief. Display levels match Viking. The source product is nominally 463 m/pixel. The layer is rendered relief, with no numerical elevation values exposed. [USGS source](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_global_color_shaded_relief_463m) |
| Jezero CTX | Optical subset of the USGS Mars 2020 TRN CTX orthomosaic, served by Mars Trek. The native product is nominally 6 m/pixel. The local rendition is a 1792 × 1280 WMTS mosaic. Enable the layer and zoom to Jezero from the layer metadata or Jezero's Data tab. [USGS source](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0) |
| Regions | All 56 use coordinates matched to the downloaded IAU/USGS Mars Gazetteer center-point archive. The Gazetteer snapshot date and hash are stored with the registry. The records for the broader Elysium volcanic rise and Medusae Fossae Formation use the named Elysium Mons and Medusae Fossae points as representative anchors. The other 54 use the matching named-feature centers, including the four crater aliases. The seed contains zero boundary polygons. [Gazetteer GIS downloads](https://planetarynames.wr.usgs.gov/GIS_Downloads) |

The rasters use the Mars Trek Simple Cylindrical geographic matrix advertised as `EPSG::104905`, with east-positive, planetocentric coordinates and north-up origin at 180°W, 90°N. The app registers a Mars-specific OpenLayers projection. Longitudes wrap and display in the ±180° domain. The scale bar estimates east–west ground distance at the view center using the declared 3,396,190 m spherical radius. The bar and the cylindrical display are for geographic context, especially near the poles. The CTX footprint is fixed to the exact tile extent. Its coverage is separate from the Jezero crater center and from any future routing pack. [NASA Mars Trek layers](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars) · [USGS Mars coordinate conventions](https://planetarynames.wr.usgs.gov/Page/MARS/system)

The local map, research and comparison work with internet access disabled and the local server running. Following external source links requires internet. No remote map request runs in the browser. The preparation script checks the advertised WMTS matrix and records capability hashes. It acquires the source tiles and packages display assets for the editor. [USGS use and credits guidance](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)

## Research extraction and audit

- **Completeness.** The registry contains IDs 01–56 exactly once. Mawrth Vallis is entry 47, whose source starts with an unnumbered transition. The public Markdown is an exact copy of the supplied survey. Each registry record indexes the archive’s original line range. Overview extracts, terrain and operations notes, scientific opportunities, observation tables, uncertainties and citations come from that record.
- **Documentation.** HEALPix evidence summaries are the sole authority for planetary documentation. The global evidence overlay is pending. Named entries provide geographic anchors and preserve the original research and citations.
- **Traversal.** Two entries have a single rover level. The other 54 use neutral markers with the original ranges, local contrasts, or unclassified wording. Valles Marineris’s moderate surfaces and extreme barriers stay distinct. Human EVA and generic terrain profiles show unknown. No rover rating is copied into either profile.
- **Scientific interest.** 54 entries have a supported single level and two remain unclassified. Conditions such as “for volcanology” and “for ice-focused missions” stay visible. No combined numeric scores were created. The optional overall priority entry opens the existing region-ranking specification.
- **Coordinates.** The Gazetteer snapshot supplies the map points. The survey’s reported centers, diameters and envelopes remain in its original text and may differ from the Gazetteer snapshot. Nested and related features are independently selectable via the index and overlap menu. Related-feature notes provide geographic context and convey no containment geometry.
- **Evidence.** Source labels and URLs are carried through. Agency-hosted links and media proxies are distinguished. Individual citations and scientific claims were not validated across all entries. Indirect images remain links and are not embedded. Numerical statements in the survey remain attributed text. None became a numeric score, a physical calibration or a routing weight. Some entries lack a standalone extracted uncertainty or dataset summary and point readers to the archive.
- **Extraction gaps.** Entries 18 and 47 lack a matching standalone location line. Their Gazetteer points and geological descriptions are available. Entry 01 lacks a registry-style documentation note and uses the archived evidence table. Entries 01 and 02 lack a standalone uncertainty field and retain limitations in their archived sections and traversal tables. All 56 have a terrain extract or table and at least one non-proxy reference. The extracted links include 389 agency or archive links, 110 other survey citations and 291 media proxy references. These categories identify link hosts and carry no assurance about the cited claim.
- **Readiness.** The Jezero display subset and the global maps are packaged. No region has a validated site pack connected to this Atlas. The planning handoff type records selected region and profile, with site pack, start, objective, target and constraint fields pending. Atlas links resolve to the current canonical Architecture Workspace components.

## Regeneration and checks

Run these commands from `reference/engineering-workspace/`. The imagery script updates the local global tiles and the shared Jezero image and metadata in `web/src/mission/assets/`.

```sh
python3 scripts/extract-atlas-research.py "/path/to/Regions Nasa Space Apps.md" "/path/to/MARS_nomenclature_center_pts.kmz"
# With Pillow installed in a local Python environment:
python3 scripts/prepare-atlas-imagery.py
npm run check:atlas
npm run check:data
npm run build
```

The Gazetteer archive URL and source hashes are in the generated registry and layer manifest. Preserve these with published builds. Use the survey archive for the complete source record and the registry for the geographic interface.
