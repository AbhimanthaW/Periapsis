import { z } from 'zod'

// Same-origin paths. In development Vite proxies these to the loopback planning service.
export const endpoints = {
  health: '/healthz',
  site: '/api/v1/site',
  plan: '/api/v1/plan',
  evidence: '/api/v1/evidence',
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
