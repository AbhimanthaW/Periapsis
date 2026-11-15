import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { describeFailure, getFixtureSite, postPlan } from './api'
import type { FixtureSite, PlanRequest, PlanResponse } from './api'
import { FixtureGrid } from './FixtureGrid'
import { seconds, signedSeconds, statusText } from './format'

type SiteState = { state: 'loading' } | { state: 'error'; reason: string } | { state: 'ready'; site: FixtureSite }
type Scenario = { closure_ids: string[]; remaining_s: number }
type PlanState =
  | { state: 'idle' }
  | { state: 'pending'; requestId: string }
  | { state: 'result'; requestId: string; data: PlanResponse }
  | { state: 'error'; requestId: string; reason: string }

const maxSeconds = 86_400
const scenarioSchema = z.object({
  closure_ids: z.array(z.string()),
  remaining_s: z.number().int().min(0).max(maxSeconds),
})
const storageKey = (site: FixtureSite) => `return-window-mission/scenario/v1/${site.pack_id}@${site.pack_version}`
const defaultScenario = (site: FixtureSite): Scenario => ({ closure_ids: [], remaining_s: site.remaining_s })

function normalise(site: FixtureSite, scenario: Scenario): Scenario {
  const chosen = new Set(scenario.closure_ids)
  return { closure_ids: site.closures.map(closure => closure.id).filter(id => chosen.has(id)), remaining_s: scenario.remaining_s }
}

function loadScenario(site: FixtureSite): Scenario {
  try {
    const parsed = scenarioSchema.safeParse(JSON.parse(localStorage.getItem(storageKey(site)) ?? 'null'))
    return parsed.success ? normalise(site, parsed.data) : defaultScenario(site)
  } catch {
    return defaultScenario(site)
  }
}

function saveScenario(site: FixtureSite, scenario: Scenario) {
  try { localStorage.setItem(storageKey(site), JSON.stringify(scenario)) } catch { /* storage unavailable */ }
}

const sameList = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((value, index) => value === b[index])

/** A response is accepted only if it answers exactly the latest request for this pack and scenario. */
function mismatch(site: FixtureSite, request: PlanRequest, response: PlanResponse): string | null {
  if (response.request_id !== request.request_id) return 'request ID'
  if (response.pack_id !== site.pack_id || response.pack_version !== site.pack_version) return 'pack identity'
  if (response.scenario_id !== site.scenario_id) return 'scenario'
  if (response.reserve_s !== request.reserve_s || !sameList(response.completed_task_ids, request.completed_task_ids)) return 'mission state'
  if (!sameList([...response.closure_ids].sort(), [...request.closure_ids].sort()) || response.remaining_s !== request.remaining_s) return 'inputs'
  return null
}

let requestCounter = 0
const nextRequestId = () => `mission-${Date.now().toString(36)}-${++requestCounter}`

function useFixtureSite() {
  const [state, setState] = useState<SiteState>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ state: 'loading' })
    getFixtureSite(controller.signal).then(result => {
      setState(result.ok ? { state: 'ready', site: result.data } : { state: 'error', reason: describeFailure(result) })
    }, () => {})
    return () => controller.abort()
  }, [attempt])
  return [state, () => setAttempt(value => value + 1)] as const
}

function usePlan(site: FixtureSite, scenario: Scenario) {
  const [plan, setPlan] = useState<PlanState>({ state: 'idle' })
  const [discarded, setDiscarded] = useState(0)
  const latest = useRef<string | null>(null)
  const closureKey = scenario.closure_ids.join(',')
  useEffect(() => {
    const request: PlanRequest = {
      schema_version: 1,
      request_id: nextRequestId(),
      pack_id: site.pack_id,
      pack_version: site.pack_version,
      scenario_id: site.scenario_id,
      checkpoint_id: site.checkpoint_id,
      shelter_id: site.shelter_id,
      closure_ids: scenario.closure_ids,
      completed_task_ids: site.completed_task_ids,
      remaining_s: scenario.remaining_s,
      reserve_s: site.reserve_s,
    }
    latest.current = request.request_id
    // Any change clears the previous result, so no stale route or recommendation stays visible.
    setPlan({ state: 'pending', requestId: request.request_id })
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      postPlan(request, controller.signal).then(result => {
        if (latest.current !== request.request_id) { setDiscarded(count => count + 1); return }
        if (!result.ok) { setPlan({ state: 'error', requestId: request.request_id, reason: describeFailure(result) }); return }
        const problem = mismatch(site, request, result.data)
        if (problem) {
          setDiscarded(count => count + 1)
          setPlan({ state: 'error', requestId: request.request_id, reason: `Response rejected: ${problem} does not match the request` })
          return
        }
        setPlan({ state: 'result', requestId: request.request_id, data: result.data })
      }, () => { if (latest.current !== request.request_id) setDiscarded(count => count + 1) })
    }, 120)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [site, closureKey, scenario.remaining_s])
  return { plan, discarded }
}

