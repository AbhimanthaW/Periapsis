import { z } from 'zod'

// The primary demo site is a qualified, less-documented area. Add its entry here only after
// it passes site qualification and is approved. Jezero is the engineering control only.
const siteSchema = z.object({
  id: z.string().regex(/^[a-z0-9-]+$/),
  label: z.string().min(1),
  role: z.enum(['primary', 'engineering_control']),
})
export type SiteDescriptor = z.infer<typeof siteSchema>

export const siteRegistry: readonly SiteDescriptor[] = z.array(siteSchema).parse([
  { id: 'jezero-control', label: 'Jezero Crater', role: 'engineering_control' },
])

export type SiteSelection =
  | { state: 'unset' }
  | { state: 'configured'; site: SiteDescriptor }
  | { state: 'invalid'; value: string }

export function resolveSite(raw: string | undefined): SiteSelection {
  const value = raw?.trim() ?? ''
  if (!value) return { state: 'unset' }
  const site = siteRegistry.find(entry => entry.id === value)
  return site ? { state: 'configured', site } : { state: 'invalid', value }
}

export const configuredSite: SiteSelection = resolveSite(import.meta.env.VITE_RW_SITE)
