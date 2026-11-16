import { useEffect, useRef, useState } from 'react'
import { describeFailure, getFixtureSite, postSortie } from '../mission/api'
import type { Cell, FixtureSite, SortiePlan, SortieRequest } from '../mission/api'
import { FixtureGrid } from '../mission/FixtureGrid'
import { signedSeconds, statusText } from '../mission/format'
import type { Layer, Point } from './Globe'
import { RouteMap } from './RouteMap'
import { distanceFromBase, formatPoint, getCell, rankCells } from '../../mission-preview/src/cells'
import { defaultObjective, methods, exclusions } from '../../mission-preview/src/regions'
import type { Method } from '../../mission-preview/src/regions'

const tabs = ['Route', 'Analysis', 'Monitor'] as const
export type Stage = typeof tabs[number]
const key = (cell: Cell) => cell.join(',')
const same = (left: Cell, right: Cell) => key(left) === key(right)

type ScienceInputs = {
  scienceObjective?: string; methodInput?: string | null; exclusionsInput?: string[]; initialLayer?: Layer
}
type SortieProps = ScienceInputs & {
  cellId: string; marsPoint: Point; demo: boolean; initialStage?: Stage; tileBase?: string
  onStageChange?: (stage: Stage) => void
}

export function Sortie({ cellId, marsPoint, demo, initialStage = 'Route', ...science }: SortieProps) {
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
  return <Planner site={site} cellId={cellId} marsPoint={marsPoint} demo={demo} initialStage={initialStage} {...science}/>
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

function useScienceDestination({ scienceObjective, methodInput, exclusionsInput }: ScienceInputs) {
  const objective = scienceObjective || defaultObjective
  const method = methods.find(choice => choice === methodInput) ?? (objective === 'shallow subsurface ice' ? 'Investigate ice' : 'Remote survey') satisfies Method
  const exclusionKey = exclusionsInput?.join(',') ?? ''
  const [attempt, setAttempt] = useState(0)
  const [destination, setDestination] = useState<{ id: string; point: Point; label: string | null; pack: string; rank: number; tier: string; sparse: boolean }>()
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')
  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    setDestination(undefined)
    setStatus('loading')
    async function load() {
      try {
        const result = await rankCells(objective, method, exclusions.filter(item => exclusionKey.split(',').includes(item)), signal)
        const best = result.abstain ? undefined : result.areas.reduce<(typeof result.areas)[number] | undefined>(
          (first, area) => !first || area.rank < first.rank ? area : first, undefined)
        if (!best) { if (!signal.aborted) setStatus('empty'); return }
        const { cell } = await getCell(best.best_cell, signal)
        if (signal.aborted) return
        setDestination({ id: cell.id, point: cell.centroid, label: best.label, pack: result.pack.version, rank: best.rank, tier: best.tier, sparse: best.sparse })
        setStatus('ready')
      } catch {
        if (!signal.aborted) setStatus('error')
      }
    }
    void load()
    return () => controller.abort()
  }, [attempt, objective, method, exclusionKey])

  return { objective, destination, status, retry: () => setAttempt(n => n + 1) }
}

function ScienceCorridor({ marsPoint, target, initialLayer = 'viking', tileBase }: {
  marsPoint: Point; target?: Point; initialLayer?: Layer; tileBase?: string
}) {
  const [layer, setLayer] = useState(initialLayer)
  return <section className="science-corridor" aria-label="Mars surface context">
    <RouteMap base={marsPoint} target={target} layer={layer} tileBase={tileBase}/>
    <div className="corridor-tools">
      <label>Basemap <select value={layer} onChange={event => setLayer(event.target.value as Layer)}>
        <option value="viking">Viking colour</option>
        <option value="mola">MOLA relief</option>
      </select></label>
    </div>
    <div className="corridor-caption">
      <span>{layer === 'viking' ? 'Viking colour mosaic' : 'MOLA shaded relief'} · Mars context</span>
      <strong>{target ? 'Base and science destination only' : 'Map centered on saved base'} · Tactical routing withheld</strong>
    </div>
  </section>
}

