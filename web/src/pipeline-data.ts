import { emptyAlgorithm, emptyDataset, newComponent, newParameter, newVariable } from './schema'
import type { Architecture, Component, Connection, Dataset, Gate, Group, Parameter, Reference, Variable } from './schema'

const geo = 'A · Geospatial and terrain data'
const science = 'B · Scientific context and regional intelligence'
const shared = 'Shared · Geospatial + science'
const brief = (locator: string): Reference => ({ label:'Planetary data pipeline brief', locator, url:'' })
const ref = (label: string, url: string): Reference => ({ label,url,locator:'' })
const sources = {
  mola: ref('NASA PDS · MOLA MEGDR archive', 'https://pds-geosciences.wustl.edu/missions/mgs/megdr.html'),
  ctx: ref('Caltech Murray Lab · Global CTX Mosaic V01', 'https://murray-lab.caltech.edu/CTX/V01/TilePages/'),
  ctxPaper: ref('Mosaic processing and coverage · Dickson et al.', 'https://doi.org/10.1029/2024EA003555'),
  ctxCatalog: ref('USGS Astrogeology · CTX Global Mosaic V1', 'https://astrogeology.usgs.gov/search/map/mars-mro-ctx-global-mosaic-murray-lab-v1'),
  ode: ref('NASA PDS · Mars Orbital Data Explorer', 'https://ode.rsl.wustl.edu/mars2/'),
  themis: ref('USGS · THEMIS controlled mosaics', 'https://stac.astrogeology.usgs.gov/docs/data/mars/themis_controlled_mosaics/'),
  hrsc: ref('ESA PSA · Mars Express HRSC map-projected archive', 'https://esdcdoi.esac.esa.int/doi/html/data/planetary/MARS-EXPRESS/MEX-M-HRSC-4-REFDR-MAPPROJECT-EXT3.html'),
  hrscAccess: ref('NASA PDS · HRSC products and access', 'https://pds-geosciences.wustl.edu/missions/mars_express/hrsc.htm'),
  hirise: ref('University of Arizona · HiRISE DTMs', 'https://www.uahirise.org/dtm/about.php'),
  quality: ref('USGS · Jezero stereo DTM quality comparison', 'https://www.usgs.gov/publications/evaluating-stereo-dtm-quality-jezero-crater-mars-hrsc-ctx-and-hirise-images'),
  geology: ref('USGS SIM 3292 · Geologic Map of Mars', 'https://pubs.usgs.gov/publication/sim3292'),
  msl: ref('NASA PDS · Curiosity archive and PLACES', 'https://pds-geosciences.wustl.edu/missions/msl/'),
  crism: ref('NASA PDS · CRISM archive and derived products', 'https://pds-geosciences.wustl.edu/missions/mro/crism.htm'),
  marsCrs: ref('USGS Astrogeology · Projection conventions', 'https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/learning-about-map-projections/'),
  marsProj: ref('USGS Astrogeology · PROJ on planetary bodies', 'https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/proj-projections/'),
  gdal: ref('GDAL · Virtual filesystems and range requests', 'https://gdal.org/en/stable/user/virtual_file_systems.html'),
}
const group = (id: string,name: string,summary: string,description: string,tone: Group['tone'] = 'data'): Group =>
  ({ id,name,summary,description,tone,phase:'offline' })

export const pipelineGroups = [
  group('sources','Scientific data sources','Orbital · surface · published','Archive and publication records by role. Global relief and imagery are separate from regional stereo elevation. Jezero assets remain an example, with coverage and exact product selection evaluated per region.'),
  group('discovery','Discovery & registry','Catalogs · footprints · selection','Discover and normalize asset metadata, index footprints, and select versioned input assets by objective. An indexed footprint is evidence of possible coverage; it does not establish valid-pixel support.'),
  group('ingest','Acquisition & ingestion','Raw cache · labels · integrity','Acquire full, tiled, local or windowed inputs with verified capabilities. Preserve unaltered source bytes and labels separately from derivatives. Quarantine unreadable or corrupt assets.'),
  group('spatial','Mars spatial reference','Body · CRS · transforms','Shared Mars coordinate conventions and transform verification for planetary indexing, polar coverage and per-region metric analysis. Carry native and destination horizontal and vertical references.'),
  group('atlas','Global Mars atlas','Relief · tiles · region index','Precompute a multi-resolution visual atlas, contextual elevation and scientific overlays. Record actual footprint and resolution by layer. Offline scope is a selected atlas subset and selected region packs.'),
  group('regions','Region evaluation','Evidence · priority · readiness','Accept an arbitrary set of candidate region records, including the current 56-region research effort. Keep scientific judgment, availability and suitability separate. Prioritization can authorize investigation; readiness requires independent gates.','decision'),
  group('prep','Regional processing','Job spec · imagery · geology','Turn a selected region and pinned assets into local terrain crops and independently processed optical and geology overlays. Jezero is a reference case; regions can vary in data, projection and output capabilities.'),
  group('terrain','Terrain & routing inputs','Grid · support · exclusions','Prepare baseline analytical elevation, native gradient, validity and screening arrays. Supply inputs to the directed runtime solver. Explicitly withhold detailed routing on insufficient terrain.'),
  group('evidence','Science & evidence','Observations · targets · tasks','Preserve observations, interpreted features, candidate targets and hypothetical approach stations as distinct, linked records. Orbital and published science can support a region without rover observations.'),
  group('quality','Integration & quality','Cross-layer checks · G1–G10','Integrate independently processed layers, record gate outcomes and classify capability. Every gate starts Not evaluated. Required failures block the affected capability; optional failures may yield a documented partial release.','constraint'),
  group('pack','Packaging & publication','Immutable packs · offline','Publish validated, versioned atlas assets and regional packs to a local registry. Deliver a bounded offline subset. Exact storage location, tile encoding and distribution policy are engineering decisions.','decision'),
  group('provenance','Build provenance','Inputs · config · checksums','One shared build configuration and lineage ledger ties source versions, methods, transforms, software, reports and artifacts together. Versions are reproducible and releases immutable.','neutral'),
]

const components: Component[] = []
function add(id: string,groupId: string,name: string,tech: string,description: string,section: string,owner: string,extra: Partial<Component> = {}) {
  const category = extra.category ?? 'Data processor'
  components.push({
    ...newComponent(id,groupId,category,name), technology:[tech], purpose:description.split('. ')[0].replace(/\.$/,'')+'.',
    description,owner,references:[brief(section)],...extra,
  })
}
function model(id: string, groupId: string, name: string, tech: string, description: string, section: string, owner: string, method: string, limitations: string, validation: string, parameters: Parameter[] = [], extra: Partial<Component> = {}) {
  add(id,groupId,name,tech,description,section,owner,{
    category:'Scientific model', classification:'Derived', parameters,
    algorithm:{ ...emptyAlgorithm,name, family:tech,description,method,limitations,validation },
    ...extra,
  })
}
const p = (name: string,type: string,unit: string,description: string,constraints: string,defaultValue = 'TBD',provenance: Parameter['provenance'] = 'TBD'): Parameter =>
  ({ ...newParameter(),name,type,unit,description,constraints,defaultValue,provenance })
const v = (name: string,type: string,unit: string,componentId: string,description: string,required = true): Variable =>
  ({ ...newVariable(),name,type,unit,componentId,description,required })
function dataset(id: string,name: string,tech: string,description: string,details: Partial<Dataset>,references: Reference[],owner = geo,priority: Component['priority'] = 'P0',classification: Component['classification'] = 'Catalog evidence') {
  add(id,'sources',name,tech,description,'§4 · Scientific data sources',owner,{
    category:'External dataset',priority,classification,
    dataset:{ ...emptyDataset, verification:'Primary catalog or product documentation verified. Asset bytes and regional suitability have not been evaluated.', ...details },
    references,
  })
}

dataset('mola-megdr','MOLA MEGDR','MGS · global altimetry grids','Use the MOLA gridded topography band for planetary elevation context. Preserve radius, areoid and counts roles when present and keep derived relief separate.',{
  mission:'Mars Global Surveyor',instrument:'Mars Orbiter Laser Altimeter',product:'MGS MOLA Topography Derived · MEGDR',provider:'NASA PDS Geosciences Node',
  dataType:'Gridded altimetry-derived topography, radius and observation counts; areoid where supplied',format:'PDS .IMG and .XML; historical labels and ENVI headers',
  resolution:'Global 4, 16, 32, 64 and 128 pixels/degree; separate polar maps 128, 256 and 512 pixels/degree.',
  crs:'Read native map projection, vertical quantity and units per product label; global filenames index longitude east 0–360°.',
  coverage:'Global grid products plus separate polar products. Inspect per-cell counts, masks and polar tile boundaries.',
  temporal:'Bins MGS mission altimetry; archive release and acquisition are separate.',processingLevel:'Derived gridded record',
  availability:'Catalog and file index available',accessMethod:'Pinned PDS image and corresponding label/header; larger products are tiled.',
  limitations:'Grid spacing is angular and does not imply uniform metre resolution, local accuracy or pedestrian traversability.',
},[sources.mola])

