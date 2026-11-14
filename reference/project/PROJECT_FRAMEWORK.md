# Return Window project framework

**Periapsis · NASA Space Apps Colombo · 12 November 2026**

Return Window is an offline-capable decision-support prototype for a human Marswalk. It helps a crew decide which science it can still attempt after a corridor closes, given the evidence available along the remaining approaches and the time reserved for returning to shelter. Its differentiator is a visible decision change caused by a specific evidence limit. The application should show what the crew can still do, what it must defer and what evidence would change that decision.

[Current implementation and evidence](CURRENT_STATE.md) · [Execution plan and acceptance gates](EXECUTION_PLAN.md)

## Crew workflow

1. **Choose a location and a science objective.** Use the Atlas to orient the crew. Inspect the local area of interest and the actual products available for the checkpoint, shelter and candidate approach. Separate source facts, interpretations and hypothetical crew locations.
2. **Check what the data supports.** Evaluate the requested variable and geometry against the versioned evidence sidecar. Show the specific product, native sampling, usable support and missing requirement. Allow only a named fallback whose own evidence requirements pass.
3. **Review the mission choices.** Where the pack and model authorize it, compare direct return with a science stop followed by return. Show travel, dwell and reserve as separate entries. List completed work and make the decision traceable to the inputs.
4. **Report a corridor closure and re-evaluate.** Apply a predefined closure to the current scenario, recompute supported choices, and update the route, time margin and science recommendation together. Keep completed tasks. Withhold unsupported calculations and clear invalidated recommendations. Where available, show a lower-resolution evidence view or a revised observation objective that requires no unsupported traverse.