function ScienceDestination({ objective, destination, status, retry, marsPoint }: ReturnType<typeof useScienceDestination> & { marsPoint: Point }) {
      return <section className="corridor-target" aria-live="polite" aria-labelledby="science-destination">
      <span className="mission-badge">Exploratory ranking</span>
      <h2 id="science-destination">Science destination</h2>
      <p>{objective}</p>
      {status === 'loading' && <p>Ranking Mars cells…</p>}
      {status === 'empty' && <p>The ranking model found no supported destination for this objective.</p>}
      {status === 'error' && <><p>Science destination unavailable.</p><button className="mission-button" onClick={retry}>Retry ranking</button></>}
      {destination && <>
        <p><strong>{destination.label ? 'Near ' + destination.label : destination.id}</strong>
          {destination.label && <> · <code>{destination.id}</code></>}</p>
        <p>{formatPoint(destination.point, 4)} · Rank {destination.rank} · {destination.tier} match</p>
        <p>{distanceFromBase(marsPoint, destination.point).toLocaleString(undefined, { maximumFractionDigits: 1 })} km surface separation</p>
        {destination.sparse && <p>Sparse evidence. Local conditions are unverified.</p>}
        <p className="mission-muted">Data pack {destination.pack}</p>
      </>}
  </section>
}

