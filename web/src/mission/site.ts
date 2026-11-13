import { z } from 'zod'
import imagery from '../atlas/imagery.json'

// Local display assets that can provide map context for a site (from the Atlas manifest).
const contextAssetSchema = z.object({
  id: z.string(),
  title: z.string(),
  extent: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  width: z.number().positive(),
  height: z.number().positive(),
  nativeMeters: z.number(),
  credit: z.string(),
  limits: z.string(),
  source: z.url(),
})
export type ContextAsset = z.infer<typeof contextAssetSchema> & { url: string }
const contextAssets = new Map(z.array(contextAssetSchema).parse(imagery)
  .map(asset => [asset.id, { ...asset, url: `${import.meta.env.BASE_URL}atlas/${asset.id}.webp` } as ContextAsset]))

// The primary demo site is a qualified, less-documented area. Add its entry here only after
// it passes site qualification and is approved. Jezero is the engineering control only.
const siteSchema = z.object({
  id: z.string().regex(/^[a-z0-9-]+$/),
  label: z.string().min(1),
  role: z.enum(['primary', 'engineering_control']),
  // The evidence package the planning service must return for this site.
  evidence: z.object({ package_id: z.string().min(1), package_version: z.string().min(1) }),
  contextAssetId: z.string().optional(),
})
export type SiteDescriptor = z.infer<typeof siteSchema> & { context: ContextAsset | null }

export const siteRegistry: readonly SiteDescriptor[] = z.array(siteSchema).parse([
  {
    id: 'jezero-control',
    label: 'Jezero Crater',
    role: 'engineering_control',
    evidence: { package_id: 'jezero-ctx-usgs-archive-checked-window', package_version: 'window-v1' },
    contextAssetId: 'jezero',
  },
]).map(site => ({ ...site, context: site.contextAssetId ? contextAssets.get(site.contextAssetId) ?? null : null }))

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
