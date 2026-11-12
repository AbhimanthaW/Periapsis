import { z } from 'zod'
import registry from './regions.json'
import rasterManifest from './imagery.json'

export const modes = ['traversal','science'] as const
export const mapModes = [...modes,'feature'] as const
export const profiles = ['rover','human','terrain'] as const
export type Mode = typeof modes[number]
export type MapMode = typeof mapModes[number]
export type Profile = typeof profiles[number]
export type Rating = 1|2|3|4|5|null
export const labels: Record<Mode,string> = { traversal:'Traversal difficulty', science:'Scientific interest' }
export const profileLabels: Record<Profile,string> = { rover:'Rover · qualitative survey', human:'Human EVA', terrain:'Generic terrain context' }
export const levels = ['Very low','Low','Moderate','High','Very high']
const colors: Record<Mode,string[]> = {
  traversal:['#62bf96','#a1ca78','#e8cd6c','#f29860','#e9605d'],
  science:['#6997ec','#978aef','#bb82e2','#e581d7','#f878ab'],
}
export const modeDescriptions: Record<Mode,string> = {
  traversal:'Qualitative research on wheeled-rover difficulty, where the survey supplies a single level.',
  science:'General research significance in the survey, with objective qualifiers preserved.',
}
export const detailKeys = ['terrain','science','data','operations'] as const
const text = z.string()
const range = z.union([z.literal(1),z.literal(2),z.literal(3),z.literal(4),z.literal(5),z.null()])
const assessment = z.object({ rating:range, original:text, kind:text, note:text })
const summary = z.record(z.enum(detailKeys),z.array(text))
const table = z.object({ title:text, head:z.array(text), rows:z.array(z.array(text)) })
const coordinate = z.tuple([z.number().min(-180).max(180),z.number().min(-90).max(90)])
// Gazetteer seed uses centers. Validated lines/areas can be added independently.
const geographyShape = z.discriminatedUnion('type',[
  z.object({type:z.literal('Point'),coordinates:coordinate}),
  z.object({type:z.literal('LineString'),coordinates:z.array(coordinate)}),
  z.object({type:z.literal('MultiLineString'),coordinates:z.array(z.array(coordinate))}),
  z.object({type:z.literal('Polygon'),coordinates:z.array(z.array(coordinate))}),
  z.object({type:z.literal('MultiPolygon'),coordinates:z.array(z.array(z.array(coordinate)))}),
])
const regionSchema = z.object({
  id:text, name:text, sourceName:text, featureType:text, location:text, startLine:z.number(),endLine:z.number(),
  geography:z.object({ center:coordinate, status:z.enum(['Gazetteer center','Representative anchor','Verified geometry','Approximate geometry','Geometry unavailable','Geometry unverified']), gazetteerName:text,gazetteerUrl:z.url(),note:text,
    shape:geographyShape.optional(),shapeSource:z.url().optional() }),
  overview:z.array(text),assessments:z.record(z.enum(modes),assessment),
  sections:summary,tables:z.record(z.enum(detailKeys),z.array(table)),fields:z.record(text,text),
  sources:z.array(z.object({title:text,url:z.url(),kind:text})),
  concern:text,opportunity:text,documentationNote:text,uncertainty:text,related:z.array(z.object({id:text,relation:text})),
})
export type Region = z.infer<typeof regionSchema>
export type ResearchTable = z.infer<typeof table>
export const regions = z.array(regionSchema).parse(registry.regions)
export const byRegion = new Map(regions.map(region=>[region.id,region]))
export const featureTypes = [...new Set(regions.map(region=>region.featureType))].sort()
const featureColors = ['#eab969','#d283a8','#f48270','#7ac7c9','#9da4d8','#b8c876','#f9d6a2','#91bdec','#7fc5a0','#bb9ce0','#dfae93','#a2a6b2']
export const featureColor = (type:string) => featureColors[featureTypes.indexOf(type)] ?? '#abb1bc'
export const researchProvenance = {source:registry.gazetteerSource,date:registry.gazetteerDate,sha256:registry.researchSha256}

export const assetIds = ['viking','mola','jezero'] as const
const rasterSchema = z.object({ id:z.enum(assetIds), title:text,source:z.url(),service:z.url(),layer:text,matrix:text,level:z.number().int(),
  extent:z.tuple([z.number(),z.number(),z.number(),z.number()]),width:z.number(),height:z.number(),
  sampleDegrees:z.number(),nativeMeters:z.number(),credit:text,era:text,limits:text,crs:text,capabilitiesSha256:text,
})
export type RasterAsset = z.infer<typeof rasterSchema>
export const assets = Object.fromEntries(z.array(rasterSchema).parse(rasterManifest).map(asset=>[asset.id,asset])) as Record<typeof assetIds[number],RasterAsset>
export const globalExtent = assets.viking.extent
export const atlasAsset = (name: string) => import.meta.env.BASE_URL + 'atlas/' + name

export function assessmentFor(region:Region,mode:Mode,profile:Profile) {
  if (mode==='traversal' && profile!=='rover') return {
    rating:null,original:'',kind:'Not evaluated',note:profile==='human'?'The survey does not establish human EVA difficulty.':'Use the underlying terrain descriptions for context.',
  }
  return region.assessments[mode]
}
export const assessmentLabel = (value:Rating) => value ? levels[value-1] : 'Unclassified'
export const ratingColor = (mode:Mode,value:Rating) => value ? colors[mode][value-1] : '#abb1bc'
export function normalizeLongitude(value:number) { return ((value+180)%360+360)%360-180 }
export function coordinatesLabel([lon,lat]: number[],digits=2) {
  const normalized = normalizeLongitude(lon)
  return `${Math.abs(lat).toFixed(digits)}°${lat<0?'S':'N'}  ${Math.abs(normalized).toFixed(digits)}°${normalized<0?'W':'E'}`
}
export const searchText = (r:Region) => [r.id,r.name,r.featureType,r.location,r.concern,r.opportunity,r.uncertainty,
  ...r.overview,...Object.values(r.sections).flat(),...Object.values(r.fields),...r.sources.map(source=>source.title)].join(' ').toLowerCase()

export const atlasModelIds = {
  terrain:['elevation','gradient','roughness','barrier-mask','resolved-scale'],
  science:['rank-regions','science-relevance','task-eligibility'],
  readiness:['g7-readiness','pack-registry','hard-filter','evidence-limits'],
  pipeline:['atlas-manifest','region-registry','routing-inputs'],
} as const

/** Handoff contract for a future planner. Region center is not a starting waypoint. */
export interface MissionHandoff {
  regionId:string
  profile:'rover'|'human'
  sitePackId:string|null
  start:{ longitude:number; latitude:number; frame:'Mars planetocentric east' }|null
  objectiveIds:string[]
  targetIds:string[]
  constraintIds:string[]
}
export const readiness = 'Regional pack preparation pending'
export function planningContext(region:Region,profile:Profile):MissionHandoff|null {
  if (profile==='terrain') return null
  return {regionId:region.id,profile,sitePackId:null,start:null,objectiveIds:[],targetIds:[],constraintIds:[]}
}
