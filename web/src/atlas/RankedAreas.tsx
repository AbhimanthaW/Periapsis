import { useState } from 'react'
import type { FormEvent } from 'react'

type Claim = { label: string; cells: number; example_cell: string; source: string; source_url: string }
type Area = {
  rank: number
  label: string | null
  best_cell: string
  tier: string
  safety_risk?: {
    score: number | null
    evaluated_cells: number
    total_cells: number
    claims: Claim[]
  }
}

export default function RankedAreas() {
  const [objective, setObjective] = useState('ancient lakes')
  const [areas, setAreas] = useState<Area[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function rank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setAreas(null)
    try {
      const response = await fetch('/api/v1/rank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schema_version: 1, request_id: crypto.randomUUID(), objective: objective.trim(), limit: 20,
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.message || 'Ranking service unavailable.')
      }
      const result = await response.json()
      if (!Array.isArray(result.areas)) throw new Error('Ranking service returned an invalid response.')
      setAreas(result.areas)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ranking failed.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="atlas-compare-shell atlas-ranking">
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
    {areas?.length === 0 && <p role="status">No matching areas. Try an objective such as “shallow ice” or “ancient lakes”.</p>}
    {areas?.map(area => {
      const risk = area.safety_risk
      return <article key={area.best_cell}>
        <h3>{area.rank}. {area.label ?? area.best_cell}</h3>
        <p>{area.tier} match · {area.best_cell}</p>
        <p><strong>Terrain screening score</strong> {risk?.score == null ? 'Not evaluated' : risk.score + '/100'}</p>
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