dataset('ctx-mosaic','Global CTX Mosaic','MRO · Murray Lab V01','Use the published V01 visible-light mosaic for atlas context and asset discovery. Retain contributor image references and mask/footprint metadata.',{
  mission:'Mars Reconnaissance Orbiter',instrument:'Context Camera',product:'Global CTX Mosaic of Mars V01',provider:'Caltech Murray Lab / USGS catalog',
  dataType:'Optical mosaic derived from CTX observations',format:'GeoTIFF tiles; tile pages list ancillary products',
  resolution:'5.0 m/pixel nominal published mosaic sampling',crs:'Inspect chosen GeoTIFF CRS, body and affine.',
  coverage:'Publisher reports about 99.5% of the surface between 88°S and 88°N; keep gaps and polar limits explicit.',
  temporal:'Multi-observation mosaic; retain contributing product IDs and V01 release.',processingLevel:'Processed mosaic, distinct from constituent observations',
  availability:'Public tile and product catalog',accessMethod:'Fetch selected published tiles or prebuild lower levels. Probe range support per object.',
  limitations:'Optical imagery, not elevation. Seams, illumination and incomplete coverage remain relevant.',
},[sources.ctx,sources.ctxPaper,sources.ctxCatalog])

dataset('themis-ir','THEMIS day / night IR','Mars Odyssey · thermal context','Optional planetary context based on separate controlled day and night infrared mosaics. Preserve product identity, acquisition and units.',{
  mission:'2001 Mars Odyssey',instrument:'Thermal Emission Imaging System',product:'USGS controlled daytime and nighttime IR mosaics',provider:'USGS Astrogeology',
  dataType:'Historical thermal infrared mosaic layers',format:'Use the catalog asset and label for format and calibration.',
  resolution:'100 m/pixel for the cited USGS controlled products',crs:'Inspect each controlled tile metadata.',
  coverage:'Cited controlled day/night products cover the ±65° latitude region. Verify exact layer footprint.',
  temporal:'Historical composites, separated by day/night observation conditions',processingLevel:'Controlled orthoprojected mosaics',
  availability:'USGS catalog published',accessMethod:'Discover controlled tiles and related documentation from the provider catalog.',
  limitations:'IR brightness is contextual and neither elevation nor a present-time surface-temperature forecast.',
},[sources.themis],geo,'P2','Optional')

dataset('hirise-stereo','HiRISE stereo DTMs','MRO · regional stereo','Discover published stereo DTMs independently from image coverage. The existing Jezero product is a specific example, not a template for coverage or quality.',{
  mission:'Mars Reconnaissance Orbiter',instrument:'HiRISE',product:'Published HiRISE stereo DTM and associated ortho records',provider:'HiRISE operations / NASA PDS',
  dataType:'Stereo-derived elevation and associated ortho context',format:'Inspect DTM IMG/label or distributed derived GeoTIFF.',
  resolution:'Provider describes typical 1–2 m post spacing. Use actual label per product; post spacing is not resolved detail.',
  crs:'Read each asset’s projection, body radii and elevation reference.',coverage:'Selected stereo footprints; regional availability is incomplete.',
  temporal:'Product-specific stereo acquisitions and processing release',processingLevel:'Stereo-derived terrain',
  availability:'Published DTM inventory; region coverage TBD',accessMethod:'Query by footprint and verify both selected asset and label.',
  limitations:'Examine seams, artifacts, native valid pixels and independent control.',
},[sources.hirise,sources.quality])

dataset('ctx-stereo','CTX stereo DTMs','MRO · regional elevation','Find regional CTX stereo elevation products when available. Evaluate their evidence separately from the 5 m optical mosaic and from fine HiRISE DTMs.',{
  mission:'Mars Reconnaissance Orbiter',instrument:'Context Camera',product:'Published regional CTX stereo terrain assets',provider:'NASA/USGS and product-specific investigators',
  dataType:'Stereo elevation',format:'Product-specific raster plus labels',resolution:'Product-specific; no regional or universal default.',
  crs:'Verify label, horizontal/vertical reference and units.',coverage:'Selected stereo footprints; optical coverage does not imply DTM coverage.',
  temporal:'Product-specific',processingLevel:'Derived stereo terrain',availability:'Archive and published examples; per-region assets TBD',
  accessMethod:'Discover in PDS/USGS indexes or curated citations and confirm file and metadata.',
  limitations:'Use for mapping or regional recon when native evidence cannot support detailed routing.',
},[sources.ode,sources.quality])

dataset('hrsc-stereo','HRSC terrain & ortho','ESA Mars Express · regional','Candidate partner terrain and ortho data. Evaluate tile or strip identity, masks, vertical reference and registration for each selected region.',{
  mission:'Mars Express',instrument:'High Resolution Stereo Camera',product:'ESA HRSC map-projected products',provider:'ESA Planetary Science Archive / HRSC team',
  dataType:'Stereo-derived elevation and mapped imagery (separate asset roles)',format:'Use the chosen ESA archive label and data object.',
  resolution:'Product-dependent. Do not substitute imagery sampling for DTM resolution.',crs:'Read HRSC map and vertical metadata per asset.',
  coverage:'Product-specific or mosaic-specific; no assumed coverage for the candidate set.',
  temporal:'Archived observations and product versions',processingLevel:'Select appropriate map-projected data product',
  availability:'ESA archive and PDS access documentation',accessMethod:'Discover in ESA PSA or PDS mirror; pin product version.',
  limitations:'Regional scientific context only until terrain support and quality pass the declared objective gates.',
},[sources.hrsc,sources.hrscAccess],geo,'P1')

dataset('regional-optical','Regional optical products','HiRISE / CTX · image & ortho','Distinguish the raw observation, projected or orthorectified product and derived mosaic in the registry. Prefer verified orthorectified assets for regional overlays.',{
  mission:'Mars Reconnaissance Orbiter',instrument:'HiRISE and CTX',product:'Candidate optical observations, orthorectified images and regional mosaics',
  provider:'NASA PDS / instrument teams / USGS',dataType:'Optical image intensity',format:'Product-specific imagery and labels',
  resolution:'Asset-specific native and delivered pixel spacing',crs:'Check projection and distortion treatment per asset.',
  coverage:'Selected regions and footprints',temporal:'Source-specific acquisition and release',processingLevel:'Record observation vs projected image vs ortho vs mosaic',
  availability:'Catalog queries supported; exact regional assets TBD',accessMethod:'Search PDS/ODE or pinned product catalogs; inspect selected source and metadata.',
  limitations:'Separate image pixel spacing from terrain, positional accuracy and scientific feature confidence.',
},[sources.ode,sources.hirise])

dataset('mars-geology','Geologic Map of Mars','USGS SIM 3292 · interpreted','Use the published global map for regional context and atlas overlays. Supplement with cited regional mapping as available, preserving mapping scale and unit provenance.',{
  mission:'Planetary geologic mapping compilation',instrument:'Multiple source datasets',product:'USGS Scientific Investigations Map 3292',
  provider:'USGS / NASA',dataType:'Interpreted geology and map units',format:'Published map and GIS database',
  resolution:'Published scale 1:20,000,000',crs:'Published sheet uses Robinson, with polar insets; inspect GIS asset CRS separately.',
  coverage:'Global thematic context',temporal:'2014 map release',processingLevel:'Published geological interpretation',
  availability:'Map, metadata and database published',accessMethod:'Pin published database, documentation and applicable attribution.',
  limitations:'Map units have scale-dependent boundaries and no implied fine terrain suitability.',
},[sources.geology],science,'P0','Interpretation')

dataset('crism-archive','CRISM targeted products','MRO · spectral cubes','Use targeted derived spectral products and published interpretations when they support a specific objective. Keep source observations and inferred mineralogy as separate lineage records.',{
  mission:'Mars Reconnaissance Orbiter',instrument:'CRISM',product:'TER / map-projected MTRDR',provider:'NASA PDS Geosciences Node',
  dataType:'Processed hyperspectral observations; interpretation separate',format:'PDS product objects and labels',
  resolution:'Read native sampling and mapped grid from selected product.',crs:'Check projection and geometry for selected MTRDR.',
  coverage:'Targeted, incomplete coverage',temporal:'Historical acquisition and processing versions',processingLevel:'Targeted Empirical Record or Map-Projected Targeted Reduced Data Record',
  availability:'Archive verified; regional asset TBD',accessMethod:'Use PDS index, product labels and published interpretation.',
  limitations:'Use quality flags and cite processing limits. No inferred mineral distribution across unsampled regions.',
},[sources.crism],science,'P2','Optional')

