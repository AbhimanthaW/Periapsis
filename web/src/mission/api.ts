import { z } from 'zod'

// Same-origin paths. In development Vite proxies these to the loopback planning service.
export const endpoints = {
  health: '/healthz',
  site: '/api/v1/site',
  plan: '/api/v1/plan',
} as const

export const apiErrorSchema = z.object({
  schema_version: z.literal(1),
  request_id: z.string().nullable(),
  error: z.string(),
  message: z.string(),
})
export type ApiError = z.infer<typeof apiErrorSchema>

const healthSchema = z.object({ status: z.literal('ready') })
const healthTimeoutMs = 5_000

export type Health =
  | { state: 'ready' }
  | { state: 'unavailable'; reason: string }

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const timeout = AbortSignal.timeout(healthTimeoutMs)
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout
  try {
    const response = await fetch(endpoints.health, { signal: requestSignal, cache: 'no-store', headers: { Accept: 'application/json' } })
    const body: unknown = await response.json().catch(() => null)
    requestSignal.throwIfAborted()
    if (response.ok && healthSchema.safeParse(body).success) return { state: 'ready' }
    const error = apiErrorSchema.safeParse(body)
    return { state: 'unavailable', reason: error.success ? `${error.data.error}: ${error.data.message}` : `HTTP ${response.status}` }
  } catch (error) {
    if (signal?.aborted) throw error
    const reason = timeout.aborted ? 'Planning service health check timed out' : 'Planning service unreachable'
    return { state: 'unavailable', reason }
  }
}

// ---- Typed bindings for site, plan and evidence ----

const requestTimeoutMs = 8_000

export type ApiFailure =
  | { ok: false; kind: 'http'; status: number; error: ApiError | null }
  | { ok: false; kind: 'invalid_response'; status: number }
  | { ok: false; kind: 'unreachable' | 'timeout' }
export type ApiResult<T> = { ok: true; data: T } | ApiFailure

async function requestJson<S extends z.ZodType>(path: string, schema: S, init: { signal?: AbortSignal; body?: unknown } = {}): Promise<ApiResult<z.infer<S>>> {
  const timeout = AbortSignal.timeout(requestTimeoutMs)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  const post = init.body !== undefined
  try {
    const response = await fetch(path, {
      method: post ? 'POST' : 'GET',
      signal,
      cache: 'no-store',
      headers: post ? { Accept: 'application/json', 'Content-Type': 'application/json' } : { Accept: 'application/json' },
      body: post ? JSON.stringify(init.body) : undefined,
    })
    const body: unknown = await response.json().catch(() => undefined)
    signal.throwIfAborted()
    if (!response.ok) {
      const error = apiErrorSchema.safeParse(body)
      return { ok: false, kind: 'http', status: response.status, error: error.success ? error.data : null }
    }
    const parsed = schema.safeParse(body)
    return parsed.success ? { ok: true, data: parsed.data } : { ok: false, kind: 'invalid_response', status: response.status }
  } catch (error) {
    if (init.signal?.aborted) throw error
    return { ok: false, kind: timeout.aborted ? 'timeout' : 'unreachable' }
  }
}

export function describeFailure(failure: ApiFailure): string {
  switch (failure.kind) {
    case 'http':
      if (failure.error) return `${failure.error.error}: ${failure.error.message}`
      return failure.status >= 500 ? `Planning service unavailable (HTTP ${failure.status})` : `Planning service returned HTTP ${failure.status}`
    case 'invalid_response': return `Unexpected response shape (HTTP ${failure.status})`
    case 'timeout': return 'Planning service timed out'
    case 'unreachable': return 'Planning service unreachable'
  }
}

const id = z.string().min(1).max(128)
const cell = z.tuple([z.number().int().nonnegative(), z.number().int().nonnegative()])
export type Cell = z.infer<typeof cell>

export const fixtureSiteSchema = z.object({
  schema_version: z.literal(1),
  pack_id: id,
  pack_version: id,
  scenario_id: id,
  checkpoint_id: id,
  shelter_id: id,
  completed_task_ids: z.array(id),
  reserve_s: z.number().int().nonnegative(),
  classification: z.literal('synthetic'),
  capabilities: z.array(z.string()),
  remaining_s: z.number().int().nonnegative(),
  closures: z.array(z.object({ id, cells: z.array(cell) })),
  checkpoint_cell: cell,
  shelter_cell: cell,
  grid: z.object({
    shape: z.tuple([z.number().int().positive(), z.number().int().positive()]),
    affine: z.tuple([z.number(), z.number(), z.number(), z.number(), z.number(), z.number()]),
    index_order: z.literal('row_col'),
  }),
})
export type FixtureSite = z.infer<typeof fixtureSiteSchema>

const route = z.object({ seconds: z.number(), cells: z.array(cell) })
export const planStatuses = ['OK', 'RETURN_OVER_RESERVE', 'NO_RETURN_ROUTE'] as const
export const planResponseSchema = z.object({
  schema_version: z.literal(1),
  request_id: id,
  route_index_order: z.literal('row_col'),
  pack_id: id,
  pack_version: id,
  scenario_id: id,
  classification: z.literal('synthetic'),
  closure_ids: z.array(id),
  remaining_s: z.number().int(),
  reserve_s: z.number().int(),
  direct_return: route.nullable(),
  reverse_control: route.nullable(),
  return_margin_s: z.number().nullable(),
  completed_task_ids: z.array(id),
  science: z.array(z.object({ id, seconds: z.number().nullable(), margin_s: z.number().nullable(), feasible: z.boolean() })),
  recommendation: z.string().nullable(),
  status: z.enum(planStatuses),
})
export type PlanResponse = z.infer<typeof planResponseSchema>