function Planner({ site, cellId, marsPoint, demo, initialStage = 'Route', tileBase, onStageChange, ...science }: SortieProps & { site: FixtureSite }) {
  const scienceResult = useScienceDestination(science)
  const [stage, setStage] = useState<Stage>(initialStage)
  const [sortie, setSortie] = useState(() => crypto.randomUUID())
  const start: Cell = demo ? [1, 1] : site.shelter_cell
  const [base, setBase] = useState(start)
  const [current, setCurrent] = useState(start)
  const [departed, setDeparted] = useState(false)
  const [closures, setClosures] = useState<string[]>([])
  const initialBudget = demo ? 130 : Math.max(160, site.remaining_s)
  const [remaining, setRemaining] = useState(initialBudget)
  const [result, setResult] = useState<SortiePlan | null>(null)
  const [approvedId, setApproved] = useState<string>()
  const [selectedId, setSelectedId] = useState<string>()
  const [playing, setPlaying] = useState(false)
  const [step, setStep] = useState(0)
  const [view, setView] = useState<'terrain' | 'mars'>(initialStage === 'Monitor' ? 'terrain' : 'mars')
  const [fault, setFault] = useState('')
  const [pending, setPending] = useState(true)
  const revision = useRef(0)
  const active = useRef<AbortController | null>(null)
  const previousRequest = useRef<SortieRequest | null>(null)

  function invalidate() {
    active.current?.abort()
    previousRequest.current = null
    setApproved(undefined)
    setSelectedId(undefined)
    setPlaying(false)
    setStep(0)
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
    setApproved(undefined)
    setSelectedId(undefined)
    setPlaying(false)
    setStep(0)
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
      if (departed) setSelectedId(plan.marswalk.candidates.find(candidate => candidate.id === 'direct_return')?.id)
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

  const candidates = result?.marswalk.candidates ?? []
  const recommended = candidates.find(candidate => candidate.passed &&
    (candidate.id === result?.recommendation || candidate.id === 'science:' + result?.recommendation))
  const route = candidates.find(candidate => candidate.id === selectedId) ?? recommended
  const cells = (candidate: (typeof candidates)[number]) => candidate.legs.flatMap(leg => leg.cells)
    .filter((cell, index, path) => index === 0 || !same(cell, path[index - 1]))
  const routeCells = route ? (route.legs.every(leg => leg.cells.length) ? cells(route) : null) : result?.direct_return?.cells ?? null
  const alternatives = candidates.filter(candidate => candidate !== route && candidate.passed && candidate.legs.every(leg => leg.cells.length)).map(cells)
  const approved = Boolean(route && approvedId === route.id)
  const distance = route?.legs.length && route.legs.every(leg => leg.length_m !== null)
    ? route.legs.reduce((sum, leg) => sum + leg.length_m!, 0) : null
  const slope = route?.legs.length && route.legs.every(leg => leg.max_slope_deg !== null)
    ? Math.max(...route.legs.map(leg => leg.max_slope_deg!)) : null
  const lastStep = (routeCells?.length ?? 1) - 1
  useEffect(() => {
    if (!playing || stage !== 'Monitor') return
    if (step >= lastStep) { setPlaying(false); return }
    const timer = window.setTimeout(() => setStep(currentStep => currentStep + 1), 450)
    return () => window.clearTimeout(timer)
  }, [playing, stage, step, lastStep])

  function selectCandidate(id: string) {
    if (stage === 'Analysis') setView('terrain')
    setSelectedId(id)
    setPlaying(false)
    setStep(0)
  }

  function switchStage(next: Stage) {
    if (next === stage) return
    setPlaying(false)
    setView(next === 'Monitor' ? 'terrain' : 'mars')
    setStage(next)
    onStageChange?.(next)
  }

  const marsMap = <ScienceCorridor marsPoint={marsPoint} target={scienceResult.destination?.point} initialLayer={science.initialLayer} tileBase={tileBase}/>
  const destination = <ScienceDestination {...scienceResult} marsPoint={marsPoint}/>
  const context = <>Mars context <code>{cellId}</code> · Saved Mars base {formatPoint(marsPoint, 4).replace(' ', ', ')}</>
  const map = <section className="sortie-map" aria-label="Computed route map">
    <div className="sortie-map-tools">
      <span className="mission-badge">Synthetic terrain</span>
      <strong>{route?.id ?? 'Rehearsal grid'}</strong>
      <span>{closures.length ? closures.length + ' corridor(s) closed' : 'Corridors open'}</span>
    </div>
    <FixtureGrid site={{ ...site, checkpoint_cell: current, shelter_cell: base }} activeClosures={closures}
      route={routeCells} alternatives={alternatives} inspectOnly={result?.status !== 'OK' || route?.passed === false}
      proposed={!approved && route?.passed === true}
      playbackCell={stage === 'Monitor' && approved ? routeCells?.[step] : undefined}/>
    {result && routeCells?.length === 1 && same(base, current) && <p>No movement required. The simulated crew is already at base.</p>}
    {stage === 'Monitor' && <div className="sortie-playback" aria-label="Simulated route playback">
      <button className="mission-button" disabled={!approved || lastStep < 1}
        onClick={() => { if (!playing && step >= lastStep) setStep(0); setPlaying(!playing) }}>
        {playing ? 'Pause route playback' : 'Play route playback'}
      </button>
      <input aria-label="Route playback step" type="range" min={0} max={Math.max(1, lastStep)}
        value={step} disabled={!approved || lastStep < 1} onChange={event => { setPlaying(false); setStep(Number(event.target.value)) }}/>
      <span>{approved && lastStep > 0 ? 'Step ' + (step + 1) + ' / ' + (lastStep + 1) : 'Approve a route with movement to play it'}</span>
    </div>}
  </section>
  const mapChooser = <div className="cell-toolbar sortie-map-chooser" aria-label="Map view">
    <button className="mission-button" aria-pressed={view === 'terrain'} onClick={() => setView('terrain')}>Computed route</button>
    <button className="mission-button" aria-pressed={view === 'mars'} onClick={() => setView('mars')}>Mars context</button>
  </div>
  const monitorActions = <section className="sortie-operations" aria-label="Operator actions">
    <p role="status">{pending ? 'Computing on the local API' : approved ? 'Operator approved · local API' : approvedId ? 'Active route: ' + approvedId + ' · previewing another candidate' : 'Awaiting a current operator-approved route'}</p>
    {result?.status === 'OK' && route?.passed && routeCells && <button className="mission-button mission-button-primary" onClick={() => setApproved(route.id)} disabled={approved}>Approve route</button>}
    {approved && !departed && routeCells?.some(cell => !same(cell, current)) && <button className="mission-button mission-button-primary" onClick={() => setDeparted(true)}>Record departure</button>}
  </section>
  return <div className="mission-site sortie-shell" data-stage={stage.toLowerCase()} aria-label="Simulated Marswalk workspace">
    <header className="sortie-workbench">
      <nav className="cell-toolbar sortie-tabs" aria-label="Marswalk stages">
        {tabs.map(tab => <button className="mission-button" key={tab} aria-pressed={stage === tab} onClick={() => switchStage(tab)}>{tab}</button>)}
      </nav>
      {stage !== 'Route' && <span className="sortie-workbench-context">{context}</span>}
      {stage === 'Monitor' && <a className="mission-button sortie-hazard-link" href={'/?' + new URLSearchParams({ cell: cellId, base: marsPoint.join(',') }) + '#monitor/rover/43/hazards'}>Hazard drill</a>}
    </header>
    {stage === 'Route' && <section className="sortie-content" aria-label="Route workspace">
      <header className="sortie-title">
        <span className="mission-badge">Simulation</span>
        <h1>Route · Synthetic Marswalk</h1>
        <p>{context}</p>
      </header>
      {marsMap}
      <details className="sortie-computed-details">
        <summary>Computed route · routing algorithm</summary>
        {map}
      </details>
    </section>}
    {stage === 'Analysis' && <>
      <nav className="sortie-analysis-nav" aria-label="Analysis sections">
        <a href="#route-comparison">Overview</a>
        {result && <a href="#sortie-candidates">Route ranking</a>}
        {route && <a href="#sortie-checks">Constraint checks</a>}
        <a href="#sortie-inputs">Inputs and provenance</a>
      </nav>
      <section className="sortie-analysis-main" aria-label="Analysis workspace">
        <header className="sortie-title sortie-analysis-title">
          <div><span className="mission-badge">Simulation · Analysis</span>
            <h1>{recommended ? (recommended.id === 'direct_return' ? 'Direct return recommended' : 'Science stop recommended') : 'Sortie analysis'}</h1>
          </div>
          {recommended && <span className="sortie-analysis-margin">{signedSeconds(recommended.margin_s)} reserve margin</span>}
        </header>
        <section aria-labelledby="route-comparison" className="sortie-analysis">
          <h2 id="route-comparison">Route comparison</h2>
          <p>Backend constraints and reserve checks for this sortie. Select a candidate to inspect its checks and path.</p>
          {result ? <>
            <div className="sortie-table" id="sortie-candidates"><table>
              <thead><tr><th scope="col">Candidate</th><th scope="col">Decision</th><th scope="col">Total time</th><th scope="col">Margin</th></tr></thead>
              <tbody>{candidates.map(candidate => <tr key={candidate.id}>
                <th scope="row"><button className="mission-button" aria-pressed={candidate === route}
                  onClick={() => selectCandidate(candidate.id)}>{candidate.id}</button></th>
                <td>{candidate === recommended ? 'Recommended' : candidate.passed ? 'Feasible' : 'Withheld'}</td>
                <td>{candidate.ledger?.total_use == null ? 'Unavailable' : Math.round(candidate.ledger.total_use) + ' s'}</td>
                <td>{signedSeconds(candidate.margin_s)}</td>
              </tr>)}</tbody>
            </table></div>
            {route && <div className="sortie-table" id="sortie-checks"><table>
              <caption>Checks for {route.id}</caption>
              <thead><tr><th scope="col">Constraint</th><th scope="col">Decision</th><th scope="col">Reason</th></tr></thead>
              <tbody>{route.constraints.map(({rule, outcome, reason}) =>
                <tr key={rule}><th scope="row">{rule.replaceAll('_', ' ')}</th><td>{outcome}</td><td>{reason}</td></tr>)}</tbody>
            </table></div>}
          </> : <p>{pending ? 'Calculating route candidates…' : 'Calculate a sortie to compare candidates.'}</p>}
        </section>
      </section>
      <aside className="sortie-analysis-preview" aria-label="Analysis maps and provenance">
        {view === 'mars' ? marsMap : map}
        {mapChooser}
        <section aria-labelledby="sortie-inputs">
          <h2 id="sortie-inputs">Inputs and provenance</h2>
          <dl className="sortie-metrics">
            <div><dt>Routing pack</dt><dd>{site.pack_id} · {site.pack_version}</dd></div>
            <div><dt>Terrain</dt><dd>Synthetic rehearsal grid</dd></div>
            <div><dt>Scenario</dt><dd>{site.scenario_id}</dd></div>
            <div><dt>Route calculation</dt><dd>{result ? 'Revision ' + result.revision : 'Awaiting result'}</dd></div>
          </dl>
        </section>
        {destination}
      </aside>
    </>}
    {stage === 'Monitor' && <section className="sortie-monitor" aria-label="Monitor workspace">
      <header className="sortie-title sortie-monitor-title">
        <div><span className="mission-badge">Simulated playback</span><h1>Mission monitor</h1></div>
        {mapChooser}
      </header>
      {monitorActions}
      {view === 'mars' ? marsMap : map}
      <section className="sortie-telemetry" aria-label="Simulated sortie status">
        <div><span>Return reserve</span><strong>{signedSeconds(route?.margin_s ?? null)}</strong><small>Margin for the selected route</small></div>
        <div><span>Playback</span><strong>{approved && lastStep > 0 ? Math.round(100 * step / lastStep) + '%' : 'Standby'}</strong><small>{lastStep > 0 ? lastStep + ' path segments' : 'No path movement'}</small></div>
        <div><span>Crew position</span><strong>Row {current[0]} · Col {current[1]}</strong><small>{departed ? 'Departure recorded' : 'At shelter'}</small></div>
        <div><span>Active route</span><strong>{approvedId ?? 'Pending approval'}</strong><small>{closures.length ? closures.join(', ') + ' closed' : 'Corridors open'}</small></div>
      </section>
    </section>}
    {stage !== 'Analysis' && <aside className="sortie-sidebar">
      {stage === 'Route' && destination}
      <section className="sortie-controls">
      <header className="sortie-panel-heading">
        <span className="mission-badge">Synthetic terrain</span>
        <h2>Simulated sortie</h2>
        <p>The backend computes paths on the local rehearsal grid. Mars imagery and rankings are context.</p>
      </header>
        {pending && <p className="sortie-result" aria-live="polite">Calculating a proposal…</p>}
        {!pending && !fault && !result && <p className="sortie-result">Settings changed. Calculate again to review a new route.</p>}
        {result && <section aria-label="Planning result" className="sortie-result">
          <div><h2>{statusText[result.status]}</h2>
            <p>Recommendation: {result.recommendation ?? 'None'}</p>
            <p>Return margin {signedSeconds(result.return_margin_s)} · {approved ? 'Operator approved' : 'Not approved'}</p>
          </div>
          {stage === 'Route' && result.status === 'OK' && route?.passed && routeCells &&
            <button className="mission-button mission-button-primary" onClick={() => switchStage('Monitor')}>Review route in Monitor</button>}
        </section>}
      {route && <dl className="sortie-metrics">
        <div><dt>Distance</dt><dd>{distance === null ? 'Unavailable' : distance.toFixed(1) + ' m'}</dd></div>
        <div><dt>Time incl. stops</dt><dd>{route.ledger?.total_use == null ? 'Unavailable' : Math.round(route.ledger.total_use) + ' s'}</dd></div>
        <div><dt>Max slope</dt><dd>{slope === null ? 'Unavailable' : slope.toFixed(1) + '°'}</dd></div>
        <div><dt>Margin above reserve</dt><dd>{signedSeconds(route.margin_s)}</dd></div>
      </dl>}
      {candidates.length > 0 && <section aria-label="Route candidates" className="sortie-candidates">
        {candidates.map(candidate => <button key={candidate.id} className="mission-button"
          aria-pressed={candidate === route} onClick={() => selectCandidate(candidate.id)}>
          <strong>{candidate.id}</strong><span>{candidate.id === approvedId ? 'Approved' : candidate === recommended ? 'Recommended' : candidate.passed ? 'Feasible' : 'Withheld'}</span>
        </button>)}
      </section>}
      <details className="sortie-settings" open={stage === 'Monitor' ? true : undefined}>
        <summary>Simulation controls</summary>
        <div>
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
      {departed && <button onClick={() => { setDeparted(false); selectBase(base); setClosures([]); setRemaining(initialBudget) }}>Start new sortie</button>}
        </div>
      </details>
      {fault && <><p role="alert">{fault}</p><button onClick={() => void calculate(true)}>Retry calculation</button></>}
      {result && <div className="sortie-details">
        <p>Completed work: {result.completed_task_ids.join(', ') || 'None'}</p>
      </div>}
      </section>
    </aside>}
  </div>
}
