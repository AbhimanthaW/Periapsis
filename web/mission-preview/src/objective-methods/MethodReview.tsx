import { useId, useState } from 'react'
import { Badge } from '../ui'
import { arcadiaScenario } from './arcadia'
import { goals } from './catalog'
import type { GoalId } from './catalog'
import type { AdvisoryProposal } from './recommend'

const statusLabels = { suggested: 'Suggested', pending: 'Pending', excluded: 'Excluded' }

export function MethodReview({ proposal, onConfirmGoals }: {
  proposal: AdvisoryProposal
  onConfirmGoals?: (goals: readonly GoalId[]) => void
}) {
  const id = useId()
  const { context, evidence, intent } = proposal
  const [draftGoals, setDraftGoals] = useState<readonly GoalId[]>(intent.goalIds)
  const canShowContext = proposal.methods.some(result =>
    result.method.id === 'review-mola-context' && result.status === 'suggested')
  return <div className="method-review">
    {onConfirmGoals ? <form onSubmit={event => { event.preventDefault(); onConfirmGoals(draftGoals) }}>
      <fieldset>
        <legend>Interpreted goals</legend>
        {goals.map(goal => <label key={goal.id}>
          <input type="checkbox" checked={draftGoals.includes(goal.id)} onChange={event => setDraftGoals(current =>
            event.target.checked ? [...current, goal.id] : current.filter(item => item !== goal.id))} />
          {goal.label}
        </label>)}
      </fieldset>
      <button type="submit" className="button compact">Confirm goals</button>
    </form> : <section aria-labelledby={id + '-goals'}>
      <h2 id={id + '-goals'}>Interpreted goals</h2>
      <ul>{goals.filter(goal => intent.goalIds.includes(goal.id)).map(goal => <li key={goal.id}>{goal.label}</li>)}</ul>
    </section>}
    {intent.modifierIds.length > 0 && <p className="muted">Modifiers {intent.modifierIds.join(', ')}</p>}
    {proposal.clarification.length > 0 && <div role="status" className="caution">
      {proposal.clarification.map((issue, index) => <p key={index}>{issue}</p>)}
    </div>}
    <section aria-labelledby={id + '-methods'}>
      <h2 id={id + '-methods'}>Methods</h2>
      {proposal.methods.length === 0 && <p className="muted">Methods are awaiting clarification.</p>}
      {proposal.methods.map(({ method, status, requested, reason, supportingProductIds }) =>
        <details key={method.id} data-method-id={method.id} className="method-result">
          <summary><strong>{method.label}</strong> <Badge>{statusLabels[status]}</Badge>{requested && <Badge>Requested</Badge>}</summary>
          <p>{reason}</p>
          <dl>
            <dt>Deliverable</dt><dd>{method.artifact}</dd>
            <dt>Scale</dt><dd>{method.scale}</dd>
            <dt>Acquisition</dt><dd>{method.acquisition}</dd>
            <dt>Prerequisite</dt><dd>{method.prerequisite}</dd>
            {supportingProductIds.length > 0 && <><dt>Product</dt><dd>{supportingProductIds.join(', ')} v1.1</dd></>}
          </dl>
          <a href={method.source.url} target="_blank" rel="noreferrer">{method.source.label}</a>
        </details>)}
    </section>
    {proposal.uncoveredObservations.length > 0 && <section aria-labelledby={id + '-gaps'}>
      <h2 id={id + '-gaps'}>Uncovered observations</h2>
      <ul>{proposal.uncoveredObservations.map(observation => <li key={observation.id} data-observation-id={observation.id}>
        <strong>{observation.label}</strong> · {observation.reasons.join(' ')}
      </li>)}</ul>
    </section>}
    {evidence && <section aria-labelledby={id + '-evidence'}>
      <h2 id={id + '-evidence'}>Evidence</h2>
      <p className="mono muted">{evidence.packageId} @ {evidence.packageVersion} · {evidence.classification}</p>
      <p className="muted">Arcadia handoff query polygon · approximately 4 × 4 km</p>
      {canShowContext && <figure>
        <img src={arcadiaScenario.contextImage} alt="Coarse MOLA elevation context around the Arcadia query area" />
        <figcaption>Regional context · 0.25° native spacing · NASA PDS / Mars Global Surveyor MOLA team</figcaption>
      </figure>}
    </section>}
    <p className="mono muted">{context.profile} · {proposal.catalogVersion} · {intent.source === 'lexicon' ? 'Lexicon' : 'Confirmed goals'}</p>
  </div>
}