dataset('curiosity','Curiosity observations','MSL · imagery & PLACES','Associate Gale-area observations, images, science records and rover poses with objectives when spatially relevant. Region evaluation does not require rover history.',{
  mission:'Mars Science Laboratory',instrument:'Mission cameras and science instruments; PLACES localization',
  product:'MSL PDS instrument archives and PLACES products',provider:'NASA PDS',
  dataType:'Historical mission evidence and localization',format:'Archive-specific images, tables and labels',
  resolution:'Product-specific; rover imagery is not a common map raster.',crs:'Resolve each rover frame, pose and published location reference.',
  coverage:'Mission observations and traverse in Gale; no extrapolation to other regions.',temporal:'By sol, observation and archive release',
  processingLevel:'Archive-specific observations, derived records and localization',
  availability:'NASA PDS mission archive',accessMethod:'Select relevant records by product ID, sol and locality.',
  limitations:'Rover pose, observed feature and hypothetical crew approach are distinct.',
},[sources.msl],science,'P1','Observation')

add('discover','discovery','Catalog discovery','PDS ODE · PSA · curated links','Query archives by body, region, mission, time and product family. Capture catalog snapshots and citations. Allow manual input for published records and datasets without machine-readable footprints.','§5 · Asset discovery',geo,{references:[sources.ode,sources.hrscAccess]})
model('footprint-index','discovery','Coverage index','Mars footprints · spatial index','Index normalized footprints and intersect candidate boundaries, including wrapped and polar regions. Preserve footprint precision, product quality flags and unknown geometries.','§5 · Spatial coverage',geo,
  'Validate polygon topology. Split seam-crossing geometries in the canonical domain and use a Mars-aware area strategy for overlap. Track footprint overlap separately from post-acquisition pixel support.',
  'Footprints can overstate usable coverage. No footprint may mean unknown, rather than no data.',
  'Test antimeridian and polar intersections, invalid polygons, mixed coordinate references and unknown states.',[
  p('coverage area method','method','','Select an area calculation appropriate to the AOI and Mars body.','Document seam handling, area units and denominator.'),
],{ notes:'P0 can use curated footprints and manual overlap review. Automated seam/polar area calculations and richer indexing are P1.',inputs:[v('native footprints','geometry[]','degrees','registry','Pinned catalog footprints with original coordinate conventions.')],outputs:[v('overlap candidates','coverage records','m² or fraction','availability','Geometry overlap, denominator and limitations.')],priority:'P0' })
add('asset-select','discovery','Select pinned assets','Objective · role · version','Select by required product role, coverage, support, accuracy evidence, suitability, integrity and access. Reuse the same asset key across regions and keep source/derivative relationships. Keep global context or alternate products explicit when a required source is missing.','§5 · Asset selection',shared,{
  inputs:[v('candidates','asset references','','footprint-index','Candidate assets with footprint/quality metadata.'),v('investigation scope','region review','','prioritize','Selected region, scientific objective and required data roles.',false)],
  outputs:[v('asset plan','manifest','','retrieve','Versioned input IDs, required/optional roles, retrieval strategy and fallbacks.')]
})

add('raw-cache','ingest','Original assets & labels','Read-only · content keyed','Retain retrieved bytes, original file names, archival labels, retrieval URI and date. Keep raw assets separate from analytical outputs. Support a local cache and local file import with equivalent lineage.','§6 · Acquisition',geo,{category:'Storage artifact'})
add('quarantine','ingest','Quarantine & retry','Explicit asset failures','Quarantine corrupt, unreadable or unsupported objects. Report missing assets, checksum mismatch, missing labels and exhausted access fallbacks with source and region IDs. Retry an alternate verified source or continue without optional layers.','§6, §14 · Failure handling',geo,{classification:'Decision'})

add('mars-reference','spatial','Mars reference definitions','Body · frame · vertical reference','Record target body, reference figure and radii, frame/version, prime meridian, latitude type, longitude direction and domain, axes, angular/linear units and vertical quantity/reference for each asset.','§7 · Mars reference',geo,{references:[sources.marsCrs,sources.marsProj]})
model('planetary-normalize','spatial','Planetary normalization','Canonical Mars longitude / latitude','Normalize verified source geometry for planetary discovery and atlas display. Preserve the original coordinates and transform record, and represent wrapped/polar geometry explicitly.','§7 · Planetary coordinates',geo,
  'Use the proposed planetocentric, east-positive convention in a declared longitude domain. Convert planetographic latitude only with verified body parameters. Split wrapped bounds; select explicitly defined polar handling. Keep native elevations in their declared vertical reference until an approved transform exists.',
  'Angular coordinates are not a routing metric. Refuse unresolved horizontal, planetary or vertical transforms where required.',
  'Check known controls, west-to-east and latitude-type conversions, axis order, round trips and seam/pole fixtures.',[
  p('planetary axis convention','enum','degrees','Proposed indexing convention; preserve native axis metadata.','Declare frame, planetocentric latitude and east-positive longitude.','planetocentric / east-positive','Assumption'),
  p('longitude domain','enum','degrees','Proposed index representation.','Use seam-aware geometry and preserve the native domain.','[-180, 180)','Assumption'),
],{references:[sources.marsCrs,sources.marsProj],inputs:[v('native reference','CRS record','','mars-reference','Body, frame, conventions and vertical metadata.')],outputs:[v('index geometry','geometry','degrees','footprint-index','Normalized geometry with transform provenance.')]})
add('verify-transform','spatial','Verify Mars transforms','Independent controls · geodesics','Validate planetary and local transforms with round trips, known control, independent Mars body distances and domain checks. Confirm units, axis order, raster origin, row direction and pixel centers. Stop on unresolved discrepancies.','§7 · Transform integrity',geo,{category:'Validation',references:[sources.marsProj]})

model('atlas-topography','atlas','Elevation & derived relief','MOLA · contextual raster','Prepare global elevation context using the actual topography quantity and preserve count/coverage metadata. Generate a separately identified hillshade or relief layer.','§8 · Global topography',geo,
  'Align selected MOLA grids for display with the declared planetary reference. Keep analytical source values separate from rendering. Generate illumination as a derived display parameter.',
  'Relief imagery is derived display context. Neither global grid spacing nor rendered shading establishes local walkability.',
  'Check units, vertical reference, grid orientation, polar cutoffs, counts and masked areas.',[
  p('relief styling','config','','Set relief illumination or choose alternate relief rendering.','Record styling as a display derivative.'),
],{inputs:[v('MOLA topography','raster','m','mola-megdr','Use the labeled topography band and matching support metadata.')],outputs:[v('elevation and relief layers','rasters','','atlas-manifest','Separate elevation and rendered relief records.')]})
add('atlas-imagery','atlas','Planetary display tiles','CTX · tiled overviews','Use a precomputed hierarchical tile pyramid as the proposed display strategy. Prepare selected lower levels and optional detail subsets using the published optical tiles. Keep analytical raster originals separate and label gaps, polar coverage and scale.','§8 · Global imagery',geo,{
  notes:'Tile matrix, zoom range, polar display strategy and encoding TBD. COG or raster overviews may be useful preprocessing artifacts; the browser should request bounded display assets. Use separately identified MOLA relief or independently verified polar imagery where the optical mosaic is unavailable.',
  inputs:[v('CTX optical tiles','raster[]','','ctx-mosaic','Pinned V01 optical input assets.'),v('optional IR context','raster[]','','themis-ir','Separate thermal channels if included.',false)],
  outputs:[v('pyramid and mask','display artifacts','','atlas-manifest','Tile scheme, levels, footprint, layer metadata and supported local subset.')]
})
add('atlas-overlays','atlas','Planetary science overlays','Geology · missions · region index','Prepare display-scale geology, mission sites, candidate region boundaries and dataset footprints. Attach source links, thematic scale and geography. Represent missing products and seam/polar clipping explicitly.','§8 · Global scientific layers',science)
add('atlas-manifest','atlas','Global atlas contract','Layer manifest · multi-resolution','Publish a versioned layer inventory with basemap, elevation context, separate relief, science overlays, region index and coverage. Each layer records asset IDs, CRS, bounds, native sampling, display levels, attribution and local availability.','§8, §15, §18 · Atlas contract',shared,{
  category:'Storage artifact', outputs:[v('atlas_manifest','versioned object','','map','Layer inventory, footprints, artifact locations, credits and offline subset.')]
})
add('atlas-offline','pack','Publish offline atlas subset','Versioned manifest · selected levels','After release checks, distribute a coarse planetary basemap and explicitly selected display detail, overlays and search index. Declare present layers and tile ranges. Keep unavailable detail discoverable in metadata, and keep NASA archive access in build-time tools.','§8, §15 · Offline atlas',shared,{category:'Storage artifact'})

