// Dust outlook artifact produced by `python -m return_window_pipeline.dust train`.
// The JSON is a build-time import. When it has not been generated yet the panel says so and shows no numbers.

export type DustStatus = 'model_skilful' | 'climatology_only'

export interface DustRegion {
  climatology: (number | null)[]
  samples: number[]
  quiet?: (number | null)[] | null
  nearby?: (number | null)[] | null
}

export interface DustOutlook {
  artifactId: string
  status: DustStatus
  horizonSols: number
  definition: string
  marsYears: number[]
  lsBins: number[]
  pooledBss: number
  foldsPositive: number
  folds: number
  scenarios: { quiet: string; nearby: string }
  regions: Record<string, DustRegion>
}

export type DustLoad = { kind: 'missing' } | { kind: 'invalid'; reason: string } | { kind: 'ready'; outlook: DustOutlook }

const isProbability = (value: unknown) => value === null || (typeof value === 'number' && value >= 0 && value <= 1)
const probabilities = (value: unknown, length: number) =>
  Array.isArray(value) && value.length === length && value.every(isProbability)

export function parseDustOutlook(raw: unknown): DustLoad {
  const fail = (reason: string): DustLoad => ({ kind: 'invalid', reason })
  if (typeof raw !== 'object' || raw === null) return fail('not an object')
  const a = raw as Record<string, any>
  if (a.schema_version !== 1) return fail('unsupported schema version')
  if (a.status !== 'model_skilful' && a.status !== 'climatology_only') return fail('unknown status')
  if (a.validation?.status !== a.status) return fail('status disagrees with validation')
  const bins = a.ls_bins_deg
  if (!Array.isArray(bins) || bins.length !== 12 || !bins.every((v: unknown) => typeof v === 'number' && v >= 0 && v < 360))
    return fail('bad Ls bins')
  const pooled = a.validation?.pooled
  const folds = a.validation?.folds
  if (typeof pooled?.brier_skill_score !== 'number' || !Array.isArray(folds) || folds.length < 2) return fail('missing validation')
  const regions: Record<string, DustRegion> = {}
  for (const [id, entry] of Object.entries(a.regions ?? {})) {
    const e = entry as Record<string, unknown>
    if (!probabilities(e.climatology, 12) || !Array.isArray(e.samples) || e.samples.length !== 12) return fail('bad region ' + id)
    const region: DustRegion = { climatology: e.climatology as (number | null)[], samples: e.samples as number[] }
    if (a.status === 'model_skilful') {
      for (const key of ['quiet', 'nearby'] as const) {
        if (e[key] !== null && !probabilities(e[key], 12)) return fail(`bad ${key} for region ${id}`)
        region[key] = e[key] as (number | null)[] | null
      }
    } else if ('quiet' in e || 'nearby' in e) return fail('model values present without skill')
    regions[id] = region
  }
  if (Object.keys(regions).length === 0) return fail('no regions')
  return {
    kind: 'ready',
    outlook: {
      artifactId: String(a.artifact_id), status: a.status, horizonSols: Number(a.target?.horizon_sols),
      definition: String(a.target?.definition ?? ''), marsYears: (a.source?.mars_years ?? []).map(Number), lsBins: bins,
      pooledBss: pooled.brier_skill_score, foldsPositive: Number(pooled.folds_with_positive_skill), folds: folds.length,
      scenarios: { quiet: String(a.scenarios?.quiet ?? ''), nearby: String(a.scenarios?.nearby ?? '') }, regions,
    },
  }
}

const bundled = import.meta.glob<unknown>('./data/dust-outlook.json', { eager: true, import: 'default' })
const raw = bundled['./data/dust-outlook.json']
export const dustOutlook: DustLoad = raw === undefined ? { kind: 'missing' } : parseDustOutlook(raw)
