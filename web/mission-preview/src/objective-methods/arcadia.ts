import query from '../../../../pipeline/evidence/arcadia-planitia/evidence-query.json' with { type: 'json' }
import evidencePackage from '../../../../pipeline/evidence/arcadia-planitia/evidence.json' with { type: 'json' }
import verification from '../../../../pipeline/evidence/arcadia-planitia/verification.json' with { type: 'json' }
import apiVerification from '../../../../pipeline/evidence/arcadia-planitia/api-verification.json' with { type: 'json' }
import display from '../../../../pipeline/evidence/arcadia-planitia/display-metadata.json' with { type: 'json' }
import type { Profile } from '../regions'

const receipt = verification.arcadia
const apiReceipt = apiVerification.evidence
const fallbackQuery = query.fallbacks.find(item => item.id === 'coarse_elevation_context')
const regionalReceipt = receipt.fallbacks.find(item => item.id === fallbackQuery?.id)
const localReceipt = receipt.requested
const molaProduct = evidencePackage.products.find(item => item.id === 'mola-meg004-topography')
const molaFootprint = evidencePackage.footprints.find(item => item.id === 'arcadia-mola-local-elevation-support')
const sameGeometry = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right)
const sameRequirements = (evaluated: typeof receipt.query.requested, expected: typeof query.requested) =>
  evaluated.id === expected.id && JSON.stringify(evaluated.requirements.map(item => ({
    variable: item.variable, product_classes: item.product_classes, max_native_spacing_m: item.max_native_spacing_m,
  }))) === JSON.stringify(expected.requirements)
const evidenceMatchesQuery = verification.schemas_validated
  && sameGeometry(receipt.query.geometry, query.geometry)
  && sameGeometry(molaFootprint?.geometry, query.geometry)
  && sameRequirements(receipt.query.requested, query.requested)
  && fallbackQuery !== undefined
  && receipt.query.fallbacks.some(item => sameRequirements(item, fallbackQuery))
  && receipt.package_id === evidencePackage.package_id && receipt.package_version === evidencePackage.version
  && receipt.package_id === apiReceipt.package_id
  && receipt.package_version === apiReceipt.package_version
  && localReceipt.id === query.requested.id && localReceipt.eligible === apiReceipt.requested_eligible
  && regionalReceipt?.eligible && apiReceipt.supported_fallback_ids.includes(regionalReceipt.id)
  && molaProduct?.version === '1.1' && regionalReceipt.supporting_product_ids.includes(molaProduct.id)

export const arcadiaScenario = {
  regionId: display.region_id,
  regionName: display.name,
  profile: 'Astronaut' satisfies Profile,
  objective: 'Map broad elevation context and assess local elevation at 20 m posting.',
  footprint: { id: 'arcadia-handoff-polygon-v1', geometry: query.geometry },
  contextImage: new URL('../../../../pipeline/evidence/arcadia-planitia/arcadia-mola-context.png', import.meta.url).href,
  evidence: {
    packageId: receipt.package_id,
    packageVersion: receipt.package_version,
    methodVersion: receipt.method_version,
    classification: apiReceipt.classification,
  },
} as const

export interface AdvisoryContext {
  regionId: string
  profile: Profile
  footprint?: { id: string; geometry: { type: string; coordinates: readonly (readonly (readonly number[])[])[] } }
}

export function arcadiaEvidence(context: AdvisoryContext) {
  const footprint = context.footprint
  if (!evidenceMatchesQuery || context.regionId !== arcadiaScenario.regionId
    || footprint?.id !== arcadiaScenario.footprint.id
    || !sameGeometry(footprint.geometry, query.geometry)) return undefined
  return {
    ...arcadiaScenario.evidence,
    footprint: arcadiaScenario.footprint,
    regional: regionalReceipt,
    local: localReceipt,
  }
}
