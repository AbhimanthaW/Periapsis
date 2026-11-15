import { useEffect, useRef, useState } from 'react'
import { describeFailure, getFixtureSite, postSortie } from '../mission/api'
import type { Cell, FixtureSite, SortiePlan, SortieRequest } from '../mission/api'
import { FixtureGrid } from '../mission/FixtureGrid'
import { signedSeconds, statusText } from '../mission/format'
import type { Point } from './Globe'

const tabs = ['Route', 'Analysis', 'Monitor'] as const
export type Stage = typeof tabs[number]
const key = (cell: Cell) => cell.join(',')
const same = (left: Cell, right: Cell) => key(left) === key(right)

export function Sortie({ cellId, marsPoint, demo, initialStage = 'Route' }: { cellId: string; marsPoint: Point; demo: boolean; initialStage?: Stage }) {
  const [site, setSite] = useState<FixtureSite | null>(null)
  const [fault, setFault] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setFault('')
    getFixtureSite(controller.signal).then(response => {
      if (response.ok) setSite(response.data)
      else setFault(describeFailure(response))
    }, () => {})
    return () => controller.abort()
  }, [attempt])
  if (!site) return <section className="mission-card">
    {fault ? <><p role="alert">{fault}</p><button onClick={() => setAttempt(n => n + 1)}>Retry loading grid</button></>
      : <p role="status">Loading simulation grid…</p>}
  </section>
  return <Planner site={site} cellId={cellId} marsPoint={marsPoint} demo={demo} initialStage={initialStage}/>
}

function GridPicker({ label, site, value, choose, disabled = false }: {
  label: string; site: FixtureSite; value: Cell; choose: (point: Cell) => void; disabled?: boolean
}) {
  const [rows, cols] = site.grid.shape
  return <label>{label} <select value={key(value)} disabled={disabled} onChange={event => {
    const [row, col] = event.target.value.split(',').map(Number)
    choose([row, col])
  }}>
    {Array.from({ length: rows }, (_, row) => Array.from({ length: cols }, (_, col) =>
      <option key={row + ',' + col} value={row + ',' + col}>Row {row}, column {col}</option>))}
  </select></label>
}

