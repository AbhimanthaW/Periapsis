import type { Connection, LayoutKey, PipelineLens, ViewSettings } from './schema'

type Rows = (string | null)[][]
export type Lens = { label: string; description: string; rows: Rows; open: string[] }
export const lenses: Record<PipelineLens,Lens> = {
  complete:{
    label:'Complete pipeline',description:'Planetary atlas, regional science and independently validated routing inputs.',
    rows:[[null,'regions','prep','evidence',null],['sources','discovery','ingest','spatial','atlas'],[null,'provenance','terrain','quality','pack']],open:[],
  },
  global:{
    label:'Global Mars data',description:'Planetary elevation and optical display, coverage footprints and local atlas delivery.',
    rows:[['sources','discovery','spatial','atlas'],['regions','ingest','quality','pack'],[null,null,'ui']],open:['atlas'],
  },
  regions:{
    label:'Region evaluation',description:'An extensible registry, three independent assessments and a separate readiness gate.',
    rows:[['discovery','regions','prep','quality']],open:['regions'],
  },
  regional:{
    label:'Regional processing',description:'Follow a selected region through independent terrain, imagery, geology and evidence branches.',
    rows:[['regions','ingest','spatial','prep'],['terrain','evidence','quality','pack']],open:['prep'],
  },
  terrain:{
    label:'Terrain & routing',description:'Native DTM support, the regional metric grid, explicit masks and the baseline routing contract.',
    rows:[['sources','ingest','spatial','terrain'],['discovery','prep','quality'],[null,'api','pack']],open:['terrain'],
  },
  science:{
    label:'Science & evidence',description:'From archives and published interpretations to a cited target, separate approach and proposed task.',
    rows:[['sources','prep','spatial','evidence'],['discovery','ingest','quality'],['regions',null,'pack']],open:['evidence'],
  },
  publication:{
    label:'Validation & publication',description:'Quality gates, immutable atlas and site-pack releases, and evidence to reproduce a build.',
    rows:[['prep','quality','pack'],['atlas',null,'api'],['provenance']],open:['quality'],
  },
}
export const pipelineNumbers: Record<string,string> = Object.fromEntries(
  ['sources','discovery','ingest','spatial','atlas','regions','prep','terrain','evidence','quality','pack','provenance'].map((id,i)=>[id,String(i+1).padStart(2,'0')]),
)
export const systemRepresentatives: Record<string,string> = {
  discovery:'ingest',spatial:'prep',atlas:'prep',regions:'prep',terrain:'prep',evidence:'prep',quality:'pack',provenance:'pack',
}
export type PipelineRoute = 'left-gutter' | 'right-gutter' | 'above'
export type SummaryLink = { label: string; kind?: Connection['kind']; route?: PipelineRoute }
export const pipelineOverview: Record<string,SummaryLink> = {
  'sources>discovery':{label:'catalog records'},
  'discovery>ingest':{label:'asset plan',kind:'Configuration'},
  'ingest>spatial':{label:'native labels'},
  'spatial>atlas':{label:'Mars alignment',kind:'Derived product'},
  'discovery>regions':{label:'footprints'},
  'regions>prep':{label:'selected scope',kind:'Configuration'},
  'spatial>prep':{label:'local reference',kind:'Configuration'},
  'prep>evidence':{label:'objectives'},
  'prep>terrain':{label:'DTM brief',route:'left-gutter'},
  'evidence>quality':{label:'task evidence',route:'right-gutter'},
  'terrain>quality':{label:'grid + masks',kind:'Derived product'},
  'provenance>quality':{label:'gate policy',kind:'Configuration',route:'above'},
  'quality>pack':{label:'release gates',kind:'Validation'},
  'atlas>pack':{label:'atlas release',kind:'Derived product'},
}
export function layoutKey(settings: ViewSettings, revision: number | undefined, modelRevision?: number): LayoutKey {
  if (settings.view === 'models' && modelRevision) return `models-${settings.modelLens ?? 'complete'}`
  return settings.view === 'pipeline' && revision ? `pipeline-${settings.pipelineLens ?? 'complete'}` : settings.view
}

const links = (entries: [string,string,PipelineRoute?][]): Record<string,SummaryLink> =>
  Object.fromEntries(entries.map(([pair,label,route])=>[pair,{label,route}]))
export const lensSummaries: Record<PipelineLens,Record<string,SummaryLink>> = {
  complete:pipelineOverview,
  global:links([
    ['sources>discovery','catalog records'],['discovery>ingest','pinned assets'],
    ['discovery>regions','footprints'],['ingest>spatial','native labels'],['spatial>atlas','Mars reference'],
    ['atlas>quality','staged atlas'],['quality>pack','release checks'],['pack>ui','local atlas'],
  ]),
  regions:links([
    ['discovery>regions','availability evidence'],['regions>prep','selected scope'],['prep>quality','integration evidence'],
  ]),
  regional:links([
    ['regions>prep','selected scope'],['ingest>prep','local inputs'],['spatial>prep','Mars reference'],
    ['prep>terrain','terrain request'],['prep>evidence','science requirements'],['prep>quality','regional layers'],
    ['terrain>quality','grid + masks'],['evidence>quality','task evidence'],['quality>pack','release checks'],
  ]),
  terrain:links([
    ['sources>discovery','catalog records'],['discovery>ingest','pinned assets'],['ingest>spatial','native labels'],
    ['spatial>terrain','metric transform'],
    ['prep>terrain','regional grid plan'],['terrain>quality','support checks'],['quality>pack','routing capability'],['pack>api','local pack'],
  ]),
  science:links([
    ['sources>discovery','catalog records'],['discovery>ingest','asset plan'],['ingest>prep','validated inputs'],
    ['regions>evidence','objectives'],['prep>evidence','selected evidence'],['spatial>evidence','local reference'],
    ['evidence>quality','claims + approach checks'],['quality>pack','validated science capability'],
  ]),
  publication:links([
    ['prep>quality','aligned layers'],['atlas>quality','staged atlas'],['provenance>quality','versioned policy'],
    ['quality>pack','release checks'],['quality>provenance','gate reports'],['pack>api','local pack'],
  ]),
}

export const childOrder: Record<string,string[]> = {
  sources:['mola-megdr','ctx-mosaic','themis-ir','hirise-stereo','ctx-stereo','hrsc-stereo','hirise-dtm','ctx','regional-optical','hirise-ortho','mars-geology','geology','crism-archive','crism','perseverance','places','curiosity','meda','esa'],
  discovery:['discover','registry','footprint-index','asset-select'],
  ingest:['retrieve','raw-cache','readers','source-gate','quarantine'],
  spatial:['mars-reference','planetary-normalize','projection','verify-transform'],
  prep:['region-job','aoi','optical-prepare','geology-prepare','context'],
  terrain:['regional-dtm','terrain-crop','elevation','gradient','coverage','screen','routing-inputs'],
  evidence:['science-objectives','observation-discover','register','evidence-quality','science-target','science-task'],
  quality:['integrate','g1-integrity','g2-coordinate','g3-coverage','g4-terrain','g5-alignment','g6-evidence','g7-readiness','capability-report','g8-schema','g9-package','g10-runtime'],
  pack:['atlas-offline','manifest','terrain-file','stations-file','display-files','evidence-files','pack-check','pack-registry'],
  provenance:['build-config','lineage','pipeline-deferred'],
}
