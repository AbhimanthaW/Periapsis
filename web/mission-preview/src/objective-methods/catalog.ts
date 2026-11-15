export const catalogVersion = 'arcadia-elevation-v1'

const molaArchive = 'https://pds-geosciences.wustl.edu/missions/mgs/megdr.html'
const stereoArchive = 'https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/'

export const goals = [
  {
    id: 'regional-elevation',
    label: 'Broad elevation context',
    aliases: ['broad elevation context', 'regional elevation', 'coarse elevation context', 'elevation overview'],
    observation: { id: 'regional-elevation-context', label: 'Regional elevation for orientation' },
  },
  {
    id: 'local-elevation',
    label: 'Local elevation at 20 m posting',
    aliases: ['local elevation at 20 m posting', 'local elevation at 20 m', '20 m posted elevation'],
    observation: { id: 'local-elevation-grid', label: 'Local elevation at 20 m posting' },
  },
] as const

export type GoalId = typeof goals[number]['id']
export type ObservationId = typeof goals[number]['observation']['id']

export interface Method {
  id: string
  label: string
  aliases: readonly string[]
  operations: readonly string[]
  observations: readonly ObservationId[]
  artifact: string
  scale: string
  acquisition: 'Existing orbital data'
  prerequisite: string
  source: { label: string; url: string }
}

export const methodCatalog = [
  {
    id: 'review-mola-context',
    label: 'Review MOLA elevation context',
    aliases: ['mola', 'mola context', 'mola elevation context', 'review mola elevation context'],
    operations: [],
    observations: ['regional-elevation-context'],
    artifact: 'Regional elevation context map and provenance',
    scale: '0.25° native spacing, about 14.8 km nominal at the equator',
    acquisition: 'Existing orbital data',
    prerequisite: 'A usable gridded altimetry product covering the entire area of interest',
    source: { label: 'NASA PDS MOLA archive', url: molaArchive },
  },
  {
    id: 'analyze-stereo-dtm',
    label: 'Analyze a local stereo terrain model',
    aliases: ['stereo dtm', 'stereo terrain model', 'local stereo terrain model', 'analyze a local stereo terrain model'],
    operations: [],
    observations: ['local-elevation-grid'],
    artifact: 'Local elevation grid and coverage note',
    scale: '20 m posting or finer across the query area',
    acquisition: 'Existing orbital data',
    prerequisite: 'A verified stereo DTM with usable coverage over the entire area of interest and posting of 20 m or finer',
    source: { label: 'USGS CTX DTM collection', url: stereoArchive },
  },
] as const satisfies readonly Method[]

export const operationAliases: Readonly<Record<string, readonly string[]>> = {
  drilling: ['drill', 'drilling'],
  sampling: ['sample', 'sampling', 'collect samples'],
}

// Age and setting terms from the Atlas lexicon are modifiers, not observations.
export const modifiers = [
  { id: 'age-ancient', aliases: ['ancient', 'noachian', 'early mars'] },
  { id: 'age-hesperian', aliases: ['hesperian'] },
  { id: 'age-young', aliases: ['young', 'recent', 'amazonian'] },
  { id: 'age-active', aliases: ['active today', 'present day'] },
  { id: 'polar', aliases: ['polar', 'high latitude'] },
] as const