add('region-registry','regions','Candidate region registry','Arbitrary records · 56 under study','Create stable region records with name, normalized boundary, geographic description, scientific objectives, mission history, candidate assets, coverage/quality, constraints, readiness and evaluation state. The current 56 candidates are a research cohort. Load actual records when supplied.','§9 · Region registry',science,{
  category:'Storage artifact', notes:'Suggested versioned local JSON or tabular source + explicit geometry/CRS. Persist assessment revisions and citations; 56 is not a schema limit.',
  outputs:[v('region_record','versioned record','degrees','region-job','ID, boundary + CRS, objective IDs, lineage, evaluation states and links to evidence.')]
})
model('availability','regions','Assess data availability','Coverage · support · access','Assess per-region elevation, optics, coverage, terrain resolution, geology, observations, accessibility and coordinate evidence. Keep each role and verification state explicit.','§9 · Availability',geo,
  'Evaluate footprint first, then distinguish catalog match, byte access, supported data, resolution and alignment where evidence exists. Represent unknown, absent, partial, available and not applicable separately. Cite candidate asset IDs and denominator.',
  'Do not treat remote footprints as validated terrain support or lack of mission imagery as a failure for all objectives.',
  'Test missing footprints, partial overlap, regional imagery without elevation, inaccessible assets and no rover history.',[],
  { inputs:[v('region','region record','','region-registry','Normalized AOI and required roles.'),v('overlap candidates','coverage records','','footprint-index','Footprint overlap and uncertainty.')],outputs:[v('availability assessment','criterion records','','rank-regions','Independent role-based availability with evidence and uncertainty.')] })
model('science-value','regions','Assess scientific value','Researcher review · citations','Capture the research question, geological diversity or processes, field-observation value, published context and a qualitative rationale. Distinguish measured evidence, interpretation and researcher judgment.','§9 · Scientific value',science,
  'Use researcher-authored rubric definitions and citations, optionally provisional ordinal assessments with a stated rubric version. Record disagreements and review status.',
  'Scientific significance is independent from asset availability or likely ease of processing.',
  'Require citations, rationale, review state and evidence class. Allow qualitative evidence and unknown ratings.',[
  p('science rubric','versioned rubric','','Provisional criteria and evidence requirements.','No fabricated ratings or required numerical score.'),
],{ classification:'Interpretation',outputs:[v('scientific assessment','review record','','rank-regions','Criterion assessments, citations and rationale.')] })
model('regional-suitability','regions','Assess processing suitability','Objective · overlap · constraints','Estimate suitability for further processing by required product overlap, native terrain evidence, target support, difficulty and uncertainty. Record flags and investigate potential routes only after processing.','§9 · Suitability',shared,
  'Summarize evidence-backed constraints against per-objective requirements; flag blockers separately from unknowns. Keep map-only or regional-analysis outcomes possible.',
  'This is investigation triage. Final route support requires asset-level terrain and downstream QA.',
  'Check a high-science region with no DTM, accessible good terrain with weak evidence, and ambiguous coordinate metadata.',[],
  { outputs:[v('suitability assessment','criteria and blockers','','rank-regions','Provisional processing recommendation and unresolved evidence.')] })
model('rank-regions','regions','Prioritize candidate regions','Editable criteria · provisional','Define a configurable multi-criteria decision model that consumes separate availability, scientific-value and suitability records. Retain qualitative rationale and missingness.','§9 · Ranking',science,
  'Proposed weighted rubric with versioned criterion definitions and explicit missing-data policy. Require review before a shortlist is approved. Keep unscored cases identifiable, and preserve rationale for overrides and ties.',
  'No finalized weights or rankings are supplied. Prioritization does not confer Marswalk eligibility or select paths.',
  'Compare rubric versions, missing criteria, equal assessments, sensitivity to weights, and reviewer overrides with rationale.',[
  p('criteria and weights','versioned config','','Separate availability, science and feasibility criteria.','Weights and normalization must be reviewed; no default values supplied.'),
  p('missing-data policy','enum','','Define abstention, flagged partial comparison or qualitative review.','Never silently replace unknown with zero.'),
  p('ranking version','identifier','','Pin method, rubric and assessment versions.','New rubric means a new ranking revision.'),
],{priority:'P1',classification:'Assumption',inputs:[
  v('availability assessment','criterion records','','availability','Per-layer access, coverage and limitations.'),
  v('scientific assessment','review record','','science-value','Citations and research rationale.'),
  v('suitability assessment','criterion records','','regional-suitability','Processing risks and blocking evidence gaps.'),
],outputs:[v('provisional shortlist','ranked or qualitative records','','prioritize','Rubric version, review flags and missingness.')]})
add('prioritize','regions','Select regions for investigation','Research decision · independent gate','Approve a scoped region investigation from the shortlist or documented qualitative review. Send its requirements to detailed asset selection and processing. Include mapping-only outcomes, and delegate final readiness to G7.','§9 · Regional selection',shared,{classification:'Decision'})

add('region-job','prep','Regional processing job','Region ID · pinned configuration','Make a reusable, reproducible job for a selected region, including boundary with CRS, selected assets, processing configuration, science objectives and required output capabilities. Retain optional omissions and blockers.','§10, §18 · Regional processing config',shared,{
  inputs:[v('region_record','versioned record','','region-registry','Stable ID, normalized AOI, evidence and objectives.'),v('asset_plan','manifest','','asset-select','Versioned inputs with roles and fallbacks.'),v('build_config','configuration','','build-config','Tool versions, spatial policy and quality criteria.')],
  outputs:[v('regional_job','job manifest','','aoi','Region, boundary, selected assets, local target frame, requested outputs and config ID.')]
})
add('regional-dtm','terrain','Select regional DTM','Stereo products · usable support','Pick the best traceable terrain candidate for the analytical objective. Verify native spacing, real resolved detail, reference, masks, seam/quality evidence and available coverage. Keep coarse reconnaissance separate and withhold detail when no asset qualifies.','§10–11 · DTM selection',geo,{references:[sources.quality]})
model('terrain-crop','terrain','Extract & align terrain','Metric crop · kernel buffer','Read the chosen DTM window plus buffer, crop to the regional reference, preserve native masks and transform provenance, and verify actual usable support before analysis.','§10 · Terrain extraction',geo,
  'Capture requested/actual bounds and native metadata. Apply a documented reprojection/resampling method, keeping validity and stencil support conservative. Keep unobserved and edge areas explicit.',
  'Resampling does not recover absent elevation or improve source resolving power.',
  'Test partial crops, boundaries, unequal spacing, seams, pixel centers and unresolved vertical references.',[
  p('kernel buffer','configuration','native cells','Choose a buffer appropriate to the gradient stencil and resampling method.','Complete native support required for routed cells.'),
],{inputs:[v('pinned DTM','raster + label','m','regional-dtm','Validated source product and native masks.'),v('local reference','CRS + grid','m','projection','Approved regional horizontal and vertical conventions.')],outputs:[v('native-supported terrain','raster and masks','m','elevation','Local crop with native scale, support and transformation records.')]})
model('optical-prepare','prep','Prepare regional imagery','Crop · register · display levels','Select appropriate optical or ortho products, crop and transform to the regional frame, inspect seams and compare landmarks, then generate display imagery with exact bounds and layer metadata.','§10 · Optical branch',geo,
  'Keep source, analytical and display resolution distinct. Record resampling and output bounds. Check alignment before handing overlays to the integrated pack.',
  'Visual registration cannot validate terrain or guarantee fine target location.',
  'Inspect landmarks and coverage, reject failed alignment, and record native and delivery spacing.',[
  p('display resampling','method','','Choose an imagery-appropriate method.','Do not apply imagery resampling to validity masks or categorical geology.'),
],{outputs:[v('regional imagery','display raster + metadata','','display-files','Local bounds, native/display sampling and validity.')]})
add('geology-prepare','prep','Prepare geology overlay','Clip units · preserve attribution','Select scale-appropriate geology and published interpretations; import vector or categorical raster, transform and clip, preserve unit IDs, descriptions, original scale and attribution. Maintain CRS and uncertainty metadata.','§10 · Geology branch',science,{
  classification:'Interpretation',outputs:[v('geology overlay','features or categorical raster','','display-files','Unit IDs, attributes, scale, boundaries, citations and transform.')],
  notes:'Preserve categorical classes during transformation; do not convert interpretations into traversability penalties.'
})
add('routing-inputs','terrain','Baseline routing inputs','Grid geometry · masks · policy','Specify immutable input elevation, Boolean validity and exclusion masks, optional native-screen derivative, affine, CRS and config ID. Distinguish policy assumptions from measurements. The runtime constructs the directed graph and applies closure geometry without rebuilding source data.','§11, §18 · Terrain contract',geo,{
  category:'Storage artifact',
  inputs:[v('elevation','float32 raster','m','elevation','Analytical grid, mask and source spacing.'),v('support','Boolean raster','','coverage','Validated complete support; retain nodata separately.'),v('screen policy','rule + mask','','screen','Versioned assumed constraints, independent from native slope measurement.')],
  outputs:[v('baseline grid package','contract','m','terrain-file','Matched shape, row/column and easting/northing conventions, units, valid/screen arrays and native resolution.')],
  notes:'Local planar [easting,northing] in metres; raster [row,col]; explicit affine and north-up assumptions. Closures are separately validated runtime inputs.'
})