The challenge calls for a layered, local view combining data from multiple NASA missions for navigation and new science. It explicitly allows less-studied areas. Its suggestion to consider three kinds of data is optional. Aim for optical context, topography and an independently useful science layer if supported. Every displayed layer should answer a crew question. The available challenge text is the Athlone organizer mirror. [Challenge brief](https://hackathlone.com/challenges/interplanetary-survival-guide-martian-map)

## Geography and evidence

| Layer | Role and boundary |
| --- | --- |
| Global geographic context | The Atlas supplies packaged Viking imagery and MOLA relief, search and named research anchors. The 56 named entries link to research and geographic points. The survey archive, sources and names are reference material. The Atlas offers qualitative traversal and science context. |
| Global index | HEALPix cell summaries from `marsdoc` are the single source of truth for planetary documentation. Nested HEALPix at Nside 128 gives 196,608 equal-area spherical cells with stable IDs such as `HPX128:96848`. A cell is a documentation summary unit. A crew corridor, a raster and a named region each have their own geometry. |
| Documentation assessment | `marsdoc` intersects product footprints with the query, distinguishes observed and usable coverage, and reports separate terrain and science/environment intervals and provenance. A verified absence is scoped to the named, complete inventory and its geometry. Where evidence bounds span tiers, show Unclassified. The weights and tiers are provisional policy. Areas without a published evidence summary remain unevaluated. The global evidence layer is pending. |
| Local evidence eligibility | Resolve a point, polygon or buffered route against full usable support, allowed product class, variable and the required scale, processing and time constraints. Eligibility requires one fully supporting product or a reviewed prepared derivative per variable, plus compatibility across variables when required. Numeric union coverage alone is insufficient. |
| Local terrain and science | Each region needs a checked window or area of interest, native product metadata, evidence geometry, actual usable support and an appropriate model. Source observations, derived elevation and science interpretation carry distinct provenance. Traversal eligibility, operational cost and scientific interest remain separate from documentation scores. |

The primary demo will use a **genuinely less-documented site**, selected for a demonstrated gap in a relevant modality alongside sufficient source-backed context to make a useful crew decision. The site is open. Document the catalogue, search bounds, dates and limits of each coverage claim. Where a catalogue is incomplete, describe what the selected products support and what remains unknown. Require an exact area of interest, a reproducible evidence query and a science objective with a cited observation or mapped feature. Compare coverage against a well-studied reference using the same modality and query method. Jezero is the known engineering control for elevation lineage, pack loading and capability refusal.

## Science and optimization

| Model | Method and inputs | Applicable result |
| --- | --- | --- |
| Mars geometry | Canonical evidence positions are east-positive, planetocentric `[longitude, latitude]` in degrees. Normalize declared source coordinates and longitude domain before indexing. Local raster geometry is projected easting/northing in metres, with source and local CRS, vertical reference, affine, pixel-center and row/column rules pinned. | Cell, footprint or position lookup and checked map alignment. The HEALPix area sphere and individual source or display CRS radii are distinct. |
| Elevation and terrain | Use native DTM elevations and recorded validity. For future analytical use, verify reprojection, vertical reference, native-scale gradients and quality or stencil exclusions before aggregation. Grade is rise over horizontal run. Slope angle follows from that grade. Any roughness metric needs a defined neighborhood and demonstrated effective scale. | Current Jezero capability is elevation preview. Slope, roughness, footing and tactical screening require separate analytical support and verification. MOLA supplies planetary context. |
| Directed traversal and return | For the simulation, use the existing four-neighbour shortest-path graph with eligible cells, fixed per-metre travel and uphill terms, and predefined closure cells. Reverse trips can differ. Compare remaining time minus the return reserve against the candidate trip cost. | Deterministic simulated return time, margin and route refusal. Current coefficients are software controls. Human Marswalk or rover estimates need profile-specific evidence and calibration. |
| Science choice | Evaluate uncompleted tasks independently as checkpoint-to-approach travel plus dwell plus approach-to-shelter travel. Remove choices that cannot retain the reserve, then apply stated priorities and explain the ranking. | The fixture ranks one outstanding task against direct return. Real tasks need reviewed targets, approach support, time assumptions and expected artifacts. Broader energy/consumables, chained-task and multi-objective optimization lack a qualified event runtime. |

For physical calculations, require all of the evidence resolver, pack capability and gate checks, and validated numerical model. Evidence support establishes where a specified calculation has data. It does not establish safety, navigation accuracy or a field prediction. Missing coverage does not establish hazards or absence of a feature. Preserve explicit reasons for unsupported scale, incomplete inventory, no route and reserve failure. Keep computations deterministic.

## Data and software boundaries

| Boundary | Canonical interface |
| --- | --- |
| NASA/partner archive → pipeline | Yumeth pins mission/instrument, asset ID, version, URL, checksums, reference frame, vertical reference, native scale, mask semantics and transformations. The corrected Stage 1 MOLA adapter owns verified ingestion. |
| Pipeline → evidence engine | Reuse [evidence sidecar v1](../../documentation/CONTRACT.md) and the generated schemas. Include provenance, observation and usable-support geometries, source variables, readiness and explicit scoped inventory assertions. Keep native sampling and effective feature scale separate. Isath reviews the evidence and scientific interpretation. |
| Producer → pack consumer | Reuse [mission pack v1](../../contracts/README.md) and its semantic validator. Immutable directory, `site.json`, flat filenames and byte lengths/SHA-256, with independently recorded site digest for release. G10 is an external acceptance receipt. Source-backed v1 is the pinned Jezero `elevation_preview`; explicit opt-in is required for `routing_simulation`. A new region's scientific evidence can use a stand-alone sidecar and local display assets. General source-backed pack ingestion and tactical capabilities are open contract changes. |
| Pack and evidence → local service → UI | Existing Python modules own resolution and simulation. The agreed application boundary to implement is a small local versioned HTTP adapter with `GET /healthz`, `GET /api/v1/site` and `POST /api/v1/plan`, plus a defined response for local evidence queries. The exact API fields, error mapping and evidence query operation require one shared review. The React/Vite/OpenLayers app owns `/mission`, visual layers and scenario interaction. Serve assets and service locally for offline replay. |

Analytical terrain in the existing synthetic contract is a north-up little-endian Float32 `z_m` raster with Boolean `valid_mask` and `screen_excluded_mask`; unsupported cells use NaN, finite zeros are legitimate, and request closures are temporary. Shape, CRS, bounds and masks must pass semantic validation. Source-backed preview uses a separate Float32 grid with an inset support polygon and has no station, scenario or analytical-mask payload. Scenario time, reserve and station dwell use whole seconds. The pack gates cover integrity, coordinates, coverage, analytical terrain, layer alignment, science provenance, capability, schema, hashes and actual consumer acceptance. Record G10 outside the immutable pack. [Stage 2 gate definitions](../pipeline/STAGE2_HANDOFF.md)

## Demonstration requirements

- Open at one real site's scientific decision. Show a local NASA-derived layer, a requested calculation, the precise evidence gap and a supportable next step. Use actual computed results and inspectable product provenance. Label a site with partial catalogue coverage accordingly.
- Show the live closure, changed return route and changed science recommendation. Use the separately labeled synthetic replay wherever real routing lacks qualification. Keep synthetic paths off real-site geography. Show both reserve and no-route states and retain completed work.
- Run the packaged workflow from a clean browser on a second disconnected machine. Capture the same qualified build and data for the submission. A fully source-backed tactical mission is contingent on a qualified producer, consumer and mobility model. The event baseline is a source-backed evidence decision plus the independently labeled mission simulation.

## Open decisions

- **Demo site and exact science decision.** Isath and Yumeth need a cited area, a scoped evidence-gap query, compatible display assets and a supported response to that gap. Abhimantha accepts the site after that evidence is reproducible.
- **Wire details and release sign-off.** Abhimantha and Senula freeze one API contract, including the evidence operation, time controls and coordinate representation. Yumeth and Senula confirm pack compatibility and Isath signs off on scientific claims.
- **Official resources and entry conditions.** The November 13 challenge resource list, any Colombo-specific submission/pitch cutoff and the applicability of the Local Lead's advance-development permission to Global Awards need confirmation. See the [execution plan](EXECUTION_PLAN.md#competition-and-eligibility).