function Planner({ site, cellId, marsPoint, demo, initialStage }: { site: FixtureSite; cellId: string; marsPoint: Point; demo: boolean; initialStage: Stage }) {
  const [stage, setStage] = useState<Stage>(initialStage)
  const [sortie, setSortie] = useState(() => crypto.randomUUID())
  const start: Cell = demo ? [1, 1] : site.shelter_cell
  const [base, setBase] = useState(start)
  const [current, setCurrent] = useState(start)
  const [departed, setDeparted] = useState(false)
  const [closures, setClosures] = useState<string[]>([])
  const [remaining, setRemaining] = useState(demo ? 130 : site.remaining_s)
  const [result, setResult] = useState<SortiePlan | null>(null)
  const [approved, setApproved] = useState(false)
  const [fault, setFault] = useState('')
  const [pending, setPending] = useState(true)
  const revision = useRef(0)
  const active = useRef<AbortController | null>(null)
  const previousRequest = useRef<SortieRequest | null>(null)

  function invalidate() {
    active.current?.abort()
    previousRequest.current = null
    setApproved(false)
    setPending(false)
    setFault('')
    setResult(null)
  }

  function selectBase(point: Cell) {
    invalidate()
    setBase(point)
    setCurrent(point)
    setSortie(crypto.randomUUID())
    revision.current = 0
  }

  async function calculate(retry = false) {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setApproved(false)
    setFault('')
    setResult(null)
    setPending(true)
    const request: SortieRequest = retry && previousRequest.current ? previousRequest.current : {
      schema_version: 2, request_id: crypto.randomUUID(), sortie_id: sortie, revision: ++revision.current,
      context_cell_id: cellId, mars_base_point: marsPoint, pack_id: site.pack_id, pack_version: site.pack_version,
      scenario_id: site.scenario_id, mode: 'simulation', base_cell: base, current_cell: current,
      completed_task_ids: site.completed_task_ids, closure_ids: closures, remaining_s: remaining,
    }
    previousRequest.current = request
    try {
      const response = await postSortie(request, controller.signal)
      if (controller.signal.aborted || active.current !== controller) return
      if (!response.ok) { setFault(describeFailure(response)); return }
      const plan = response.data
      if (plan.request_id !== request.request_id || plan.revision !== request.revision || plan.sortie_id !== request.sortie_id ||
          plan.context_cell_id !== cellId || plan.pack_id !== site.pack_id || plan.pack_version !== site.pack_version ||
          plan.scenario_id !== site.scenario_id || plan.remaining_s !== request.remaining_s ||
          !same(plan.base_cell, base) || !same(plan.current_cell, current) || !same(plan.mars_base_point, marsPoint) ||
          plan.closure_ids.join() !== request.closure_ids.join() || plan.completed_task_ids.join() !== request.completed_task_ids.join()) {
        setFault('The service returned a different scenario or position. Calculate again.')
        return
      }
      setResult(plan)
    } catch (error) {
      if (!controller.signal.aborted) setFault(String(error))
    } finally {
      if (active.current === controller && !controller.signal.aborted) setPending(false)
    }
  }

  useEffect(() => {
    void calculate()
    return () => active.current?.abort()
    // Submit the initial rehearsal once, with the current inputs.
  }, [])

  const route = result?.marswalk.candidates.find(candidate => candidate.passed &&
    (candidate.id === result.recommendation || candidate.id === 'science:' + result.recommendation))
  const routeCells = route?.legs.flatMap(leg => leg.cells) ?? result?.direct_return?.cells ?? null
  return <div className="mission-site sortie-shell" data-stage={stage.toLowerCase()} aria-label="Simulated Marswalk workspace">
    <div className="mission-site-main">
      <nav className="cell-toolbar sortie-tabs" aria-label="Marswalk stages">
        {tabs.map(tab => <button className="mission-button" key={tab} aria-pressed={stage === tab} onClick={() => setStage(tab)}>{tab}</button>)}
      </nav>
      <section className="sortie-content">
        <header className="sortie-title">
          <span className="mission-badge">SIMULATION</span>
          <h1>{stage} · Synthetic Marswalk</h1>
          <p>Mars context <code>{cellId}</code> · Saved Mars base {Math.abs(marsPoint[1]).toFixed(4)}°{marsPoint[1] < 0 ? 'S' : 'N'}, {Math.abs(marsPoint[0]).toFixed(4)}°{marsPoint[0] < 0 ? 'W' : 'E'}</p>
          <p>The map below simulates crew movement on a local grid. It does not show a traversable route on Mars.</p>
        </header>
        {pending && <p className="sortie-result" aria-live="polite">Calculating a proposal…</p>}
        {!pending && !fault && !result && <p className="sortie-result">Settings changed. Calculate again to review a new route.</p>}
        {result && <section aria-label="Planning result" className="sortie-result">
          <div><h2>{statusText[result.status]}</h2>
            <p>Recommendation: {result.recommendation ?? 'None'}</p>
            <p>Return margin {signedSeconds(result.return_margin_s)} · {approved ? 'Operator approved' : 'Not approved'}</p>
          </div>
          {stage === 'Route' && result.status === 'OK' && route &&
            <button className="mission-button mission-button-primary" onClick={() => setStage('Monitor')}>Review route in Monitor</button>}
        </section>}
        <div className="sortie-map">
          <FixtureGrid site={{ ...site, checkpoint_cell: current, shelter_cell: base }} activeClosures={closures}
            route={routeCells} inspectOnly={!approved}/>
        </div>
        {stage === 'Analysis' && result && <section aria-labelledby="route-comparison">
          <h2 id="route-comparison">Route comparison</h2>
          <p>Feasibility checks use the synthetic grid and the current time budget.</p>
          <div className="sortie-table"><table>
            <thead><tr><th scope="col">Candidate</th><th scope="col">Decision</th><th scope="col">Legs</th><th scope="col">Reason</th></tr></thead>
            <tbody>{result.marswalk.candidates.map(candidate => <tr key={candidate.id}>
              <th scope="row">{candidate.id}</th>
              <td>{candidate === route ? 'Recommended' : candidate.passed ? 'Feasible' : 'Withheld'}</td>
              <td>{candidate.legs.length}</td>
              <td>{candidate.failure_reasons.join(', ') || '—'}</td>
            </tr>)}</tbody>
          </table></div>
        </section>}
        {stage === 'Monitor' && <>
          <p role="status">{pending ? 'Computing on the local API' : approved ? 'Operator approved · local API' : 'Awaiting a current operator-approved route'}</p>
          {result?.status === 'OK' && route && <button className="mission-button mission-button-primary" onClick={() => setApproved(true)} disabled={approved}>Approve route</button>}
          {approved && !departed && routeCells?.some(cell => !same(cell, current)) && <button className="mission-button mission-button-primary" onClick={() => setDeparted(true)}>Record departure</button>}
          <a href={'/demo/?' + new URLSearchParams({ cell: cellId, base: marsPoint.join(',') }) + '#monitor/rover/43/hazards'}>
            Open the separate hazard replay
          </a>
        </>}
      </section>
    </div>
    <aside className="sortie-controls">
      <h2>Simulation controls</h2>
      <GridPicker label="Synthetic base" site={site} value={base} disabled={departed} choose={selectBase}/>
      {departed && <GridPicker label="Report simulated crew position" site={site} value={current}
        choose={point => { invalidate(); setCurrent(point) }}/>}
      <label>Remaining time (s) <input type="number" min={0} max={86400} value={remaining}
        onChange={event => { invalidate(); setRemaining(Math.max(0, Math.min(86400, Math.trunc(Number(event.target.value))))) }}/></label>
      {site.closures.map(closure => <label key={closure.id}><input type="checkbox" checked={closures.includes(closure.id)}
        onChange={event => {
          invalidate()
          setClosures(checked => event.target.checked ? [...checked, closure.id] : checked.filter(item => item !== closure.id))
        }}/> Close {closure.id} corridor</label>)}
      <button className="mission-button mission-button-primary" onClick={() => void calculate()} disabled={pending}>{departed ? 'Recalculate return' : 'Calculate sortie'}</button>
      {departed && <button onClick={() => { setDeparted(false); selectBase(base); setClosures([]); setRemaining(site.remaining_s) }}>Start new sortie</button>}
      {fault && <><p role="alert">{fault}</p><button onClick={() => void calculate(true)}>Retry calculation</button></>}
      {result && <div className="sortie-details">
        <p>Completed work: {result.completed_task_ids.join(', ') || 'None'}</p>
      </div>}
    </aside>
  </div>
}