add('science-objectives','evidence','Objectives & feature registry','Citations · local science intent','Record research questions, relevant geological feature IDs, evidence requirements and expected observations. Keep interpreted feature geometry, mapping scale and positional uncertainty separate from observed events and from proposed targets.','§12 · Objectives and features',science,{classification:'Interpretation'})
add('observation-discover','evidence','Retrieve science evidence','Orbital · publications · surface','Select observations or publications tied to regional objectives. Retrieve media and metadata by pinned ID; record citations, acquisition or sol, rights, instrument, quality flags and native location references. Accept absence of rover history.','§10, §12 · Observation discovery',science)
model('evidence-quality','evidence','Classify evidence quality','Provenance · uncertainty · support','Assess whether a georeferenced observation supports a particular claim. Keep source resolution, positional uncertainty, observation quality, evidence class and reviewer notes separate.','§12–14 · Evidence quality',science,
  'Trace the original data, verify location interpretation, and document a defensible feature association with citations. Use explicit observed, derived, interpreted, assumed and simulated classes as applicable.',
  'Unknown quality or insufficient evidence blocks the affected science claim. Spatial proximity alone does not establish association.',
  'Check records without rover imagery, approximate positions, unsupported associations, missing provenance and unresolved frames.',[],
  { outputs:[v('reviewed observations','observation records','','science-target','Source ID, native and local location, uncertainty, feature link, quality and limitations.')] })
model('science-target','evidence','Define science targets','Observed feature ≠ proposed station','Associate a reviewed feature or supported location with a hypothetical observation target. Define one or more distinct candidate crew approaches and identify unsuitable or unverified positions.','§12 · Target definition',science,
  'Keep stable IDs for historical observation, interpreted feature, candidate target and approach station. Confirm a candidate station against supported local terrain and record uncertainty. Do not move an invalid station silently.',
  'A rover pose is evidence about mission history, not a safe or admissible crew waypoint.',
  'Check IDs, source evidence, geometry, grid support, objectives and invalid or out-of-bounds stations.',[],
  { outputs:[v('science targets','target and approach records','m','science-task','Separate target/approach geometry, uncertainty, supporting evidence and validation status.')] })
add('science-task','evidence','Science task contract','Objective · evidence · artifact','Define proposed observation type, region/objective, target and validated approach references, required evidence/data, expected output, dwell assumption, priority and limitations. Runtime later decides whether an admissible task fits.','§12, §18 · Science task contract',science,{
  category:'Storage artifact',classification:'Assumption',
  inputs:[v('candidate target and approach','target record','m','science-target','Keep historic and hypothetical positions distinct.')],
  outputs:[v('task_record','station and task specification','','stations-file','Objective, expected artifact, dependencies, citations, dwell units, priority and limitations.')],
  parameters:[p('planned observation duration','number','minutes','Task-specific assumed field dwell.','Record source/rationale and convert to seconds at the runtime API boundary.')]
})

model('integrate','quality','Cross-layer integration','Bounds · alignment · cell indexing','Merge independently processed terrain, imagery, geology and evidence into a consistent regional manifest. Preserve each native scale, analytical/display resolution, valid support, common geography, orientation and quality.','§13 · Integration',shared,
  'Compare affine, orientation, cell centers, extent, aligned controls and coverage intersections. Verify target and station IDs and document residual uncertainty without silently shifting a product.',
  'Layer agreement is relative to verified references and distinct source scales. Incompatible products remain unresolved or omitted.',
  'Cross-check independent controls and reported tolerances; verify that no unsupported pixels or invalid stations enter routing.',[
  p('alignment tolerance','configuration','m','Set per asset pair, objective and supported scale.','No universal positional tolerance; record policy and independent measurements.'),
],{inputs:[
  v('terrain baseline','grid and masks','m','routing-inputs','Optional for map-only releases.',false),
  v('imagery','display raster','','optical-prepare','Aligned imagery and coverage.',false),
  v('geology','overlay','','geology-prepare','Thematic metadata and map scale.',false),
  v('scientific task records','record[]','','science-task','May be unavailable for some objectives.',false),
],outputs:[v('integrated candidate','staged regional artifacts','','g7-readiness','Versioned coverage, per-layer resolutions, evidence and unresolved findings.')]})

type GateSeed = [id: string, code: string, name: string, stage: string, purpose: string, acceptance: string, failure: string, upstream: string, downstream: string, owner: string]
const gates: GateSeed[] = [
  ['g1-integrity','G1','Source integrity','Acquisition','Check selected sources, bytes and labels.','Required asset identity and checksum or recorded verification agree; readable archive and label pair.','Quarantine and retry a verified source, or record an optional omission.','raw-cache','quarantine',geo],
  ['g2-coordinate','G2','Metadata & coordinates','Spatial reference','Check metadata and coordinate interpretation.','Mars body/reference, axes, angular/linear and vertical conventions resolved with control checks.','Reject unresolved assets or transforms. Never silently shift a layer.','verify-transform','integrate',geo],
  ['g3-coverage','G3','Geographic coverage','Acquisition / regional preparation','Check actual coverage against objective and AOI.','Valid footprint and denominator recorded, including native-pixel support and required overlap.','Report gap, restrict declared coverage or select a verified alternative. No unsupported routing.','terrain-crop','g7-readiness',geo],
  ['g4-terrain','G4','Terrain resolution & support','Terrain preparation','Verify DTM and analytical support.','Declared native detail and quality evidence support the objective. Routing cells have valid source support and verified masks.','Withhold routing and retain map/analysis capability if independently valid. No fine-grid fabrication.','routing-inputs','g7-readiness',geo],
  ['g5-alignment','G5','Cross-layer alignment','Integration','Verify geographic consistency and grid alignment.','Independent controls and recorded tolerance pass for required layers; extent, affine, orientation, cells and coordinates agree.','Reject or omit the affected layer, invalidate affected stations and record the reason.','integrate','g7-readiness',shared],
  ['g6-evidence','G6','Observation provenance','Evidence review','Verify attribution, geography and support for each claim.','Stable source IDs, citation, observation/interpretation distinction and location uncertainty retained; proposed station checked independently.','Withhold unsupported claim or task, mark invalid station, retain supported context.','evidence-quality','g7-readiness',science],
  ['g7-readiness','G7','Regional readiness','Pre-publication capability review','Classify release capability independently of the candidate ranking.','Route support requires relevant coordinate, coverage, terrain and integration gates. Tasks additionally need evidence and valid stations. Mapping and regional analysis have separate declared requirements.','Publish only independently validated capabilities, otherwise block release. Record failed, unknown and inapplicable checks.','integrate','capability-report',shared],
  ['g8-schema','G8','Output schema','Release validation','Validate atlas and site-pack contracts.','Declared schema supported; required keys, units, IDs, bounds, masks and references check out for enabled capabilities.','Reject incompatible output and rebuild or migrate with a documented version.','manifest','pack-check',shared],
  ['g9-package','G9','Package integrity','Release validation','Verify artifact content and declared hash.','Referenced artifacts present with matching checksums, versions, byte identity and access rights.','Withhold the corrupted or incomplete release; rebuild immutable output.','manifest','pack-check',shared],
  ['g10-runtime','G10','Runtime compatibility','Release smoke check','Check the intended runtime against staged atlas and pack.','Local loader can read the declared schema, layer coordinates, shapes, bounds, capability flags and optional omissions without live archive calls.','Reject incompatible release or disable its unsupported capability with a visible reason.','manifest','pack-check',shared],
]
for (const [id,code,name,stage,purpose,acceptance,failure,upstream,downstream,owner] of gates) {
  const output = id === 'g7-readiness' ? 'Capability decision + gate report' : 'Versioned gate report + evidence, findings and affected capability'
  const gate: Gate = { code,stage,acceptance,failure,result:'Not evaluated',output }
  add(id,'quality',code+' · '+name,stage,purpose,'§14 · Validation gates',owner,{
    category:'Validation',gate,
    notes:'Each build records its own gate result for the artifact and capability being evaluated. This seed contains no measured outcomes.',
    inputs:[v('artifact and evidence','versioned artifact references','',upstream,'Identity, required policy, source versions and evidence used by the gate.')],
    outputs:[v('gate report','structured finding','',downstream,output)],
  })
}