export type PlanRequest = {
  schema_version: 1
  request_id: string
  pack_id: string
  pack_version: string
  scenario_id: string
  checkpoint_id: string
  shelter_id: string
  closure_ids: string[]
  completed_task_ids: string[]
  remaining_s: number
  reserve_s: number
}

const requirement = z.object({
  variable: z.string(),
  product_classes: z.array(z.string()).optional(),
  max_native_spacing_m: z.number().nullable().optional(),
  max_effective_scale_m: z.number().nullable().optional(),
})
const capabilitySpec = z.object({ id, requirements: z.array(requirement) })
const candidate = z.object({
  product_id: z.string(),
  observed_fraction: z.number(),
  support_fraction: z.number(),
  native_spacing_m: z.number().nullable(),
  effective_scale_m: z.number().nullable(),
  readiness: z.string(),
  reasons: z.array(z.string()),
})
const assessment = z.object({
  id,
  eligible: z.boolean(),
  variables: z.array(z.object({
    variable: z.string(),
    qualified_fraction: z.number(),
    covered_by_single_product: z.boolean(),
    candidates: z.array(candidate),
    reason: z.string().nullable(),
  })),
  supporting_product_ids: z.array(z.string()),
  reason: z.string().nullable(),
})
export type CapabilityAssessment = z.infer<typeof assessment>
const geometry = z.object({ type: z.string(), coordinates: z.unknown() })
export type Geometry = z.infer<typeof geometry>

export const evidenceResponseSchema = z.object({
  schema_version: z.literal(1),
  classification: z.literal('pinned_evidence'),
  context: z.literal('reviewed_local_query'),
  query_sha256: z.string(),
  package_sha256: z.string(),
  result: z.object({
    package_id: z.string(),
    package_version: z.string(),
    method_version: z.string(),
    limitations: z.array(z.string()),
    provenance: z.array(z.object({
      dataset: z.object({
        id: z.string(),
        mission: z.string().nullable().optional(),
        instrument: z.string().nullable().optional(),
        modality: z.string().nullable().optional(),
        product_class: z.string().nullable().optional(),
        archive_url: z.string().nullable().optional(),
        version: z.string().nullable().optional(),
        catalogue_status: z.string().nullable().optional(),
      }),
      product: z.object({
        id: z.string(),
        version: z.string().nullable().optional(),
        processing_level: z.string().nullable().optional(),
        readiness: z.string(),
        observation_extent_complete: z.boolean().nullable().optional(),
        support_extent_complete: z.boolean().nullable().optional(),
        variables: z.array(z.string()),
        native_spacing_m: z.number().nullable(),
        effective_scale_m: z.number().nullable(),
        limitations: z.array(z.string()).optional(),
      }),
      footprints: z.array(z.object({ id: z.string(), coverage_kind: z.string(), status: z.string(), geometry: geometry.optional() })),
    })),
    query: z.object({
      geometry,
      corridor_width_m: z.number().nullable().optional(),
      requested: capabilitySpec,
      fallbacks: z.array(capabilitySpec),
    }),
    requested: assessment,
    fallbacks: z.array(assessment),
    supported_fallback_ids: z.array(z.string()),
  }),
})
export type EvidenceResponse = z.infer<typeof evidenceResponseSchema>

export const getFixtureSite = (signal?: AbortSignal) => requestJson(endpoints.site, fixtureSiteSchema, { signal })
const evidenceBounds = z.object({ lower: z.number(), upper: z.number() })
const axis = z.object({
  classification_status: z.enum(['classified', 'unclassified']),
  tier: z.string(),
  bounds: evidenceBounds,
})

const regionEvidenceSchema = z.object({
  schema_version: z.literal(1),
  region_id: z.string(),
  anchor_cell_id: z.string().regex(/^HPX128:(0|[1-9]\d{0,5})$/),
  cell_context: z.object({
    pack: z.object({ version: z.string(), sha256: z.string() }),
    terrain: axis,
    science_environment: axis,
    mola_elevation_m: z.number().nullable(),
    mola_observation_count: z.number().int().nonnegative().nullable(),
    stereo_topography: z.object({
      status: z.string(),
      observed_fraction: z.number().min(0).max(1),
      usable_fraction: z.number().min(0).max(1),
    }),
  }).nullable(),
  local_evidence: evidenceResponseSchema.nullable(),
  tactical_routing: z.literal('withheld_no_qualified_pack'),
  live_hazards: z.literal('unavailable_no_qualified_feed'),
})
export type RegionEvidence = z.infer<typeof regionEvidenceSchema>
export const getRegionEvidence = (regionId: string, signal?: AbortSignal) =>
  requestJson('/api/v1/regions/' + encodeURIComponent(regionId), regionEvidenceSchema, { signal })
export const postPlan = (request: PlanRequest, signal?: AbortSignal) => requestJson(endpoints.plan, planResponseSchema, { signal, body: request })
