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

export type Health =
  | { state: 'ready' }
  | { state: 'unavailable'; reason: string }

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  try {
    const response = await fetch(endpoints.health, { signal, cache: 'no-store', headers: { Accept: 'application/json' } })
    const body: unknown = await response.json().catch(() => null)
    if (response.ok && healthSchema.safeParse(body).success) return { state: 'ready' }
    const error = apiErrorSchema.safeParse(body)
    return { state: 'unavailable', reason: error.success ? `${error.data.error}: ${error.data.message}` : `HTTP ${response.status}` }
  } catch (error) {
    if (signal?.aborted) throw error
    return { state: 'unavailable', reason: 'Planning service unreachable' }
  }
}