const recommendationText = (id: string) => id === 'direct_return' ? 'Return directly to shelter' : `Attempt ${id}, then return`

function Timeline({ label, total, remaining, reserve, note }: { label: string; total: number | null; remaining: number; reserve: number; note?: string }) {
  const span = Math.max(remaining, total ?? 0, 1)
  const pct = (value: number) => `${Math.max(0, Math.min(100, value / span * 100))}%`
  const budget = Math.max(0, remaining - reserve)
  const overrun = total === null ? 0 : Math.max(0, Math.min(total, remaining) - budget)
  return (
    <div className="mission-timeline">
      <div className="mission-timeline-head">
        <span>{label}</span>
        <span>{total === null ? 'No route' : seconds(total)}</span>
      </div>
      <div className="mission-timeline-bar" aria-hidden="true">
        <span className="mission-seg-reserve" style={{ left: pct(budget), width: pct(Math.min(reserve, remaining)) }}/>
        {total !== null && <span className="mission-seg-travel" style={{ left: 0, width: pct(Math.min(total, budget)) }}/>}
        {overrun > 0 && <span className="mission-seg-overrun" style={{ left: pct(budget), width: pct(overrun) }}/>}
        {total !== null && total > remaining && <span className="mission-seg-overrun" style={{ left: pct(remaining), width: pct(total - remaining) }}/>}
        <span className="mission-seg-limit" style={{ left: pct(remaining) }}/>
      </div>
      {note && <p className="mission-muted mission-small">{note}</p>}
    </div>
  )
}