add('capability-report','quality','Capability & failure report','Map · analysis · routing','Publish separate flags for map availability, regional analysis, terrain routing and task availability. Record passed, failed, not evaluated and not applicable by gate and capability. Required checks must pass before enabling a capability. Unknown is distinct from failure and applicability.','§14, §23 · Failure policy',shared,{
  category:'Storage artifact',classification:'Decision',notes:'Missing dataset, unreadable asset, invalid CRS, coverage gap, unsupported resolution, failed alignment, insufficient evidence, invalid station and incompatible schema are explicit failure reasons.',
  outputs:[v('quality report','versioned report','','manifest','Affected asset/region/capability, gate outcomes, omitted layers, evidence and remediation.')]
})
add('pack-registry','pack','Regional pack registry','Many regions · pinned versions','Index immutable region ID, pack ID/version, layer availability, build date, gate status, routing readiness, sources, location and hash. A new configuration yields a new pack rather than overwriting a release.','§15 · Multi-region management',shared,{
  category:'Storage artifact',
  outputs:[v('pack_record','versioned registry entry','','loader','Package path, integrity, schema, validation status, layer and routing capability.')]
})
add('build-config','provenance','Versioned build configuration','Tools · policies · thresholds','Freeze region selection, source versions, body/CRS policy, resampling, masks, terrain assumptions, target criteria, quality tolerances and dependency/tool versions. Record a change as a new build identity.','§16 · Reproducibility',shared,{
  category:'Storage artifact',classification:'Assumption',
  outputs:[v('build_config','versioned configuration','','region-job','Source pins, tool versions, transforms, thresholds and output policy.')]
})
add('lineage','provenance','Transformation & lineage ledger','Inputs → methods → outputs','Link original product IDs and hashes to derived artifacts through versioned operations. Record source and destination references, resampling, masks, execution identity, parameters, checksums, attribution and quality evidence.','§16, §18 · Provenance contract',shared,{
  category:'Storage artifact',
  inputs:[v('source record','catalog and retrieval record','','registry','Pinned metadata, original labels and attribution.'),v('build configuration','versioned configuration','','build-config','Deterministic policy, tool versions and assumptions.')],
  outputs:[v('lineage report','versioned provenance record','','manifest','Input/output IDs, operations, config and tool versions, transforms, hashes, attribution and gate reports.')]
})
add('pipeline-deferred','provenance','Deferred capabilities','P3 · explicit scope limit','Global meter-scale routing, automated safety certification, unvalidated hazard prediction, global high-resolution reconstruction, AI/ML and distributed processing infrastructure are deferred.','§22–24 · Priorities and scope',shared,{category:'Annotation',priority:'P3',classification:'Excluded'})

const patches: Record<string,Partial<Component>> = {
  registry:{groupId:'discovery',name:'Versioned source registry',description:'Normalize shared asset keys, provider, mission, instrument, product ID/version, acquisition and processing level, scientific role, format, access, footprint, CRS, units, native spacing, limitations and verification. Store source/derived dependencies, provenance, credit and license. Multiple regions reference the same asset record.',owner:geo},
  retrieve:{description:'Choose full download, distributed tile, verified windowed read or local import/cache per asset. Check advertised and actual range behavior and media type. Fall back to published tiles or complete local sources, then quarantine if required bytes cannot be acquired. Record original checksums, URIs and retrieval dates.',owner:geo},
  readers:{description:'Use GDAL/Rasterio for supported rasters and Fiona/GeoPandas for vector data where useful. Inspect PDS/XML, native labels and archive members. Preserve scale/offset, unit, nodata, quality, CRS and provenance. Unreadable formats and invalid labels are explicit ingestion failures.',owner:geo},
  'source-gate':{description:'Inspect retrieved products, labels, native units, spatial metadata, masks, checksum, extent, resolution and access rights. Record each problem and route to the relevant gate or quarantine. Catalog availability alone cannot pass acquisition.',owner:geo},
  aoi:{groupId:'prep',name:'Regional bounds & analysis grid',technology:['Validated AOI · local grid spec'],description:'Derive a region-specific crop, buffer, desired output capabilities and analytical grid plan from the job. Keep declared planetary geometry and local metric geometry. AOI size and grid spacing depend on the source, objective and coverage; the original Jezero crop is a reference case.',owner:geo,status:'proposed'},
  projection:{groupId:'spatial',name:'Regional metric projection',technology:['pyproj · region-specific metres'],owner:geo,
    description:'Select a verified local metric frame from the declared Mars reference and AOI; validate distortion, pole and longitude-wrap behavior and vertical compatibility. Near-site equirectangular remains a Jezero reference option; select a suitable alternative for polar or larger regions.',
    algorithm:{...emptyAlgorithm,name:'Region-specific Mars metric transform',family:'Planetary geospatial transformation',method:'Resolve source horizontal/vertical references; validate local easting/northing, scale, affine and control with an independent Mars calculation.',alternatives:'Local equirectangular for a bounded suitable patch; approved polar or other regional projection for different geometry.',limitations:'Stop on unresolved body, datum, scale or axis conventions.',validation:'Known controls, independent geodesics, seam and polar tests, source-to-local round trips.'}},
  elevation:{groupId:'terrain',name:'Analytical elevation grid',technology:['Native support · local metres'],owner:geo,
    description:'Prepare a metric analytical elevation grid within the validated regional crop. Record native post spacing, actual support, aggregation and delivery grid independently. The original 5 m analytical Jezero example is illustrative and is not a global grid default.',
    inputs:[v('native-supported local DTM','raster + masks','m','terrain-crop','Valid native elevations on the declared regional support.')],
    outputs:[v('analytical elevation grid','float32[rows,cols]','m','routing-inputs','Matched grid, affine, coverage and native provenance.')],
    parameters:[p('regional grid spacing','number','m','Select per region, support and objective.','Keep native resolution separate; never claim inferred detail.'),p('aggregation reducer','method','','Pin a validated representative elevation reducer.','Use distinct conservative mask and local screening aggregation.')]},
  gradient:{groupId:'terrain',owner:geo,
    inputs:[v('regional native-supported terrain','raster and stencil support','m','terrain-crop','Use native-scale elevations or explicitly documented source-grid derivative.')],
    outputs:[v('native slope','raster','degrees','screen','Native local slope independent of directed route grade.'),v('stencil support','Boolean raster','','coverage','Validity for the documented native kernel.')]},

  coverage:{groupId:'terrain',owner:geo,
    inputs:[v('native support','mask and extent','','terrain-crop','Missing-data mask and valid native support.'),v('stencil support','Boolean raster','','gradient','Complete kernel support.'),v('analytical grid','grid descriptor','m','elevation','Output grid geometry.')],
    outputs:[v('conservative validity','Boolean raster','','routing-inputs','Analytical grid cells with documented valid support.'),v('support mask','Boolean raster','','screen','Keep unknown terrain distinct from screening exclusions.')]},

  screen:{groupId:'terrain',owner:geo,
    description:'Compute terrain screen properties separately from elevation and native gradient. Apply a versioned configurable exclusion policy; record any illustrative Jezero threshold as a reference only. The policy is a prototype assumption and does not establish human safety.',
    inputs:[v('native slope','raster','degrees','gradient','Native gradient with kernel and provenance.'),v('conservative support mask','Boolean raster','','coverage','Do not screen unsupported cells as valid.')],
    outputs:[v('screening exclusion mask','Boolean raster','','routing-inputs','Versioned assumption, mask and optional retained native slope statistic.')],
    parameters:[p('slope screen threshold','number','degrees','Region/config-specific screening assumption; original 15° is illustrative Jezero only.','No platform-wide threshold and no EVA safety claim.'),p('native slope statistic','method','','Document the conservative aggregate and sampling support.','Keep original slope evidence and validity masks.')]},
  context:{name:'Regional display layer manifest',technology:['Exact local bounds · per-layer scale'],description:'Collect the independently prepared optical and geology outputs. Record native and display spacing, credits, omissions, analytical use limits and exact local bounds.',owner:shared},
  register:{groupId:'evidence',name:'Register historical observations',algorithm:{...emptyAlgorithm,name:'Source-anchored observation registration',family:'Geospatial registration and review',method:'Resolve declared mission pose frames or cited orbital and publication coordinates. Transform into the regional reference, preserve original coordinates and positional uncertainty, and record unmatched features for scientific review.',limitations:'Source geometry and uncertainty vary by mission and publication. Do not assign a crew waypoint in this step.',validation:'Check source ID, control points, declared frame, residual and propagated uncertainty.'},description:'Register native rover observations, orbital evidence and published records in the regional frame. Record source IDs, time, uncertainty, and native coordinates. Retain rover poses, observed features and hypothetical approaches as separate entities.',owner:science,
    inputs:[v('retrieved observations','evidence records','','observation-discover','May be orbital, surface or published records.'),v('local reference','metric CRS','m','projection','Declared Mars reference and transform provenance.')],
    outputs:[v('registered observations','georeferenced records','m','evidence-quality','Observation IDs, native/derived location and uncertainty.')]},
  manifest:{name:'Regional site.json',description:'Declare region_id, pack_id/version, schema version, processing date/config, pack capabilities, gate results, layer availability, bounds/CRS/vertical reference, shape/affine where terrain exists, source versions, attribution, provenance and checksums. Required payloads depend on enabled capabilities.',owner:shared},
  'terrain-file':{description:'For a pack declaring routing support, store matched float32 z_m, Boolean validity and screening masks, and optional slope on the declared local metric grid. [row,col] raster indexing and [easting,northing] coordinates follow the affine. Omit analytical terrain from display-only packs and expose the reason.',owner:geo},
  'stations-file':{description:'Store regional task IDs, objective, target, approved approach node, positional certainty, evidence IDs, dwell_s in whole seconds, priority, expected artifact and limitations. Omit invalid stations and unsupported tasks.',owner:science},
  'display-files':{owner:geo},
  'evidence-files':{owner:science},
  'pack-check':{name:'Publish immutable site pack',technology:['Schema · checksums · runtime check'],description:'Assemble staged artifacts and gate reports, enforce required checks for each enabled capability, and atomically publish a new immutable region/pack version. Emit explicit omissions and retain rejected builds for inspection.',owner:shared},
  'hirise-dtm':{name:'Jezero HiRISE DTM',owner:geo},
  'hirise-ortho':{name:'Jezero HiRISE optical mosaic',owner:geo},
  ctx:{name:'Jezero CTX fallback',owner:geo},
  geology:{owner:science}, perseverance:{owner:science}, places:{owner:science}, meda:{owner:science}, crism:{owner:science}, esa:{owner:geo},
}

