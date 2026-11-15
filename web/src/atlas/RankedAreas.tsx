import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft } from 'lucide-react'
import { z } from 'zod'

const concept = z.object({ id: z.string() })
const resultSchema = z.object({
  schema_version: z.literal(1),
  abstain: z.boolean(),
  parse: z.object({
    concepts: z.array(concept),
    unsupported: z.array(concept),
    unknown: z.array(z.string()),
  }),
  request_id: z.string(),
  areas: z.array(z.object({
    rank: z.number().int().positive(),
    label: z.string().nullable(),
    best_cell: z.string(),
    tier: z.string(),
    terrain_screening: z.object({
      score: z.number().min(0).max(100).nullable(),
      flagged_cells: z.number().int().nonnegative(),
      evaluated_cells: z.number().int().nonnegative(),
      total_cells: z.number().int().positive(),
      claims: z.array(z.object({
        label: z.string(),
        cells: z.number().int().positive(),
        example_cell: z.string(),
        source: z.literal('USGS SIM 3292'),
        source_url: z.literal('https://pubs.usgs.gov/sim/3292/'),
      })),
    }).optional(),
  })),
})
type Result = z.infer<typeof resultSchema>

export default function RankedAreas({ back }: { back: () => void }) {
  const [objective, setObjective] = useState('ancient lakes')
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [submittedObjective, setSubmittedObjective] = useState('')
  const [busy, setBusy] = useState(false)

  async function rank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const submitted = objective.trim()
    if (!submitted || busy) return
    setBusy(true)
    setError('')
    setSubmittedObjective(submitted)
    setResult(null)
    try {
      const requestId = crypto.randomUUID()
      const response = await fetch('/api/v1/rank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schema_version: 1, request_id: requestId, objective: submitted, limit: 20,
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.message || 'Ranking service unavailable.')
      }
      const result = resultSchema.safeParse(await response.json())
      if (!result.success || result.data.request_id !== requestId)
        throw new Error('Ranking service returned an invalid response.')
      setResult(result.data)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ranking failed.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="atlas-compare-shell atlas-ranking">
    <button className="button" onClick={back}><ArrowLeft size={14}/> Back to map</button>
    <h2>Ranked areas</h2>
    <form onSubmit={rank}>
      <label htmlFor="rank-objective">Science objective</label>
      <input id="rank-objective" value={objective} maxLength={300} required
        onChange={event => setObjective(event.target.value)}/>
      <button className="button" disabled={busy || !objective.trim()}>Rank areas</button>
    </form>
    <p>Ranking thresholds are provisional. The terrain screening score is the percentage of evaluated cells with mapped mass-wasting or polar dune units. Local slope, trafficability and mission safety are outside this assessment.</p>
    {busy && <p role="status">Ranking areas…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <section aria-label="Objective interpretation">
      <p>Results for “{submittedObjective}”</p>
      {result.parse.concepts.length > 0 && <p>Evaluated concepts: {result.parse.concepts.map(item => item.id).join(', ')}.</p>}
      {result.parse.unsupported.length > 0 && <p>Unsupported concepts: {result.parse.unsupported.map(item => item.id).join(', ')}.</p>}
      {result.parse.unknown.length > 0 && <p>Unrecognized terms: {result.parse.unknown.join(', ')}.</p>}
      {(result.parse.unsupported.length > 0 || result.parse.unknown.length > 0) &&
        <p>Match tiers apply only to the evaluated concepts.</p>}
      {result.abstain ? <p role="status">Ranking withheld. No supported concepts were recognized.</p>
        : result.areas.length === 0 && <p role="status">No matching areas for the evaluated concepts.</p>}
    </section>}
    {result?.areas.map(area => {
      const risk = area.terrain_screening
      return <article key={area.best_cell}>
        <h3>{area.rank}. {area.label ?? area.best_cell}</h3>
        <p>{area.tier} match · {area.best_cell}</p>
        <p><strong>Terrain screening score</strong> {risk?.score == null ? 'Not evaluated' : risk.score + '% of evaluated cells'}</p>
        {risk && <p>{risk.evaluated_cells} of {risk.total_cells} cells evaluated</p>}
        <details>
          <summary>Evidence-backed claims</summary>
          {risk?.claims.length ? <ul>{risk.claims.map(claim => <li key={claim.label}>
            {claim.label} in {claim.cells} {claim.cells === 1 ? 'cell' : 'cells'}.
            Example {claim.example_cell}. <a href={claim.source_url}>{claim.source}</a>
          </li>)}</ul> : <p>{risk?.evaluated_cells
            ? 'No screened indicators were found in the evaluated cells.'
            : 'No evaluated terrain evidence available.'}</p>}
        </details>
      </article>
    })}
  </main>
}