function Results({ plan }: { plan: PlanState }) {
  if (plan.state === 'idle' || plan.state === 'pending') return (
    <section className="mission-card mission-results" aria-live="polite" data-plan-state="pending">
      <p className="mission-kicker">Return margin <span className="mission-badge">CALC</span></p>
      <p className="mission-big mission-muted" role="status">Computing…</p>
      <p className="mission-muted">No recommendation while the plan is recalculated.</p>
    </section>
  )
  if (plan.state === 'error') return (
    <section className="mission-card mission-results mission-callout-fail" aria-live="polite" data-plan-state="error">
      <p className="mission-kicker">Plan not available</p>
      <p className="mission-big">No plan</p>
      <p role="alert">{plan.reason}</p>
      <p className="mission-muted">No route or recommendation is shown.</p>
    </section>
  )
  const data = plan.data
  const ok = data.status === 'OK'
  const remaining = data.remaining_s, reserve = data.reserve_s
  return (
    <section className="mission-card mission-results" aria-live="polite" data-plan-state={data.status} data-request-id={data.request_id}>
      <div className="mission-results-head">
        <div>
          <p className="mission-kicker">Return margin <span className="mission-badge">CALC</span></p>
          <p className={`mission-big ${data.return_margin_s === null ? 'mission-muted' : data.return_margin_s < 0 ? 'mission-fail-text' : ''}`} data-testid="return-margin">
            {data.return_margin_s === null ? 'No route' : signedSeconds(data.return_margin_s)}
          </p>
        </div>
        <span className={ok ? 'mission-pass' : 'mission-fail'} data-testid="plan-status">{data.status}</span>
      </div>
      <p className={ok ? 'mission-muted' : 'mission-fail-text'}>{statusText[data.status]}</p>

      <dl className="mission-facts">
        <dt>Return to shelter</dt><dd data-testid="return-seconds">{data.direct_return ? seconds(data.direct_return.seconds) : 'No route'}</dd>
        <dt>Remaining</dt><dd>{seconds(remaining)}</dd>
        <dt>Reserve</dt><dd>{seconds(reserve)}</dd>
        <dt>Reverse control</dt><dd>{data.reverse_control ? seconds(data.reverse_control.seconds) : 'No route'}</dd>
      </dl>

      <div className="mission-timelines">
        <Timeline label="Direct return" total={data.direct_return?.seconds ?? null} remaining={remaining} reserve={reserve}/>
        {data.science.map(task => (
          <Timeline key={task.id} label={`Science ${task.id}`} total={task.seconds} remaining={remaining} reserve={reserve}
            note="Travel out, dwell and return to shelter, combined by the service"/>
        ))}
        <p className="mission-legend"><i className="mission-swatch-travel"/>Modeled time <i className="mission-swatch-reserve"/>Reserve <i className="mission-swatch-overrun"/>Into reserve</p>
      </div>

      <div className="mission-science">
        <p className="mission-kicker">Science feasibility</p>
        {data.science.length ? (
          <table className="mission-table">
            <thead><tr><th scope="col">Task</th><th scope="col">Time</th><th scope="col">Margin</th><th scope="col">Feasible</th></tr></thead>
            <tbody>{data.science.map(task => (
              <tr key={task.id} data-testid={`science-${task.id}`}>
                <td><code>{task.id}</code></td>
                <td>{task.seconds === null ? 'No route' : seconds(task.seconds)}</td>
                <td>{signedSeconds(task.margin_s)}</td>
                <td className={task.feasible ? 'mission-pass-text' : 'mission-fail-text'}>{task.feasible ? 'Yes' : 'No'}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <p className="mission-muted">Withheld. Science is evaluated only when the direct return fits the reserve.</p>}
      </div>

      <div className="mission-recommendation" data-testid="recommendation">
        <p className="mission-kicker">Recommendation</p>
        {data.recommendation
          ? <p className="mission-rec-value">{recommendationText(data.recommendation)} <code>{data.recommendation}</code></p>
          : <p className="mission-fail-text">No recommendation · {data.status}</p>}
      </div>

      <div>
        <p className="mission-kicker">Completed work</p>
        <ul className="mission-list" data-testid="completed-work">
          {data.completed_task_ids.map(task => <li key={task}><span className="mission-pass-text">✓</span> <code>{task}</code> retained</li>)}
        </ul>
      </div>
      <p className="mission-muted mission-small"><code>{data.pack_id}@{data.pack_version}</code> · {data.scenario_id} · request <code>{data.request_id}</code></p>
    </section>
  )
}

function Controls({ site, scenario, onChange }: { site: FixtureSite; scenario: Scenario; onChange: (update: (current: Scenario) => Scenario) => void }) {
  // Functional updates so rapid inputs compose instead of overwriting each other.
  const toggle = (id: string) => onChange(current => {
    const chosen = new Set(current.closure_ids)
    if (chosen.has(id)) chosen.delete(id)
    else chosen.add(id)
    return normalise(site, { ...current, closure_ids: [...chosen] })
  })
  const setRemaining = (value: number) => {
    if (Number.isInteger(value) && value >= 0 && value <= maxSeconds) onChange(current => ({ ...current, remaining_s: value }))
  }
  const sliderMax = Math.max(240, site.remaining_s * 2, scenario.remaining_s)
  return (
    <section className="mission-card mission-controls" aria-label="Scenario inputs">
      <div>
        <p className="mission-kicker">Corridor closures</p>
        <div className="mission-toggles">
          {site.closures.map(closure => {
            const active = scenario.closure_ids.includes(closure.id)
            return (
              <button key={closure.id} className="mission-button" aria-pressed={active} onClick={() => toggle(closure.id)}>
                {active ? 'Reopen' : 'Close'} {closure.id} corridor
              </button>
            )
          })}
        </div>
      </div>
      <div>
        <label className="mission-kicker" htmlFor="mission-remaining">Remaining time</label>
        <div className="mission-remaining">
          <input id="mission-remaining-range" type="range" min={0} max={sliderMax} step={5} value={scenario.remaining_s}
            aria-label="Remaining time slider" onChange={event => setRemaining(Number(event.target.value))}/>
          <input id="mission-remaining" type="number" min={0} max={maxSeconds} step={1} value={scenario.remaining_s}
            onChange={event => setRemaining(Number(event.target.value))}/>
          <span className="mission-muted">s</span>
        </div>
      </div>
      <div className="mission-fixed">
        <span>Reserve {seconds(site.reserve_s)}</span>
        <span>Checkpoint <code>{site.checkpoint_id}</code></span>
        <span>Shelter <code>{site.shelter_id}</code></span>
        <span className="mission-muted">Fixed by scenario</span>
        <button className="mission-button" onClick={() => onChange(() => defaultScenario(site))}>Reset inputs</button>
      </div>
    </section>
  )
}

function Marswalk({ site }: { site: FixtureSite }) {
  const [scenario, setScenario] = useState<Scenario>(() => loadScenario(site))
  useEffect(() => { saveScenario(site, scenario) }, [site, scenario])
  const { plan, discarded } = usePlan(site, scenario)
  const result = plan.state === 'result' ? plan.data : null
  const route = result?.direct_return?.cells ?? null
  return (
    <div className="mission-sim">
      <div className="mission-sim-main">
        <Controls site={site} scenario={scenario} onChange={setScenario}/>
        <FixtureGrid site={site} activeClosures={scenario.closure_ids} route={route} inspectOnly={result !== null && result.status !== 'OK'}/>
        {discarded > 0 && <p className="mission-muted mission-small" data-testid="discarded">Discarded {discarded} superseded response{discarded === 1 ? '' : 's'}.</p>}
      </div>
      <Results plan={plan}/>
    </div>
  )
}

export function Simulation() {
  const [siteState, retry] = useFixtureSite()
  if (siteState.state === 'loading') return <p className="mission-pad mission-muted" role="status">Loading simulation fixture…</p>
  if (siteState.state === 'error') return (
    <div className="mission-pad">
      <section className="mission-card mission-callout-fail" role="alert">
        <p className="mission-kicker">Simulation unavailable</p>
        <p>{siteState.reason}</p>
        <button className="mission-button" onClick={retry}>Retry</button>
      </section>
    </div>
  )
  return <Marswalk key={`${siteState.site.pack_id}@${siteState.site.pack_version}`} site={siteState.site}/>
}