const legacySourceDetails: Record<string,Pick<Dataset,'instrument'|'processingLevel'|'accessMethod'>> = {
  'hirise-dtm':{instrument:'HiRISE',processingLevel:'TRN stereo DTM mosaic',accessMethod:'USGS product catalog or indexed component TIFF/XML; confirm byte and window access.'},
  'hirise-ortho':{instrument:'HiRISE',processingLevel:'TRN orthorectified image mosaic',accessMethod:'USGS product catalog or indexed orthorectified components.'},
  ctx:{instrument:'Context Camera',processingLevel:'Jezero science terrain and optical mosaics',accessMethod:'Pin the separately labeled USGS CTX terrain and optical assets.'},
  geology:{instrument:'Photogeological interpretation based on orbital observations',processingLevel:'Published interpretation and GIS supplement',accessMethod:'Download the published GIS supplement or USGS fallback; verify the exact layer and rights.'},
  perseverance:{instrument:'Mars 2020 mission instruments and cameras; verify per observation',processingLevel:'Mission observations and interpreted sample records',accessMethod:'Pin cited NASA/JPL observation, image and sample record identifiers.'},
  places:{instrument:'Rover localization archive',processingLevel:'Historical derived rover pose and mapping products',accessMethod:'Use the PDS PLACES bundle and pin the applicable product and frame.'},
  meda:{instrument:'MEDA',processingLevel:'Historical environmental archive products',accessMethod:'Pin PDS Atmospheres product, sol/time and quality metadata.'},
  crism:{instrument:'CRISM',processingLevel:'Targeted observations / published interpretations',accessMethod:'Verify a specific archive or published derived product and its rights.'},
  esa:{instrument:'HRSC / CTX context',processingLevel:'Regional cartographic orientation',accessMethod:'ESA public reference; identify and verify source assets before reuse.'},
}

