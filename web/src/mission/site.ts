import imagery from '../atlas/imagery.json'
import sites from '../../../evidence/sites.v1.json'
import arcadia from '../../../pipeline/evidence/arcadia-planitia/display-metadata.json'
import arcadiaImage from '../../../pipeline/evidence/arcadia-planitia/arcadia-mola-context.png?url'

export type ContextAsset = {
  title: string
  extent: number[]
  width: number
  height: number
  nativeMeters: number
  credit: string
  url: string
}

type SiteDescriptor = typeof sites.sites[keyof typeof sites.sites]
const evidenceSites: Readonly<Partial<Record<string, SiteDescriptor>>> = sites.sites

const contextAssets: Record<string, ContextAsset> = {
  ...Object.fromEntries(imagery.map(asset => [asset.id, {
    ...asset, url: `${import.meta.env.BASE_URL}atlas/${asset.id}.webp`,
  }])),
  'arcadia-mola': {
    title: 'Arcadia MOLA regional context',
    extent: arcadia.display_bounds_wsen_deg,
    width: 528,
    height: 528,
    nativeMeters: 14_818,
    credit: arcadia.attribution,
    url: arcadiaImage,
  },
}

export const primaryRegion = sites.primary_region
export const pinnedSite = (regionId: string) => evidenceSites[regionId]
export const contextFor = (site: SiteDescriptor | undefined) => site && contextAssets[site.display]
