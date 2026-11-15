import { expandModels } from './model-data'
import { expandPipeline } from './pipeline-data'
import { architectureSchema, defaultView, emptyAlgorithm, emptyDataset, newComponent, newParameter, newVariable } from './schema'
import type { Algorithm, Architecture, Component, Connection, Dataset, Group, Parameter, Reference, Variable } from './schema'

const groups: Group[] = [
  { id: 'sources', name: 'External sources', summary: 'MRO · Mars 2020 · geology', phase: 'offline', tone: 'data', description: 'Archived observations and published interpretations for western Jezero. A catalog record establishes discoverability. Byte access, exact overlap, labels and target registration are separate build gates.' },
  { id: 'ingest', name: 'Data ingestion', summary: 'Pinned assets · labels', phase: 'offline', tone: 'data', description: 'An offline, reproducible Python CLI acquires and validates source assets. Only a validated site pack crosses the runtime boundary.' },
  { id: 'prep', name: 'Scientific preprocessing', summary: 'Mars CRS · terrain · GIS', phase: 'offline', tone: 'data', description: 'Use a common local metre plane. Preserve the distinction between elevations, derived terrain quantities, interpreted geology and assumed screening rules.' },
  { id: 'pack', name: 'Local site pack', summary: 'Versioned · immutable files', phase: 'offline', tone: 'data', description: 'An immutable release of aligned local artifacts. Keep native resolution, coverage, transforms, credits, hashes and provenance with each layer.' },
  { id: 'ui', name: 'Crew interface', summary: 'React · OpenLayers', phase: 'runtime', tone: 'neutral', description: 'A tablet-friendly planning and field workspace for a fictional two-person crew. Compare baseline and updated decisions with a time ledger, retained and deferred science and source evidence.' },
  { id: 'api', name: 'Planning API', summary: 'Loopback · versioned JSON', phase: 'runtime', tone: 'neutral', description: 'The local Python service serves both built applications, regional evidence, ranking and simulated planning. Regional evidence binds an Atlas ID to the selected HEALPix anchor and a reviewed package/query pair where available.' },
  { id: 'decision', name: 'Decision engine', summary: 'Time ledger · science', phase: 'runtime', tone: 'decision', description: 'Evaluate a single next action under the remaining time and return reserve. Show direct return, feasibility, reason codes and evidence. Suppress recommendations when an admissible on-budget return is unavailable.' },
  { id: 'routing', name: 'Terrain routing', summary: 'Directed graph · SciPy CSR', phase: 'runtime', tone: 'data', description: 'Build directed, weighted adjacency from the prepared grid. Apply closure exclusions per request. Solve outward travel and return-to-shelter on the appropriate graph orientations.' },
  { id: 'deploy', name: 'Deployment', summary: 'Local first · optional host', phase: 'assurance', tone: 'neutral', description: 'Use the identical app and pinned data in one local process or an optional team-approved container host. Keep a labeled offline replay for live-demo failure.' },
  { id: 'validate', name: 'Validation', summary: 'GIS checks · solver tests', phase: 'assurance', tone: 'constraint', description: 'Planned acceptance checks and measurements. Catalog presence does not validate the pack, routes, decisions or real EVA performance.' },
]

