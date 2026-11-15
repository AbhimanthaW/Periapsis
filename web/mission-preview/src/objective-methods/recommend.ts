import { arcadiaEvidence } from './arcadia.ts'
import type { AdvisoryContext } from './arcadia.ts'
import { catalogVersion, goals, methodCatalog } from './catalog.ts'
import type { Method } from './catalog.ts'
import type { Intent } from './interpret.ts'

export interface MethodResult {
  method: Method
  requested: boolean
  status: 'suggested' | 'pending' | 'excluded'
  reason: string
  supportingProductIds: readonly string[]
}

export function recommendMethods(intent: Intent, context: AdvisoryContext, catalog: readonly Method[] = methodCatalog) {
  const evidence = arcadiaEvidence(context)
  const observations = goals.filter(goal => intent.goalIds.includes(goal.id)).map(goal => goal.observation)
  const clarification = [...intent.constraintIssues, ...(intent.goalIssue ? [intent.goalIssue] : [])]
  const methods: MethodResult[] = []

  for (const method of catalog) {
    const requested = intent.requestedMethodIds.includes(method.id)
    const relevant = observations.some(observation => method.observations.includes(observation.id))
    if (!requested && (!relevant || clarification.length)) continue
    const conflictingOperation = method.operations.find(id => intent.excludedOperationIds.includes(id))
    if (intent.excludedMethodIds.includes(method.id) || conflictingOperation) {
      methods.push({ method, requested, status: 'excluded', supportingProductIds: [],
        reason: conflictingOperation ? 'Requires excluded operation: ' + conflictingOperation : 'Excluded in the objective.' })
    } else if (clarification.length) {
      methods.push({ method, requested, status: 'pending', supportingProductIds: [], reason: 'Awaiting clarification.' })
    } else {
      const support = method.id === 'review-mola-context' ? evidence?.regional
        : method.id === 'analyze-stereo-dtm' ? evidence?.local : undefined
      const reason = support?.eligible
        ? 'The pinned result supports this observation across the query area.'
        : evidence && method.id === 'analyze-stereo-dtm'
          ? 'The pinned evidence package supplies no qualifying stereo DTM for this polygon. Local elevation calculation is withheld.'
          : 'No reviewed evidence for this method at the selected region and footprint.'
      methods.push({ method, requested, status: support?.eligible ? 'suggested' : 'pending',
        supportingProductIds: support?.supporting_product_ids ?? [], reason })
    }
  }

  const uncoveredObservations = clarification.length ? [] : observations.flatMap(observation => {
    const options = methods.filter(result => result.method.observations.includes(observation.id))
    if (options.some(result => result.status === 'suggested')) return []
    return [{
      ...observation,
      reasons: options.length ? options.map(result => result.reason) : ['No catalog method delivers this observation.'],
    }]
  })
  return {
    catalogVersion, intent, context, methods, observations, uncoveredObservations, clarification,
    evidence: evidence ? {
      packageId: evidence.packageId,
      packageVersion: evidence.packageVersion,
      methodVersion: evidence.methodVersion,
      classification: evidence.classification,
      footprint: evidence.footprint,
    } : undefined,
  }
}

export type AdvisoryProposal = ReturnType<typeof recommendMethods>