const edges: Connection[] = []
function wire(source: string,target: string,label: string,kind: Connection['kind'] = 'Data flow',contract: Partial<Connection> = {}) {
  edges.push({id:source+'--'+target,source,target,label,kind,payload:label,format:'',protocol:'Local build artifact / interface',description:'',validation:'',dependencies:[],...contract})
}
for (const asset of [...components.filter(item=>item.category === 'External dataset').map(item=>item.id),'hirise-dtm','hirise-ortho','ctx','perseverance','places','geology','meda','crism','esa']) wire(asset,'discover','Catalog record and attribution')
wire('regional-optical','ctx-mosaic','CTX contributor image lineage','Provenance',{description:'Record the actual CTX input product IDs where published; the candidate optical family alone is not a contributor list.'})
wire('discover','registry','Normalized catalog candidates')
wire('registry','mars-reference','Native labels and footprint conventions')
wire('mars-reference','planetary-normalize','Resolved Mars reference','Configuration')
wire('planetary-normalize','footprint-index','Normalized footprints','Derived product',{spatialReference:'Declared Mars geographic longitude/latitude; preserve original reference and seam handling.'})
wire('registry','footprint-index','Product IDs and candidate footprints')
wire('footprint-index','asset-select','Region overlaps and unknowns')
wire('registry','asset-select','Versioned product metadata')
wire('asset-select','retrieve','Pinned acquisition plan','Configuration',{format:'Manifest',requiredMetadata:'Product/version, role, source locator, expected bytes/hash where available, fallbacks.',failure:'Required unavailable assets block the dependent job; optional assets may be omitted.'})
wire('retrieve','raw-cache','Original bytes and labels')
wire('raw-cache','readers','Read-only source assets')
wire('raw-cache','g1-integrity','Integrity evidence','Validation')
wire('g1-integrity','quarantine','Corrupt or missing asset','Validation')
wire('readers','quarantine','Unreadable assets or labels','Validation')
wire('readers','mars-reference','Native label and coordinate metadata')
wire('source-gate','verify-transform','Required coordinate and unit checks','Validation')
wire('planetary-normalize','verify-transform','Planetary transform candidate','Validation')
wire('projection','verify-transform','Regional transform candidate','Validation')
wire('verify-transform','g2-coordinate','Controls and transform findings','Validation')
wire('g2-coordinate','terrain-crop','Verified Mars coordinate evidence','Validation')
wire('g2-coordinate','atlas-manifest','Validated planetary reference','Validation')
wire('g2-coordinate','integrate','Accepted reference / rejected assets','Validation')
wire('planetary-normalize','atlas-topography','Planetary elevation alignment')
wire('planetary-normalize','atlas-imagery','Planetary image alignment')
wire('planetary-normalize','atlas-overlays','Normalized overlay geometry')
wire('mola-megdr','atlas-topography','MOLA topography product role','Configuration')
wire('ctx-mosaic','atlas-imagery','Pinned optical product role','Configuration')
wire('themis-ir','atlas-imagery','Optional IR context','Configuration')
wire('mars-geology','atlas-overlays','Interpreted geologic units','Configuration')
wire('source-gate','atlas-topography','Validated planetary raster inputs')
wire('source-gate','atlas-imagery','Validated mosaic inputs')
wire('region-registry','atlas-overlays','Region index and boundaries')
wire('footprint-index','atlas-overlays','Data-availability footprints')
for (const node of ['atlas-topography','atlas-imagery','atlas-overlays']) wire(node,'atlas-manifest','Atlas layer artifact and metadata','Derived product')
wire('atlas-manifest','g8-schema','Atlas schema checks','Validation')
wire('atlas-manifest','g9-package','Atlas artifact integrity','Validation')
wire('atlas-manifest','g10-runtime','Atlas runtime smoke check','Validation')
wire('atlas-manifest','atlas-offline','Staged atlas release','Derived product',{format:'Versioned layer manifest and tiled display assets',spatialReference:'Declared Mars atlas reference and tile matrix.',resolution:'Per-layer native sampling and display levels.',requiredMetadata:'Atlas version, region index, coverage, credits, checksums and offline subset.',failure:'Block corrupt layers or declare bounded unavailable detail.'})
for (const gate of ['g8-schema','g9-package','g10-runtime']) wire(gate,'atlas-offline','Required atlas release gate','Validation')
wire('atlas-offline','map','Local atlas and region discovery','Deployment',{protocol:'Same-origin local assets',description:'Planetary mapping consumes only installed assets. Detailed planning uses a separate validated site pack.'})
wire('footprint-index','availability','Catalog overlaps by region')
wire('region-registry','availability','AOI and required asset roles')
wire('region-registry','science-value','Objectives and region context')
wire('region-registry','region-job','Candidate region record','Data flow',{format:'Versioned region record',spatialReference:'Canonical Mars AOI with explicit frame and conventions.',requiredMetadata:'Stable region ID, geometry, objectives, candidate products, evaluation state and citation IDs.',failure:'Unknown bounds or missing required objective metadata blocks a detailed job.'})
wire('availability','regional-suitability','Data constraints and unknowns')
wire('science-value','regional-suitability','Research rationale and required evidence')
for (const node of ['availability','science-value','regional-suitability']) wire(node,'rank-regions','Independent assessment record')
wire('rank-regions','prioritize','Reviewed shortlist','Derived product')
wire('regional-suitability','prioritize','Qualitative fallback and blockers')
wire('prioritize','asset-select','Detailed acquisition scope','Configuration')
wire('prioritize','region-job','Selected regional investigation','Configuration')
wire('build-config','region-job','Pinned build config','Configuration',{format:'Versioned local manifest',requiredMetadata:'Region/config versions, required capabilities, source pins, tools, projection, methods and gate policy.',failure:'Unpinned inputs or unresolved required configuration prevent reproducible publication.'})
wire('asset-select','region-job','Selected product plan','Configuration')
wire('source-gate','region-job','Validated local inputs')
wire('region-job','aoi','Regional job and AOI')
wire('aoi','regional-dtm','Regional DTM requirements')
wire('source-gate','regional-dtm','Validated stereo candidates')
wire('asset-select','regional-dtm','Pinned terrain product roles','Configuration')
wire('regional-dtm','terrain-crop','Pinned DTM and native support')
wire('planetary-normalize','region-job','Canonical Mars AOI reference','Configuration')
wire('aoi','projection','Selected regional bounds and frame requirements','Configuration')
wire('projection','terrain-crop','Validated local metric transform','Configuration')
wire('terrain-crop','elevation','Local DTM and support mask','Derived product',{units:'Elevation metres; horizontal metres.',resolution:'Native spacing and requested analytical spacing recorded separately.'})
wire('terrain-crop','gradient','Native-support elevations')
wire('terrain-crop','g3-coverage','Actual usable footprint','Validation')
wire('terrain-crop','coverage','Native nodata and supported crop')
wire('elevation','routing-inputs','Analytical elevation and affine','Derived product')
wire('coverage','routing-inputs','Conservative validity mask','Derived product')
wire('screen','routing-inputs','Declared exclusion policy and mask','Derived product')
wire('routing-inputs','g4-terrain','Terrain/grid support evidence','Validation')
wire('routing-inputs','integrate','Regional terrain baseline','Derived product')
wire('routing-inputs','terrain-file','Staged baseline terrain contract','Derived product',{format:'NPZ: float32 elevation and Boolean validity/screen arrays',units:'Elevation and horizontal dimensions in metres.',spatialReference:'Site-pack metric Mars CRS with declared vertical reference and [row,col] affine.',resolution:'Native support and analytical grid spacing retained.',requiredMetadata:'Mask semantics, shape, affine, native sources, thresholds, processing version, integrity and routing eligibility.',failure:'Missing terrain support disables routing; it may leave a display-only pack.'})
for (const node of ['optical-prepare','geology-prepare','observation-discover']) wire('region-job',node,'Regional requirements and pinned assets','Configuration')
for (const node of ['optical-prepare','geology-prepare','register']) wire('projection',node,'Verified local spatial reference','Configuration')
for (const node of ['optical-prepare','geology-prepare']) {
  wire(node,'context','Aligned display artifact','Derived product')
  wire(node,'integrate','Layer, footprint and quality record')
}
wire('region-registry','science-objectives','Regional objectives and references')
wire('science-value','science-objectives','Research rationale')
wire('science-objectives','observation-discover','Evidence requirements')
wire('observation-discover','register','Pinned mission, orbital or published observations')
wire('register','evidence-quality','Registered historical observations','Derived product')
wire('register','evidence-files','Credited source media and observation records')
wire('evidence-quality','science-target','Reviewed evidence and uncertainty')
wire('science-objectives','science-target','Research objective and feature IDs')
wire('routing-inputs','science-target','Validated candidate approach support','Validation')
wire('science-target','science-task','Distinct targets and approach stations')
wire('science-target','g6-evidence','Science claims and approach checks','Validation')
wire('evidence-quality','g6-evidence','Evidence quality and source trace','Validation')
wire('science-task','integrate','Task records and supporting evidence')
wire('science-task','stations-file','Staged science task contract','Derived product',{format:'JSON station/task records',units:'Local positions in metres; declared dwell in minutes.',spatialReference:'Site local metre plane; preserve historical native positions and uncertainty.',requiredMetadata:'Region/objective/feature/target/approach IDs, citations, support, expected artifact, duration assumption and validation.',failure:'Omit unsupported tasks or invalid approaches with a reason.'})
wire('integrate','g5-alignment','Layer compatibility evidence','Validation')
wire('integrate','g7-readiness','Integrated candidate release','Validation')
for (const gate of ['g1-integrity','g2-coordinate','g3-coverage','g4-terrain','g5-alignment','g6-evidence']) wire(gate,'g7-readiness','Applicable gate outcome','Validation')
wire('g7-readiness','capability-report','Per-capability readiness','Validation')
wire('capability-report','manifest','Released capabilities and limitations','Validation')
for (const gate of ['g8-schema','g9-package','g10-runtime']) {
  wire('manifest',gate,'Staged regional pack release','Validation')
  wire(gate,'pack-check','Required release gate','Validation')
}
wire('pack-check','pack-registry','Immutable pack registration','Derived product',{format:'Versioned registry record and local artifact directory',requiredMetadata:'Region ID, pack ID/version, build date, validation, capability flags, source versions, artifact location and hash.',failure:'Withhold invalid staged outputs. Keep earlier immutable releases available.'})
wire('pack-registry','loader','Capability-aware local pack','Deployment',{protocol:'Local filesystem / same-origin asset delivery',requiredMetadata:'Compatible schema, pack identity, capabilities, hashes, coverage and available layers.',failure:'Refuse incompatible releases; withhold route support when not declared.'})
wire('registry','lineage','Original product IDs, hashes and attribution','Provenance')
wire('build-config','integrate','Versioned validation policy','Configuration')
wire('build-config','lineage','Versioned build policy and software','Configuration')
for (const node of ['terrain-crop','atlas-manifest','integrate','register','capability-report','g8-schema','g9-package','g10-runtime']) wire(node,'lineage','Operation, provenance or quality record','Provenance')
wire('lineage','manifest','Source-to-derivative provenance','Provenance',{format:'Versioned lineage records and stable artifact IDs',requiredMetadata:'Source and output IDs, transform and CRS versions, software, assumptions, hash, attribution, gate reports and evidence class.',failure:'Untraceable required artifacts cannot be published.'})

// The legacy seed remains the merge base for existing saves. Replace only shortcuts
// that bypass the new staged contracts. Runtime, deployment and walkthrough IDs stay stable.
const replacedEdges = new Set([
  'registry--retrieve','source-gate--aoi','aoi--projection','projection--elevation','projection--gradient',
  'projection--context','projection--register','elevation--terrain-file','coverage--terrain-file','screen--terrain-file',
  'projection--manifest','registry--manifest','register--stations-file','register--evidence-files','pack-check--loader',
  ...['hirise-dtm','hirise-ortho','ctx','perseverance','places','geology'].map(id=>id+'--registry'),
])
export function expandPipeline(base: Architecture): Architecture {
  const groups = [...pipelineGroups,...base.groups.filter(item=>!pipelineGroups.some(group=>group.id===item.id))]
  const merged = base.components.map(item=>({
    ...item,...patches[item.id],
    ...(item.dataset && legacySourceDetails[item.id] ? {dataset:{...item.dataset,...legacySourceDetails[item.id]}} : {}),
  }))
  const all = [...merged,...components]
  const byId = new Map(all.map(item=>[item.id,item]))
  const connections = [...base.connections.filter(edge=>!replacedEdges.has(edge.id)),...edges]
  // Give each new processing node structured contract entries even where only an
  // edge label is needed on the canvas. More specific authored variables win.
  const editable = new Set([...components.map(item=>item.id),...Object.keys(patches)])
  const byDirection = (direction: 'source' | 'target') => Map.groupBy(connections.filter(edge=>['Data flow','Derived product','Configuration'].includes(edge.kind)),edge=>edge[direction])
  const incoming = byDirection('target'), outgoing = byDirection('source')
  return {
    ...base,architectureVersion:'2.0.0',pipelineRevision:1,groups,connections,
    components:all.map(item=>{
      if (!editable.has(item.id)) return item
      const inputs = incoming.get(item.id) ?? [], outputs = outgoing.get(item.id) ?? []
      return {
        ...item,
        purpose:patches[item.id]?.description ? item.description.split('. ')[0].replace(/\.$/,'')+'.' : item.purpose,
        inputs:item.inputs.length ? item.inputs : inputs.map(edge=>v(edge.label,edge.format || 'Artifact reference',edge.units ?? '',edge.source,edge.payload,byId.get(edge.source)?.priority !== 'P2')),
        outputs:item.outputs.length ? item.outputs : outputs.map(edge=>v(edge.label,edge.format || 'Artifact reference',edge.units ?? '',edge.target,edge.payload)),
      }
    }),
  }
}