const report = (locator: string): Reference => ({ label: 'Return Window strategy report', locator, url: '' })
const link = (label: string, url: string): Reference => ({ label, url, locator: '' })
const refs = {
  dtm: link('USGS HiRISE DTM catalog', 'https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40'),
  tiles: link('USGS HiRISE component TIFFs and labels', 'https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/index.html'),
  quality: link('USGS Jezero stereo DTM quality study', 'https://www.usgs.gov/publications/evaluating-stereo-dtm-quality-jezero-crater-mars-hrsc-ctx-and-hirise-images'),
  ortho: link('USGS HiRISE orthomosaic', 'https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_orthorectified_image_mosaic'),
  ctx: link('USGS CTX science products', 'https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic'),
  stack: link('Stack et al. western Jezero map and GIS supplement', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7116714/'),
  sim: link('USGS SIM 3464 regional geologic map', 'https://pubs.usgs.gov/publication/sim3464'),
  rover: link('NASA Perseverance sample catalog', 'https://science.nasa.gov/mission/mars-2020-perseverance/mars-rock-samples/'),
  outcrop: link('JPL delta-front sampling locations', 'https://www.jpl.nasa.gov/images/pia24924-2-perseverance-sampling-locations-in-jezeros-delta/'),
  images: link('NASA Jezero abrasion images', 'https://science.nasa.gov/resource/two-abrasion-patches-from-perseverance-at-jezero-delta/'),
  places: link('PDS Mars 2020 PLACES bundle', 'https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn%3Anasa%3Apds%3Amars2020_rover_places&version=11.0'),
  meda: link('PDS Atmospheres Node MEDA archive', 'https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html'),
  crism: link('Published Jezero CRISM analysis', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8243932/'),
  esa: link('ESA Mars Express Jezero context', 'https://www.esa.int/Science_Exploration/Space_Science/Mars_Express/An_interactive_map_to_explore_Jezero_crater'),
  scipy: link('SciPy directed Dijkstra', 'https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.dijkstra.html'),
  gdal: link('GDAL virtual file and range access', 'https://gdal.org/en/stable/user/virtual_file_systems.html'),
  ol: link('OpenLayers custom projection', 'https://openlayers.org/en/latest/apidoc/module-ol_proj_Projection-Projection.html'),
  usage: link('USGS copyright and credits', 'https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits'),
  media: link('NASA media guidelines', 'https://www.nasa.gov/nasa-brand-center/images-and-media/'),
}
const components: Component[] = []
function add(group: string, id: string, name: string, category: Component['category'], tech: string, description: string, locator: string, details: Partial<Component> = {}) {
  components.push({ ...newComponent(id, group, category, name), status: 'planned', technology: tech.split(' · '), purpose: description.split('. ')[0].replace(/\.$/, '') + '.', description, references: [report(locator)], ...details })
}
function source(id: string, name: string, tech: string, description: string, data: Partial<Dataset>, references: Reference[], options: Partial<Component> = {}) {
  add('sources', id, name, 'External dataset', tech, description, '§6 · Product-level data manifest', {
    classification: 'Catalog evidence', ...options,
    dataset: { ...emptyDataset, ...data },
    references: [report('§6 · Product-level data manifest'), ...references],
  })
}
source('hirise-dtm', 'HiRISE terrain model', 'MRO · USGS · 1 m posts', 'Core elevation input for slope and directed route costs. Read the western or delta component TIFFs if mosaic access fails.', {
  mission: 'Mars Reconnaissance Orbiter', product: 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40', provider: 'USGS Astrogeology', dataType: 'Stereo-derived elevation (m), vertically referenced to MOLA topography', format: 'GeoTIFF and XML', resolution: 'Nominal 1 m posts. Spacing is distinct from positional and vertical accuracy.', crs: 'Mars equirectangular, latTs 0°, lon0 0° per product name. Read body, radius and conventions from WKT and label.', coverage: 'Jezero mosaic and indexed component footprints. Confirm the exact western delta crop.', temporal: 'Static composite', limitations: 'Native masks, seams, registration and actual resolution at the selected site remain build gates.', availability: 'Public index; mosaic byte and range access TBD', verification: 'Catalog/index cited in report. Component index rechecked. Site checks pending.',
}, [refs.dtm, refs.tiles, refs.quality])
source('hirise-ortho', 'HiRISE optical mosaic', 'MRO · USGS · 0.25 m', 'Fine optical context for the map and co-registration checks. Keep display imagery separate from the analytical DEM.', {
  mission: 'Mars Reconnaissance Orbiter', product: 'Mars 2020 TRN HiRISE orthorectified image mosaic', provider: 'USGS Astrogeology', dataType: 'Optical intensity', format: 'GeoTIFF', resolution: 'Nominal 0.25 m', crs: 'Native Mars equirectangular; use asset WKT and affine', coverage: 'Jezero mosaic; test shared AOI and approach coverage', temporal: 'Static composite; retain source acquisition IDs', limitations: 'Check shadows, seams and overlap. Optical brightness does not measure composition.', availability: 'Public catalog per report; AOI extraction pending', verification: 'Catalog verified by report; co-coverage pending',
}, [refs.ortho, refs.tiles])
source('ctx', 'CTX regional fallback', 'MRO · 20 m DTM / 5 m ortho', 'Use the 5 m orthomosaic for lighter visual context. If fine terrain is unavailable, use the 20 m DTM only in an explicitly separate regional preview.', {
  mission: 'Mars Reconnaissance Orbiter', product: 'Jezero CTX science DTM and orthomosaic', provider: 'USGS / JPL', dataType: 'Stereo elevation (m) and optical intensity', format: 'GeoTIFF', resolution: '20 m terrain, 5 m optical', crs: 'Verify Mars CRS and datum per label; extended DTM vertically tied to MOLA', coverage: 'Crater-wide', temporal: 'Static mosaics', limitations: 'Small scarps and footing hazards unresolved. Preserve fine nodata. Use a grid of 20 m or coarser in preview.', availability: 'Public catalog per report', verification: 'Catalog verified by report; regional AOI not validated',
}, [refs.ctx], { notes: 'Fallback. Optical substitution and analytical preview are separate choices.' })
source('perseverance', 'Perseverance observations', 'Mars 2020 · samples + images', 'Use historical sample, abrasion and context imagery at Skinner Ridge and Wildcat Ridge as one science cluster. Attribute each asset and keep proposed crew observations separate.', {
  mission: 'Mars 2020 / Perseverance', product: 'Mars Rock Samples catalog, delta-front location references and abrasion images', provider: 'NASA / JPL', dataType: 'Sample/lithology descriptions, named outcrops, sols and surface images', format: 'Public web records and image assets', resolution: 'Perspective imagery; no uniform ground pixel size', crs: 'No assumed map coordinates for images or targets', coverage: 'Western Jezero field sites; irregular coverage', temporal: 'Pin relevant 2022 records and sol/date', limitations: 'Rover evidence supports science context. Verify target attribution separately from approach placement.', availability: 'Public catalog and images; review media rights', verification: 'NASA sample catalog rechecked; exact target alignment pending',
}, [refs.rover, refs.images, refs.outcrop], { classification: 'Observation' })
source('places', 'Perseverance PLACES', 'Mars 2020 · PDS localization', 'Anchor rover observations using archived position and orientation. Keep the rover fix, inferred feature center and hypothetical approach node separate.', {
  mission: 'Mars 2020 / Perseverance', product: 'mars2020_rover_places bundle', provider: 'NASA Planetary Data System', dataType: 'Historical rover location and orientation', format: 'Archive products and PDS labels; inspect selected asset', resolution: 'Asset-specific positional certainty', crs: 'Read native frame and longitude/latitude conventions from product labels', coverage: 'Rover traverse and recorded fixes', temporal: 'Irregular historic records; retain sol/time', limitations: 'A rover pose is distinct from a drill target and does not establish human traversability.', availability: 'Public PDS bundle cited by report', verification: 'Archive identified; selected fixes and transform TBD',
}, [refs.places])
source('geology', 'Western Jezero geology', 'Stack et al. · GIS supplement', 'Published photogeologic interpretation for science context. Preserve unit codes and contacts. USGS SIM 3464 is the regional fallback.', {
  mission: 'Mars 2020 science team mapping', product: 'Stack et al. Online Resource 3; USGS SIM 3464 fallback', provider: 'Authors / USGS', dataType: 'Interpreted polygons, contacts and categorical unit metadata', format: 'GIS ZIP / shapefile and accompanying documentation', resolution: 'Use map scale, not pixel spacing. SIM 3464 is 1:75,000.', crs: 'Inspect selected shapefile .prj and README', coverage: 'Western Jezero; fallback regional', temporal: 'Static, pre-landing interpretation', limitations: 'Thematic interpretation supplies neither walkability nor mineral probabilities. Confirm redistribution rights.', availability: 'Public supplement and USGS release per report', verification: 'Catalog/supplement verified by report; file CRS and registration pending',
}, [refs.stack, refs.sim], { classification: 'Interpretation' })
source('meda', 'MEDA historical context', 'Mars 2020 · PDS Atmospheres', 'Optional pressure history with labeled rover position and sol/time. Keep outside the decision path.', {
  mission: 'Mars 2020 / Perseverance', product: 'MEDA pressure products', provider: 'NASA PDS Atmospheres Node', dataType: 'Near-surface pressure (Pa per selected label)', format: 'PDS tables and XML', resolution: 'Point sampling; cadence and quality are product-specific', crs: 'Join documented rover position by matching sol/time', coverage: 'Rover-local points with gaps', temporal: 'Historical', limitations: 'No live data or corridor forecast', availability: 'Public archive cited by report', verification: 'Exact product and cadence TBD',
}, [refs.meda], { classification: 'Optional', priority: 'P2' })
source('crism', 'CRISM spectral context', 'MRO · FRT000047A3 / FRT00005C5E', 'Optional published georeferenced spectral interpretation for western Jezero. Verify a usable product, rights and alignment before inclusion.', {
  mission: 'Mars Reconnaissance Orbiter', product: 'Jezero targeted CRISM coverage', provider: 'MRO CRISM / published research', dataType: 'Near-infrared observations and interpreted mineralogy', format: 'Published georeferenced derived asset TBD', resolution: 'Read selected product label', crs: 'Asset geometry TBD', coverage: 'Patchy targeted passes', temporal: 'Historical', limitations: 'Context only. No spectral classifier.', availability: 'Published observations; event-ready raster TBD', verification: 'Study identified; file, co-registration and rights pending',
}, [refs.crism], { classification: 'Optional', priority: 'P2' })
source('esa', 'ESA regional context', 'Mars Express · HRSC / CTX', 'Partner orientation reference for Jezero. Optional context without a core computation dependency.', {
  mission: 'Mars Express / MRO', product: 'ESA interactive Jezero map', provider: 'ESA and partners', dataType: 'Regional cartographic orientation', format: 'Interactive published map', resolution: 'Exact deliverable TBD if adopted', crs: 'Verify labels if an asset is adopted', coverage: 'Jezero region', temporal: 'Archival', limitations: 'Orientation only', availability: 'Public reference per report', verification: 'Reference identified; no proposed pack integration',
}, [refs.esa], { classification: 'Optional', priority: 'P2' })

const v = (name: string, type: string, unit: string, componentId: string, description = '', options: Partial<Variable> = {}): Variable => ({ ...newVariable(), name, type, unit, componentId, description, ...options })
const p = (name: string, type: string, unit: string, defaultValue: string, description: string, constraints: string, provenance: Parameter['provenance'] = 'Assumption'): Parameter => ({
  ...newParameter(), name, type, unit, defaultValue, description, constraints, provenance,
})
function model(group: string, id: string, name: string, tech: string, description: string, algorithm: Partial<Algorithm>, details: Partial<Component> = {}, category: Component['category'] = 'Scientific model') {
  add(group, id, name, category, tech, description, '§6 · Site preparation and computation', {
    classification: 'Derived', ...details, algorithm: { ...emptyAlgorithm, ...algorithm },
  })
}
add('ingest','registry','Source asset registry','Data processor','Pinned IDs · credits · hashes','Record IDs, URLs, acquisition/sol, retrieval dates, credits, license, original dimensions and checksums. Verify rights for the geology supplement and images. Keep an attribution link when redistribution is uncertain.','§6 · Access and usage',{references:[report('§6 · Access and usage'),refs.usage,refs.media]})
add('ingest','retrieve','Asset acquisition','Data processor','Window read · component fallback','Attempt a byte-range window read, fall back to indexed component TIFF or original local files, and confirm access and bytes before selecting the site. Capture the raw retrieval and checksum in a reproducible offline build.','§6 · Site preparation',{references:[report('§6 · Site preparation'),refs.gdal,refs.tiles]})
add('ingest','readers','Raster and vector readers','Data processor','GDAL · Rasterio · Fiona/GeoPandas','Read rasters with GDAL/Rasterio and vectors with Fiona or GeoPandas where needed. Parse gdalinfo JSON, GeoTIFF transforms, PDS/XML labels and shapefile .prj/README. Keep band units, scale/offset and native masks.','§6–7 · Preparation and data build')
add('ingest','source-gate','Product validation gate','Validation','Units · coverage · CRS · lineage','Reject unusable metadata, unresolved body/datum, unexpected scale or missing required footprint. Confirm units, nodata, resolution, temporal provenance and attribution before processing. Record optional assets separately.','§6 · Site preparation')
add('ingest','aoi','Jezero patch selection','Data processor','Western delta · roughly 1–2 km','Choose one compact overlapping patch with at least two defensible activities or approaches. Exact extent, shelter, checkpoint and approach nodes remain TBD. Try indexed fine components or one alternate patch before changing product scope.','§5–6 · Site choice and preparation',{status:'tbd'})

model('prep','projection','Local Mars projection','pyproj · local metres','Transform all layers into a declared Mars metric plane. Validate verified datum, longitude direction, wrapping, order, and planetocentric vs planetographic latitude.',{
  name:'Local equirectangular reprojection',family:'Geospatial transformation',method:'Use a standard parallel near AOI latitude on the verified Mars base datum. Keep both native and local WKT, north-up transform and [easting,northing].',validation:'Independently check east/west and north/south Mars-geodesic scale, origin, cell centers, row direction and three landmarks.',limitations:'Reject unresolved planetary datum transforms.',
},{parameters:[p('local CRS','WKT','','TBD','Freeze after asset-label verification.','Mars datum and metric plane required','TBD')]})
model('prep','elevation','Elevation grid','NumPy · nominal 5 m','Crop and co-register the fine terrain and imagery in the shared plane. Represent elevation separately from the conservative native terrain screen.',{
  name:'Elevation aggregation',family:'Raster aggregation',method:'Aggregate source footprint to north-up graph cells. Document median vs mean choice for representative elevations; retain conservative validity separately.',validation:'Compare terrain and optical anchors, shape, transform and source samples. Check overlaps and seams.',
},{inputs:[v('native elevations','raster','m','hirise-dtm')],outputs:[v('z_m','float32[rows,cols]','m','terrain-file')],parameters:[p('fine graph spacing','number','m','5','Nominal graph cell width.','Match affine and validate the footprint.'),p('regional preview spacing','number','m','20 or coarser','Coarse fallback grid.','No fine-scale terrain claim.'),p('aggregation reducer','enum','','TBD','Select median or mean and record method.','Keep the upper local screen separate.','TBD')]})
model('prep','gradient','Native terrain gradient','Fixed kernel · slope in degrees','Derive local slope at native scale before graph aggregation. This estimates terrain gradient and screen support independently of directed edge grade.',{
  name:'Finite differences / GDAL slope',family:'Raster gradient',method:'Choose and document a fixed gradient kernel and use complete native source support. Convert gradient magnitude to degrees for screening.',alternatives:'Explicit finite-difference support or documented GDAL slope.',validation:'Check flat and known-slope fixtures, nodata stencil, seams and slope units.',limitations:'Native samples can miss small terrain features.',
},{inputs:[v('native elevations','raster','m','hirise-dtm')],outputs:[v('native slope','raster','deg','screen')],parameters:[p('gradient kernel','enum','','TBD','Select fixed stencil.','Complete valid stencil support.','TBD')]})
model('prep','coverage','Coverage and support masks','Native nodata · complete support','Propagate native validity and full kernel support to routed cells. A mixed invalid cell is excluded; preserve coverage separately from the terrain screen.',{
  name:'Conservative mask aggregation',family:'Raster mask',method:'Require complete valid native footprint and gradient support. Keep unknown cells explicit through packaging and visualization.',validation:'Test mixed, boundary and seam cases; assert unknown cells cannot create graph edges.',
},{outputs:[v('valid mask','bool[rows,cols]','','terrain-file')]})
model('prep','screen','Slope screening','Upper local slope · assumption','Screen fine cells with the documented native-scale upper slope aggregate. This can catch cross-slope exposure that signed edge grade alone can miss.',{
  name:'Conservative local slope screen',family:'Threshold rule',method:'Aggregate an upper native-scale slope statistic independently of representative elevation. Reject configured slope-screen exceedances. Keep the actual slope grid if useful.',limitations:'The threshold and aggregation do not validate footing, traction or suit performance.',validation:'Inspect threshold boundary, excluded cells and steep features in QGIS.',
},{classification:'Assumption',inputs:[v('native slope','raster','deg','gradient')],outputs:[v('screen mask','bool[rows,cols]','','terrain-file')],parameters:[p('screen threshold','number','deg','15','Illustrative prototype test value.','Document configured threshold and slope units.'),p('upper slope statistic','enum','','TBD','Choose a conservative aggregation from valid samples.','Record in processing metadata.','TBD')]})
add('prep','context','Imagery and geology alignment','Data processor','Local bounds · original unit IDs','Clip optical context and geological units into the common metre plane. Generate display WebP/PNG with exact bounds and keep interpreted unit IDs and source credits. Check terrain/ortho landmarks and inspect vector alignment.','§6–7 · Preparation and data build')
model('prep','register','Observation registration','Feature area · separate approach','Reconcile dated rover evidence, positional certainty and geology with candidate observations. Store original rover fix, inferred feature location or coarse area and approved approach separately.',{
  name:'Source-anchored registration',family:'Geospatial registration and review',method:'Use PLACES and cited imagery plus independent GIS anchors. Record provenance, uncertainty and artifact expected at each station. GIS and science owners jointly approve placement.',validation:'Check known anchors and approach reachability. Do not silently snap targets. Exact approach nodes TBD.',
},{classification:'Interpretation',inputs:[v('rover fixes','archive records','','places'),v('observations','source records','','perseverance')],outputs:[v('approach definitions','station records','','stations-file')]})
add('pack','manifest','site.json','Storage artifact','Manifest · schema · provenance','Include schema_version, pack_id, raster shape, affine, metre extent, source and local CRS WKT, display extents, vertical datum, native resolution, processing method, evidence class, source URLs, acquisition/sol, credits, coverage and hashes.','§7 · Pack contract')
add('pack','terrain-file','terrain.npz','Storage artifact','float32 elevation · boolean masks','Store matching z_m, validity and screening masks, and optional per-cell screen slope. Coordinates are [easting,northing]; raster indices are [row,col]. Mask or dimension mismatch fails the pack gate.','§7 · Pack contract')
add('pack','stations-file','stations.json','Storage artifact','Approaches · tasks · dwell','Keep approach node, attribution, positional certainty, task ID, planned dwell in whole seconds (dwell_s), priority, expected artifact type and source asset ID.','§7 · Pack contract')
add('pack','display-files','Display imagery and overlays','Storage artifact','WebP/PNG · local vectors','Package image and terrain display products with exact local bounds and projected geological overlays with original units. Vector serialization is TBD; preserve local projected metre coordinates.','§7 · Pack contract')
add('pack','evidence-files','Evidence assets','Storage artifact','Local photos · sources · credits','Keep curated photos, source labels, descriptions, transform metadata and attribution with source asset IDs. Distinguish measured, interpreted, assumed and simulated provenance. Preserve source links for optional independent review.','§6–7 · Evidence and pack contract')
add('pack','pack-check','Pack assembly and integrity','Data processor','Reproducible CLI · version + hashes','Emit the pinned immutable site pack and manifest. Check required files, compatible schema and IDs, grid and affine consistency, bounds, references and file hashes before offline launch.','§7–8 · Data build and integration gate')

add('ui','mission','Mission setup and review','Frontend component','Local site · shelter · hypotheses','Load the one configured site, choose a hypothetical shelter and hypothesis, compare the two candidate science actions and review outbound, return and direct-return routes. Show the planned allowance, field time and reserve.','§5 · Plan and review')
add('ui','field','Crew reports blocked corridor','Frontend component','Checkpoint · simulated event','Confirm the current checkpoint manually, preserve completed task IDs, set remaining time and report a simulated corridor closure with source and event time. P0 uses a predefined closure ID; validating drawn closures is P1.','§5, §7 · Execute and request',{classification:'Simulation'})
add('ui','freshness','Invalidate the previous plan','Frontend component','Request ID · stale history','Invalidate the current recommendation at a closure, scenario change or new request. Keep the prior plan only as gray history while pending or failed. Accept a response as current only if request and pack identity still match active state.','§7, §9 · Runtime storage and demo',{classification:'Decision',inputs:[v('change event','scenario event','','field'),v('response request ID','string','','serialize')],outputs:[v('current scenario request','JSON','','plan-api')]})
add('ui','map','Local Mars map','Frontend component','OpenLayers · local metre plane','Render local raster and vector layers without an Earth projection, online tiles or coordinate helpers that assume lat/lon. Toggle optical, terrain/slope and interpreted geology. Draw actual grid legs, closure and exclusions.','§5, §7 · Map and UI',{references:[report('§7 · Map and UI'),refs.ol]})
add('ui','cards','Show updated choice','Frontend component','Baseline vs update · time ledger','Compare the measured bedding transect, oriented photo set and return now. Show feasibility, changed signed margin and retained/deferred science. If return is unavailable or over reserve, suppress additional science and show the scenario contingency instruction. Round crew-facing time; keep raw values in evidence.','§5, §9 · Choose and demo',{classification:'Decision'})
add('ui','inspector','Route and evidence inspector','Frontend component','Segment · task · source','Inspect segment source, scale, coverage and exclusion rule plus task evidence, pace assumptions, reserve and closure provenance. Keep original evidence values and attribution available offline; richer replay/evidence links are P1.','§5–7 · Evidence view')
add('ui','session','Versioned browser session','Frontend component','Memory or localStorage','Keep one browser session keyed by pack and schema version. Preserve completed tasks, chosen scenario and comparison state. Each plan request carries the full state.','§7 · Runtime storage')

add('api','loader','Site pack loader','Backend service','Immutable startup · baseline cache','Load one pack and validate version, shape, assets and matching source metadata. Keep baseline graph cache keyed by pack/config. Apply per-request exclusions to copied/rebuilt adjacency rather than mutating shared graph.','§7 · Solver and runtime')
add('api','site-api','Site information','API','GET /api/v1/site','Return the synthetic simulation fixture identity, fixed inputs and local grid. GET /api/v1/regions/{id} returns regional context, capability gates and pinned local evidence where available.','§7 · Solver and API',{outputs:[v('site metadata','JSON','','mission'),v('layer bounds and assets','JSON','','map')]})
add('api','health-api','Health check','API','GET /healthz','Report ready when pack and solver are initialized. Exact response body and status mapping TBD.','§7 · Hosting')
add('api','plan-api','Plan request','API','POST /api/v1/plan','Accept a stateless full scenario request. P0 closes predefined polygons. For a P1 drawn closure validate area, complexity and bounds before acceptance.','§7 · Request',{
  inputs:['pack_id','request_id','checkpoint_id','shelter_id','completed_task_ids','remaining_s','reserve_s','scenario_id','closure_ids'].map(name => v(name,name.endsWith('_ids') ? 'string[]' : name.endsWith('_s') ? 'number' : 'string',name.endsWith('_s') ? 's' : '', 'freshness')),
  outputs:[v('full request','JSON','','request-check')],
})
add('api','request-check','Scenario input validation','Backend service','Full request · bounds · units','Validate pack and identifiers, manual checkpoint, shelter, completed tasks, numeric budgets and closure bounds. Resolve station IDs, scenario pace and closure polygons. Classify malformed or out-of-bounds inputs separately from missing terrain and over-budget return.','§6–7 · Inputs and request')
add('api','serialize','Plan response','API','JSON · IDs · nulls + reason codes','Serialize pack_id, request_id, status, return_option, candidate_options[], recommended_id, evidence[] and warnings[]. Each option includes task_id, outbound_s, dwell_s, return_s, margin_s, outbound_xy_m, return_xy_m, included_evidence_ids and reason_codes[]. Use nulls when unavailable.','§7 · Response',{inputs:[v('recommendation and evidence','structured decision','','explain'),v('failure and reason codes','structured failure','','abstain')],outputs:[v('plan response','JSON','','freshness')]})

model('routing','grade','Directed edge geometry','Local metres · signed grade','Compute distances between cell centers and direction-specific signed grade from representative cell elevations.',{
  name:'Center distance and signed grade',family:'Grid geometry',formula:'d(i,j) = ‖xy[j] − xy[i]‖₂; g(i,j) = (z[j] − z[i]) / d(i,j)',method:'Use local easting/northing and z_m. Uphill and downhill directions use opposite signed grades.',validation:'Check flat cardinal and diagonal distance, gradient sign and units on a tiny fixture.',
},{inputs:[v('z_m','float32[rows,cols]','m','terrain-file')],outputs:[v('edge geometry and grade','edge arrays','m, dimensionless','traverse')]})
model('routing','traverse','Traversal time','Asymmetric · illustrative pace','Estimate nonnegative direction-dependent traversal seconds. Use scenario assumptions for the crew pair, independent of rover motion and consumables.',{
  name:'Linear uphill/downhill grade penalties',family:'Parametric deterministic cost',formula:'w(i,j) = d / v × (1 + k_up × max(g,0) + k_down × max(−g,0))',method:'Keep terrain screening separate from along-edge grade. Use declared scenario parameters for every leg.',limitations:'No physiology, traction, suit or slip calibration. Values are illustrative.',validation:'Flat and uphill/downhill fixtures, weight positivity and reverse-direction cost.',
},{classification:'Assumption',inputs:[v('signed grade','float','dimensionless','grade'),v('center distance','float','m','grade')],outputs:[v('edge weights','array','s','graph')],parameters:[
  p('v','number','m/s','0.5','Illustrative base pace.','v > 0'),p('slower pace','number','m/s','0.35','Illustrative P1 pace.','v > 0'),p('k_up','number','dimensionless','4','Illustrative uphill penalty.','k_up ≥ 0'),p('k_down','number','dimensionless','2','Illustrative downhill penalty.','k_down ≥ 0'),
]})
model('routing','graph','Directed terrain graph','CSR · 8 neighbors · no corner cuts','Build or retrieve the sparse baseline graph keyed by pack/config. Include only admissible cells and edges. Block diagonals when a side cell is excluded.',{
  name:'Directed grid adjacency',family:'Sparse graph construction',method:'Materialize directed weighted CSR and transpose. Preserve per-edge geometry, source footprint and exclusions. Cache immutable baseline.',alternatives:'Switch to four neighbors if tests uncover shortcuts.',complexity:'O(V) memory with bounded degree.',validation:'Test masks, slope screens, diagonal side cells, positive weights and stable adjacency ordering.',
},{inputs:[v('valid/screen masks','bool[rows,cols]','','terrain-file'),v('directional travel times','array','s','traverse')],outputs:[v('base graph','CSR','s','closure')],parameters:[p('neighbor count','integer','','8','Proposed grid connectivity.','4 or 8; verify diagonal treatment.')]})
model('routing','closure','Apply closure constraints','Request-scoped mask · exclusions','Conservatively mark the simulated corridor footprint. Exclude edges touching the closure or blocked cells, including diagonals that would cut an excluded side cell. Keep the shared baseline unchanged.',{
  name:'Closure intersection and exclusion',family:'Geometric masking',method:'Apply a validated local-plane polygon to a request-scoped graph. Carry closure IDs, event metadata and excluded cells to the UI.',validation:'Check intersecting edges, side cells, excluded endpoints, and two concurrent requests with different closures.',
},{classification:'Simulation',inputs:[v('closure polygons','local geometry','m','request-check'),v('base graph','CSR','s','graph')],outputs:[v('admissible graph','CSR','s','solve')]})
model('routing','solve','Recompute outbound and return','Two directed Dijkstra runs','Compute outward times from the current checkpoint and return-to-shelter times from a single run on the transposed graph.',{
  name:'Sparse Dijkstra',family:'Single-source shortest path',method:'Run from c on G and from h on Gᵀ. Use graph after closure and screen masks; preserve predecessor arrays. D(·,h) is not a forward shelter search.',complexity:'Approximately O(V log V) for two runs on a bounded-degree grid.',limitations:'Shortest estimated time on the modeled, admissible graph only.',validation:'Known tiny asymmetric graph, independent solver and deterministic tie checks.',pseudocode:'out = dijkstra(G, indices=c)\nback = dijkstra(G.T, indices=h)',
},{references:[report('§6 · Return and task selection'),refs.scipy],inputs:[v('scenario graph','CSR','s','closure'),v('checkpoint c and shelter h','node IDs','','request-check')],outputs:[v('cost fields and predecessors','arrays','s','legs')]},'Algorithm')
model('routing','legs','Route reconstruction','Forward geometry · reverse predecessors','Reconstruct outward and return legs in the original direction. Keep original cell-center geometry, leg seconds and segment evidence. Preserve null routes for unreachable pairs.',{
  name:'Predecessor backtracking',family:'Path reconstruction',method:'Follow valid predecessors and orient return s→h in G. Keep direct c→h independently. Report length and slope exposure outside the optimization objective.',validation:'Verify routes follow actual directed edges and never smooth across masks.',
},{inputs:[v('costs and predecessors','arrays','s','solve')],outputs:[v('outbound and return legs','routes','m, s','feasibility'),v('direct return leg','route','m, s','budget')]},'Algorithm')

model('decision','budget','Compute return-time margin','B − R − travel · direct return','Use remaining scenario time B and required reserve R. Show the signed margin for direct return and preserve the distinction between an unavailable route and an over-reserve route.',{
  name:'Time budget and reserve gate',family:'Deterministic feasibility rule',formula:'return_margin = B − R − D(c,h)',method:'Reject an invalid numeric request. Suppress science when direct return is unavailable or direct margin is below zero. A zero margin meets the modeled threshold.',validation:'Check exact zero, exhausted allowance and null direct leg.',
},{classification:'Assumption',inputs:[v('remaining_s','number','s','request-check'),v('reserve_s','number','s','request-check'),v('direct return travel time','nullable number','s','legs')],outputs:[v('return option and margin','nullable option','s','rank')],parameters:[p('remaining time','number','s','3600','Illustrative report scenario (60 min), not a measured mission value.','Nonnegative; validate API input.'),p('reserve','number','s','900','Illustrative report scenario (15 min).','Nonnegative; validate API input.')]})
add('decision','tasks','Science task definitions','Backend service','Bedding transect · oriented photos','The full task returns a measured bedding transect; the alternate returns oriented photos that preserve bedding context and defer the measurement. Use separately approved approaches and records with priority, dwell and source asset IDs. Do not reselect completed work.','§5–7 · Tasks and stations',{classification:'Assumption',inputs:[v('station records','JSON','','stations-file')],outputs:[v('unfinished candidate tasks','records','s','feasibility')],parameters:[p('transect dwell','number','s','600','Illustrative 10 min action duration.','Verify final scenario and artifact.'),p('photo set dwell','number','s','360','Illustrative 6 min action duration.','Verify final scenario and artifact.')]})
model('decision','feasibility','Reevaluate science tasks','Both legs + dwell · signed margins','Evaluate every unfinished task using the same closure and pace scenario. Require two admissible legs and a nonnegative margin. Preserve candidate failure reasons and deferred artifacts.',{
  name:'Single-action feasibility',family:'Budget-constrained option evaluation',formula:'cost(s) = D(c,s) + a_s + D(s,h)\nmargin(s) = B − R − cost(s)',method:'Show each task as feasible, over budget or unavailable. Require an admissible on-budget direct return before making a science recommendation.',limitations:'Single next action in P0. P2 may enumerate ordered pairs, charging each dwell once.',validation:'Test closure threshold crossing, exact zero, null legs and completed tasks.',
},{classification:'Decision',inputs:[v('candidate route legs','routes','m, s','legs'),v('station dwell and task IDs','records','s','tasks'),v('remaining and reserve','numbers','s','request-check')],outputs:[v('candidate costs and margins','options','s','budget')]})
model('decision','rank','Select next action','Science priority → greatest margin','Among feasible unfinished tasks, use predeclared science priority, then greatest margin for equal priority. Present direct return as an explicit option. If no task fits and return does, show return now.',{
  name:'Lexicographic selection',family:'Deterministic ranking',method:'Use the same priority schedule before and after closure. Stable final tie rule TBD. Avoid a weighted safety score.',validation:'Test equal priority, equal margin, completions and abstention override.',
},{classification:'Decision',inputs:[v('candidate options','options','s','feasibility'),v('return gate and margin','nullable option','s','budget'),v('unavailable states','reason codes','','abstain')],outputs:[v('recommended option','nullable ID','','explain')]},'Algorithm')
model('decision','abstain','Abstain and classify failures','Missing evidence · no path · over budget','Reject invalid positions/inputs separately. Use insufficient_terrain_evidence for a coverage-gap endpoint; distinguish no_path_under_constraints from a valid route that exceeds the available time after reserve.',{
  name:'Fail-closed result classification',family:'Constraint diagnostics',method:'P0 produces no route across unknown cells. Optional diagnostic can relax only the unknown mask and retain known exclusions and closure. If connectivity returns, report missing evidence without rendering that path. Suppress science without an on-budget return.',limitations:'Disconnected within the modeled AOI does not prove the real terrain is impassable.',validation:'True nodata fixture, invalid/out-of-bounds inputs, blocked graph, reachable over-budget return and no stale recommendation.',
},{classification:'Decision',inputs:[v('validated endpoint / rejection','state','','request-check'),v('route availability','flags','','legs'),v('direct margin','nullable number','s','budget')],outputs:[v('failure reason and warnings','reason codes','','serialize')]})
model('decision','sensitivity','Pace sensitivity','P1 · same routes · zero crossing','Evaluate the same route at a slower declared pace and flag when the feasibility margin crosses zero. Display the scenario assumptions.',{
  name:'Shared-route what-if',family:'Deterministic sensitivity',method:'If only uniform base speed changes, rescale travel times and keep dwell unchanged. If weights or masks change, recompute or explicitly evaluate one shared route across scenarios.',limitations:'No confidence percentage. Never splice legs across incompatible scenarios.',validation:'Check unchanged path ordering under uniform speed scaling and zero crossing.',
},{priority:'P1',classification:'Optional',inputs:[v('routes and times','routes','s','legs'),v('scenario weights','parameters','','traverse')],outputs:[v('sensitivity flag','boolean','','explain')]})
add('decision','explain','Explain the revised choice','Backend service','Reason codes · evidence · artifacts','Attach segment and task source IDs, nominal scale, coverage, applied screen, pace and reserve, and simulated event provenance. Show which science artifact is retained or lost and why a route or task was rejected. Use audited text and deterministic reason codes.','§5–7 · Decision and provenance',{classification:'Decision'})
add('decision','excluded','Excluded from core','Annotation','AI/ML · live telemetry · suit forecasts','Core uses deterministic geospatial rules, costs and ranking. No validated human walkability labels, Mars suit calibration or generative decision requirement. Future EVA, life support and live navigation systems are outside this prototype.','§5, §7 · Scope and AI',{classification:'Excluded',priority:'P3'})

add('deploy','local','Offline demo environment','Infrastructure','One local process · Wi-Fi off','Serve the built Atlas, Mission and demo, plus the local APIs, from one loopback Python process. Verify hashes for the manifest assets and matching checkout before startup. Keep sourced evidence and calculations separate from the simulated replanning and hazard fixtures.','§7, §9 · Hosting and demo')
add('deploy','host','Optional hosted release','Infrastructure','Same application · container','Use the identical image or pinned local configuration on a team-approved container host. Host choice is TBD. Verify public access from a clean device if released during the event.','§7–9 · Hosting and release',{classification:'Optional',priority:'P1'})
add('deploy','replay','Labeled offline replay','Storage artifact','Captioned recording · fallback','Keep a time-stamped local recording and annotated screenshot for app or device failure. Identify recorded footage as replay and keep pack version visible.','§9 · Reliability')
add('validate','gis-check','Data and GIS acceptance','Validation','QGIS / Mars Trek · three anchors','Independently confirm sources, units and CRS, three shared landmarks, Mars-geodesic scale, transform, coverage, nodata and seams. Initial terrain/ortho overlay target is one analytical cell when both show the same feature. Inspect two alternative profiles and separate target uncertainty.','§6, §8 · GIS checks',{dependencies:['source-gate','projection','elevation','coverage','screen','register','pack-check']})
add('validate','solver-test','Graph and decision tests','Validation','Synthetic fixture · independent solver','Unit-test flat distances, slope sign, asymmetric costs, masked edges, diagonal exclusion, blocked corridor, no path, invalid input, zero margin, completion persistence and stable ties. Hand-check a tiny directed graph and compare with an independent solver.','§6 · Validation',{dependencies:['grade','traverse','graph','closure','solve','legs','budget','feasibility','rank']})
add('validate','scenario-test','Closure and abstention proof','Validation','Same inputs · three baselines','Compare static route after closure, shortest route ignoring science and the actual decision. Demonstrate a rejected transect, feasible alternate and direct return. Run a separate true missing-data case. Check stale response suppression and same-output reproducibility across devices.','§6, §8–10 · Validation and judging',{dependencies:['closure','abstain','rank','freshness','cards']})
add('validate','perf-test','Runtime and offline acceptance','Validation','Click-to-card · cold start · pack size','Measure latency, pack size and local cold-start on the presentation hardware, versioned by fixture. Two seconds click-to-updated-card is an internal target only. Confirm localhost with Wi-Fi off and a replay available.','§6–9 · Reliability',{dependencies:['local','health-api','solve','cards','replay']})

const connections: Connection[] = []
function edge(source: string, target: string, label: string, details: Partial<Connection> = {}) {
  connections.push({
    id: `${source}--${target}`, source, target, label, kind: 'Data flow', payload: label, format: '', protocol: '',
    description: '', validation: '', dependencies: [], ...details,
  })
}
for (const [id, payload] of [
  ['hirise-dtm','Terrain GeoTIFF + XML'],['hirise-ortho','Orthorectified imagery'],['ctx','Fallback terrain and optical assets'],
  ['perseverance','Archived observations'],['places','Archived fixes and orientations'],['geology','Interpreted unit polygons'],
]) edge(id,'registry',payload)
edge('registry','retrieve','Pinned asset IDs and URLs')
edge('retrieve','readers','Raster, vector and archive files')
edge('readers','source-gate','Labels, affine, units and masks')
edge('source-gate','aoi','Validated footprints and inputs')
edge('aoi','projection','Native products and chosen extent')
edge('projection','elevation','Local metric elevations')
edge('projection','gradient','Native-support DTM + metric scale')
edge('projection','context','Co-registered optical and vectors')
edge('projection','register','Local transform and context')
edge('elevation','coverage','Aggregate footprint')
edge('gradient','coverage','Native stencil support')
edge('gradient','screen','Native-scale slope')
edge('coverage','screen','Complete validity mask')
edge('elevation','terrain-file','z_m · float32',{format:'NumPy NPZ'})
edge('coverage','terrain-file','Native validity mask',{format:'NumPy NPZ'})
edge('screen','terrain-file','Screen mask + optional slope',{format:'NumPy NPZ'})
edge('projection','manifest','CRS, affine and extent',{format:'JSON + WKT'})
edge('registry','manifest','Attribution and source IDs',{format:'JSON'})
edge('register','stations-file','Approaches, tasks and source IDs',{format:'JSON'})
edge('register','evidence-files','Curated assets and uncertainty')
edge('context','display-files','Local imagery and geology',{format:'WebP/PNG and projected vectors (format TBD)'})
for (const id of ['manifest','terrain-file','stations-file','display-files','evidence-files']) edge(id,'pack-check','Pack member')
edge('pack-check','loader','Versioned local pack',{format:'JSON, NPZ, images and vectors',protocol:'Local filesystem',validation:'Match pack ID, schema, shape, affine, hashes and required assets.'})
edge('loader','site-api','Local manifest and assets')
edge('loader','health-api','Pack and solver readiness')
edge('loader','request-check','Pack IDs, stations and scenarios')
edge('loader','grade','Elevation, affine and masks')
edge('loader','graph','Immutable baseline by pack and config')
edge('loader','tasks','Pack station and evidence records')
edge('loader','explain','Asset IDs, provenance and rules')
edge('site-api','mission','Site context',{kind:'Response',format:'JSON',protocol:'Same-origin HTTP · GET /api/v1/site'})
edge('site-api','map','Layer bounds and assets',{kind:'Response',protocol:'Same-origin HTTP'})
edge('mission','freshness','Baseline planning inputs',{kind:'Control'})
edge('field','session','Completed tasks and field state',{kind:'Control'})
edge('field','freshness','Simulated corridor closure',{kind:'Control',payload:'checkpoint_id, completed_task_ids, remaining_s and closure_ids; event source and time',description:'Invalidate the previous plan immediately after the simulated report.'})
edge('freshness','plan-api','Submit fresh scenario',{kind:'Request',format:'JSON',protocol:'Same-origin HTTP · POST /api/v1/plan',payload:'pack_id, request_id, checkpoint_id, shelter_id, completed_task_ids, remaining_s, reserve_s, scenario_id, closure_ids',validation:'Fresh request ID and complete active state.'})
edge('plan-api','request-check','Validate plan request',{kind:'Control',format:'JSON'})
edge('request-check','closure','Validated closure geometry',{validation:'Known closure ID in P0. P1 drawn closures require area, complexity and bounds checks.'})
edge('request-check','solve','Current checkpoint and shelter')
edge('request-check','tasks','Completed task IDs')
edge('request-check','budget','Remaining time B and reserve R',{format:'Seconds'})
edge('request-check','abstain','Invalid inputs',{kind:'Control'})
edge('grade','traverse','Center distances and signed grades')
edge('traverse','graph','Directional travel seconds')
edge('graph','closure','Immutable baseline adjacency')
edge('closure','solve','Admissible graph',{payload:'Directed CSR with closure, terrain and coverage exclusions',validation:'Do not mutate cached baseline. Exclude invalid side-cell diagonals.'})
edge('solve','legs','Time fields and predecessors')
edge('legs','feasibility','Outbound and return legs')
edge('legs','budget','Direct return estimate')
edge('legs','abstain','Missing or disconnected legs')
edge('tasks','feasibility','Approaches, dwell and priority')
edge('feasibility','budget','Signed task margins',{description:'Combine candidate margins with the independently evaluated direct-return gate.'})
edge('feasibility','rank','Feasible unfinished options')
edge('budget','abstain','Unavailable or over-reserve return',{kind:'Control'})
edge('budget','rank','Direct-return option and gate',{kind:'Control'})
edge('abstain','rank','Suppress further science',{kind:'Control'})
edge('abstain','serialize','Failure reason and warnings',{kind:'Control'})
edge('legs','sensitivity','Evaluate the same paths')
edge('sensitivity','explain','Pace sensitivity flag')
edge('rank','explain','Selected action and alternatives')
edge('explain','serialize','Auditable choice and evidence',{format:'Structured options, reason codes and evidence IDs'})
edge('serialize','freshness','Plan response with request ID',{kind:'Response',format:'JSON',protocol:'Same-origin HTTP · POST /api/v1/plan',validation:'Discard superseded requests and incompatible pack IDs. No stale recommendation.'})
edge('freshness','cards','Accept current decision',{kind:'Control'})
edge('freshness','map','Current route and gray history',{kind:'Control'})
edge('cards','inspector','Task and reason evidence IDs')
edge('map','inspector','Selected segment evidence ID')
edge('local','loader','Local startup',{kind:'Deployment'})
edge('local','mission','Serve built UI',{kind:'Deployment'})
edge('host','local','Identical process / image',{kind:'Deployment'})
edge('cards','replay','Recorded demo only',{kind:'Deployment'})
edge('gis-check','pack-check','Site acceptance',{kind:'Validation'})
edge('solver-test','solve','Path verification',{kind:'Validation'})
edge('scenario-test','cards','Golden-path proof',{kind:'Validation'})
edge('perf-test','local','Offline and latency checks',{kind:'Validation'})

const traceStages = [
  ['simulated report', ['field--freshness']],
  ['validate + mask', ['freshness--plan-api','plan-api--request-check','request-check--closure']],
  ['admissible graph', ['closure--solve']],
  ['route legs', ['solve--legs','legs--feasibility']],
  ['signed margins', ['feasibility--budget']],
  ['rank or abstain', ['budget--rank','budget--abstain','abstain--rank','rank--explain']],
  ['current response', ['explain--serialize','serialize--freshness','freshness--cards']],
] as const


const decisionSteps = [
  { componentId:'field', caption:'Confirm the crew checkpoint and submit the simulated corridor closure.' },
  { componentId:'freshness', caption:'Mark the previous plan as history and submit a new request with the full crew state.' },
  { componentId:'closure', caption:'Validate the event through the API, then exclude the affected cells and edges from the request graph.' },
  { componentId:'solve', caption:'Find outward paths from the checkpoint and return-to-shelter paths on the transposed graph.' },
  { componentId:'feasibility', caption:'Compare both route legs and time on site for each unfinished task.' },
  { componentId:'budget', caption:'Recalculate signed margins and check direct return. In the report’s illustrative 60-minute allowance with a 15-minute reserve, the transect drops from +5 to −3 minutes.' },
  { componentId:'explain', caption:'Apply the science-priority rule or abstain. Attach the sources, reason codes and expected science artifacts.' },
  { componentId:'cards', caption:'Accept only the current response. In the report’s illustrative example, oriented photos preserve bedding context at +20 minutes and defer the measured transect. Direct return keeps +33 minutes.' },
].map((step,index) => ({
  ...step, transition: index ? traceStages[index - 1][0] : '', connectionIds: index ? [...traceStages[index - 1][1]] : [],
}))

const raw: Architecture = {
  schemaVersion: 1, architectureVersion: '1.0.0', title: 'Return Window', groups, components, connections,
  decisionSteps, layout: {}, viewSettings: defaultView,
}
export const baselineArchitecture = architectureSchema.parse(raw)
export const pipelineArchitecture = architectureSchema.parse(expandPipeline(baselineArchitecture))
export const initialArchitecture = architectureSchema.parse(expandModels(pipelineArchitecture))
