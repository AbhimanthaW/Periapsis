import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft } from 'lucide-react'
import { z } from 'zod'

const resultSchema = z.object({
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
type Area = z.infer<typeof resultSchema>['areas'][number]

export default function RankedAreas({ back }: { back: () => void }) {
  const [objective, setObjective] = useState('ancient lakes')
  const [areas, setAreas] = useState<Area[] | null>(null)
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
    setAreas(null)
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
      setAreas(result.data.areas)
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
    <p>The terrain screening score is the percentage of evaluated cells with mapped mass-wasting or polar dune units. Local slope, trafficability and mission safety are outside this assessment.</p>
    {busy && <p role="status">Ranking areas…</p>}
    {error && <p role="alert">{error}</p>}
    {areas && <p>Results for “{submittedObjective}”</p>}
    {areas?.length === 0 && <p role="status">No matching areas. Try an objective such as “shallow ice” or “ancient lakes”.</p>}
    {areas?.map(area => {
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
