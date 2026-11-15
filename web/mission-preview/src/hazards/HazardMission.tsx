import { useId, useState } from 'react'
import { Action, Panel } from '../MissionUI'
import { archive, recommendation, terrain } from './replay'
import type { Cell, Frame, HazardReplay, Platform, RouteAssessment, RouteId, Span } from './replay'
import './hazards.css'

const minutes = (value: number | null) => value === null ? '—' : (value / 60).toFixed(1) + ' min'
const clock = (utc: string) => utc.slice(11, 19) + ' UTC'
const elevationColors = ['#3d3028', '#49392e', '#534033', '#614a39', '#6e5140', '#7b5944', '#89614a', '#996d53', '#aa7959', '#b68662']
const spanPath = (spans: Span[]) => spans.map(([r, c, count]) => `M${c} ${r}h${count}v1h-${count}z`).join('')
const elevationPaths = terrain.elevation.map(spanPath)
const exclusions = spanPath(terrain.excluded)
const unknown = spanPath(terrain.unknown)
const points = (cells: Cell[]) => cells.map(([r, c]) => `${c + 0.5},${r + 0.5}`).join(' ')

function HazardMap({ frame, routes, active, selected }: {
  frame: Frame; routes: RouteAssessment[]; active: RouteId; selected: RouteId
}) {
  const hatch = useId()
  const activeBlocked = routes.some(route => route.id === active && route.status === 'blocked')
  const [zoom, setZoom] = useState(false)
  const [showTerrain, setShowTerrain] = useState(true)
  const [showDust, setShowDust] = useState(true)
  return <section className="hazard-map" aria-label="Hazard map">
    <div className="hazard-map-tools">
      <label><input type="checkbox" checked={showTerrain} onChange={event => setShowTerrain(event.target.checked)}/> Terrain limits</label>
      <label><input type="checkbox" checked={showDust} onChange={event => setShowDust(event.target.checked)}/> Dust footprint</label>
      <Action onClick={() => setZoom(!zoom)}>{zoom ? 'Fit terrain' : 'Focus routes'}</Action>
    </div>
    <svg className="hazard-grid" viewBox={zoom ? '24 26 98 99' : `0 0 ${terrain.shape[1]} ${terrain.shape[0]}`} role="img"
      aria-label={`Synthetic terrain and return corridors. Route ${active} is active. ${frame.footprint.length ? 'Simulated dust footprint mapped.' : 'No active dust footprint.'}`}>
      <defs><pattern id={hatch} width="2" height="2" patternUnits="userSpaceOnUse">
        <path d="M0 0L2 2M-1 1L1 3M1 -1L3 1" stroke="#bca79a" strokeWidth=".4"/>
      </pattern></defs>
      <rect width={terrain.shape[1]} height={terrain.shape[0]} fill="#211a16"/>
      {elevationPaths.map((path, i) => <path key={i} d={path} fill={elevationColors[Math.min(i, elevationColors.length - 1)]}/>)}
      {showTerrain && <>
        <path d={exclusions} fill="#352526" opacity=".96"/>
        <path d={unknown} fill={`url(#${hatch})`} opacity=".7"/>
      </>}
      {showDust && frame.footprint.length > 0 &&
        <path className={'hazard-footprint footprint-' + frame.extent} d={spanPath(frame.footprint)} data-testid="dust-footprint"/>}
      {[...routes].sort((a, b) => Number(a.id === selected) - Number(b.id === selected)).map(route => {
        const middle = route.cells[Math.floor(route.cells.length / 2)]
        const className = 'hazard-line' + (route.status === 'blocked' ? ' blocked' : route.id === active ? ' active' : '')
          + (route.id === selected ? ' selected' : '')
        return <g key={route.id} data-route={route.id} className={className}>
          <polyline className="hazard-line-shadow" points={points(route.cells)}/>
          <polyline className="hazard-line-path" points={points(route.cells)}/>
          {middle && <text x={middle[1] + .5} y={middle[0] - 3} textAnchor="middle">{route.id}</text>}
        </g>
      })}
      {([[terrain.start, 'P', 'Checkpoint'], [terrain.shelter, 'H', 'Shelter and drill station']] as const).map(
        ([[r, c], mark, name]) => <g className="hazard-point" key={mark}>
          <title>{name}</title><circle cx={c + .5} cy={r + .5} r="2.6"/>
          <text x={c + .5} y={r + .5} dy=".34em" textAnchor="middle">{mark}</text>
        </g>)}
      <g className="hazard-map-scale" transform={zoom ? 'translate(30 117)' : 'translate(7 151)'}>
        <path d="M0 -1V0H20V-1"/><text x="10" y="-2" textAnchor="middle">100 m</text>
      </g>
    </svg>
    <div className="hazard-map-key">
      <span><i className={'key-line' + (activeBlocked ? ' key-blocked' : '')}/> {activeBlocked ? 'Blocked active route' : 'Active route'}</span>
      <span><i className="key-line alternate"/> Alternate</span>
      <span><i className="key-dust"/> Simulated dust</span>
      <span><i className="key-terrain"/> Steep / unknown terrain</span>
    </div>
    <p className="hazard-map-caption">P checkpoint · H shelter and station · {terrain.cell_m} m cells · Synthetic local grid</p>
  </section>
}

function ForecastEvidence({ frame, expanded }: { frame: Frame; expanded: boolean }) {
  const forecast = frame.forecast
  const [variable, setVariable] = useState('pressure_pa')
  const variables = forecast.status === 'issued' ? new Map(forecast.rows.map(row => [row.target, row.label])) : null
  const latest = forecast.status === 'issued' ? forecast.latest[variable] : null
  const observation = archive.messages[0]
  return <div className="hazard-evidence">
    <details open={expanded || undefined}>
      <summary>Station forecast <span className="badge">MODEL · SIM INPUTS</span></summary>
      {forecast.status === 'unavailable' ? <p>{forecast.reason} The dust drill can still run.</p> : <>
        <p>Advisory point outlook at {forecast.station.lat_deg}° N, {Math.abs(forecast.station.lon_east_deg)}° W.
          This synthetic station uses a separate replay clock and has no footprint on the routing grid.</p>
        <p className="mono">Issued {forecast.issued_utc} · {forecast.model_id}</p>
        <p>{forecast.sensors_fresh.length ? 'Fresh sensor bins · ' + forecast.sensors_fresh.join(', ') + '.' : 'No usable current sensor bins.'}</p>
        <p>Bands describe residuals on synthetic data. Mars forecast confidence is unestablished.</p>
        {expanded && <div className="hazard-forecast-control">
          <label>Weather variable <select value={variable} onChange={event => setVariable(event.target.value)}>
            {Array.from(variables ?? [], ([id, label]) => <option value={id} key={id}>{label}</option>)}
          </select></label>
          <p className="mono">{latest ? 'Latest sample ' + latest.time_utc : 'No recent sample for this variable.'}</p>
        </div>}
        <div className="hazard-forecast-table">
          <table>
            <thead><tr><th scope="col">Weather</th><th scope="col">Horizon</th><th scope="col">P50 (P10–P90)</th><th scope="col">Method</th></tr></thead>
            <tbody>{forecast.rows.filter(row => expanded ? row.target === variable : row.target === 'dust_tau' || row.target === 'wind_ms')
              .map(row => <tr key={row.target + row.horizon} title={row.reason ?? row.kit}>
                <th scope="row">{row.label}</th><td>{row.horizon}<br/>{clock(row.valid_utc)}</td>
                <td>{row.p50} {row.unit === '1' ? 'τ' : row.unit}<br/><span className="muted">{row.p10} to {row.p90}</span></td>
                <td>{row.status === 'model' ? 'Learned model' : row.status === 'abstained' ? 'Climatology (abstained)' : 'Climatology'}
                  {expanded && row.reason && <span className="hazard-method-reason">{row.reason}</span>}
                  {expanded && row.track_record.n != null && row.track_record.coverage_p10_p90 != null &&
                    <span className="hazard-method-reason">Synthetic test coverage {Math.round(row.track_record.coverage_p10_p90 * 100)}% · n={row.track_record.n}</span>}</td>
              </tr>)}</tbody>
          </table>
        </div>
        {expanded && <p>Horizons are in Mars hours. Forecast rows are independent of route eligibility.</p>}
      </>}
    </details>
    <details open={expanded || undefined}>
      <summary>Jezero MEDA <span className="badge">OBS · ARCHIVE</span></summary>
      <p><strong>{observation.value} {observation.unit}</strong> horizontal wind, Perseverance sol 36.</p>
      <p className="mono">{observation.time_utc}</p>
      <p>Historical observation. No uncertainty is recorded in this sample. Jezero geography and this reading serve as reference context for the drill.</p>
      <a href="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html">NASA Planetary Data System</a>
    </details>
  </div>
}

function RouteCard({ route, active, recommended, selected, choose }: {
  route: RouteAssessment; active: boolean; recommended: boolean; selected: boolean; choose: () => void
}) {
  return <article className={'hazard-route-card' + (selected ? ' picked' : '')}>
    <button className="hazard-route-choice" aria-pressed={selected} onClick={choose}>
      <strong>Route {route.id} · {route.id === 'A' ? 'Northern crossing' : 'Southern detour'}</strong>
      <span className={route.status === 'feasible' ? 'good' : 'bad'}>
        {route.status === 'feasible' ? 'Within drill limits' : route.status === 'blocked' ? 'Blocked' : 'Infeasible'}
      </span>
    </button>
    {(active || recommended) && <div className="hazard-route-flags">{active && <span className="badge">ACTIVE PLAN</span>}
      {recommended && <span className="badge">REVIEW ADVISED</span>}</div>}
    <dl className="hazard-readouts">
      <div><dt>Travel time</dt><dd>{minutes(route.seconds)}</dd></div>
      <div><dt>Distance</dt><dd>{route.distance_m === null ? '—' : route.distance_m + ' m'}</dd></div>
      <div><dt>Time above reserve</dt><dd>{minutes(route.margin_s)}</dd></div>
      <div><dt>In dust footprint</dt><dd>{route.exposure_m} m</dd></div>
      {route.energy_margin_wh !== null && <div><dt>Battery above reserve</dt><dd>{route.energy_margin_wh.toLocaleString()} Wh</dd></div>}
      {route.crew && <div><dt>EVA envelope</dt><dd>{route.crew.class}</dd></div>}
    </dl>
    {route.reasons.map(reason => <p className="bad" key={reason}>{reason}</p>)}
    {route.crew?.reason && <p className="bad">{route.crew.reason}</p>}
    {!!route.checks.length && <details>
      <summary>Constraint checks</summary>
      <ul>{route.checks.map(check => <li key={check.id}>{check.reason} <span className="mono">({check.status})</span></li>)}
        {route.crew?.margin_s != null && <li>Smallest crew reserve margin {minutes(route.crew.margin_s)} at flat pace.</li>}
      </ul>
    </details>}
  </article>
}

export function HazardMission({ replay, platform, stage, go }: {
  replay: HazardReplay; platform: Platform; stage: 'route' | 'monitor' | 'analysis'; go: (stage: string) => void
}) {
  const { frame } = replay
  const operator = replay.operators[platform]
  const routes = frame.routes[platform]
  const active = routes.find(route => route.id === operator.active)!
  const proposed = recommendation(frame, platform, active.id)
  const [selection, setSelection] = useState<RouteId | null>(null)
  const selected = routes.find(route => route.id === (selection ?? proposed ?? active.id))!
  const alternate = routes.find(route => route.id !== active.id)!
  const stale = frame.weather.status === 'stale'
  const pending = selected.id !== active.id || operator.holding
  const canApprove = stage === 'monitor' && pending && !stale && selected.status === 'feasible'
  const headline = stale ? 'Station data stale' : active.status !== 'feasible' ? 'Active route blocked'
    : operator.holding ? 'Holding by operator decision' : proposed ? 'Review a detour' : 'Active route within drill limits'
  const deltaTime = active.seconds !== null && alternate.seconds !== null ? alternate.seconds - active.seconds : null
  const dustLabel = { nominal: 'Below drill threshold', caution: 'Caution', warning: 'Warning', stale: 'Expired' }[frame.weather.status]

  return <div className="hazard-workspace">
    <header className="hazard-header">
      <div><p className="caption">SIMULATED PLAYBACK · {platform === 'human' ? 'WALKING EVA' : 'ROVER'}</p>
        <h1>{stage === 'analysis' ? 'Hazard evidence' : 'Hazard mapping & routing'}</h1></div>
      <span className={'hazard-headline ' + (stale || active.status !== 'feasible' ? 'bad' : proposed || operator.holding ? 'caution' : 'good')}
        role="status">{headline}</span>
    </header>
    <div className="hazard-layout">
      <Panel name="Environmental changes" className="hazard-dock">
        <h2>What changed</h2>
        <p>{frame.detail}</p>
        <dl className="hazard-readouts">
          <div><dt>Drill time</dt><dd>{clock(frame.time_utc)}</dd></div>
          <div><dt>Station dust τ <span className="badge">SIM</span></dt><dd>{frame.weather.value.toFixed(2)} · {dustLabel}</dd></div>
          <div><dt>Sample age</dt><dd>{Math.round(frame.weather.age_s)} s / {frame.weather.freshness_limit_s} s limit</dd></div>
          <div><dt>Sample time</dt><dd>{clock(frame.weather.observed_utc)}</dd></div>
        </dl>
        {platform === 'rover' && frame.weather.solar_disabled && <p className="caution">Solar charging credit withheld.</p>}
        <div className="hazard-playback">
          <Action primary disabled={replay.complete} onClick={replay.toggle}>{replay.playing ? 'Pause' : 'Play drill'}</Action>
          <Action disabled={replay.complete} onClick={replay.advance}>Next update</Action>
          <Action onClick={() => { replay.restart(); setSelection(null) }}>New drill</Action>
        </div>
        <p className="hazard-step mono">Update {frame.index + 1} / {replay.count} · {replay.source === 'runtime' ? 'Local compute' : replay.source === 'fallback' ? 'Bundled fallback' : 'Offline bundle'}</p>
        <ForecastEvidence frame={frame} expanded={stage === 'analysis'}/>
        {stage !== 'analysis' && <Action onClick={() => go('analysis')}>Inspect evidence</Action>}
      </Panel>

      <HazardMap frame={frame} routes={routes} active={active.id} selected={selected.id}/>

      <Panel name="Route decisions" className="hazard-dock">
        <h2>Return options</h2>
        <p className="hazard-reason">
          {stale ? 'Approval is paused until a fresh station reading arrives. The last closure remains on the map.'
            : active.status === 'blocked' ? (proposed ? 'The northern route crosses the exclusion. The detour stays outside it.' : 'The active route crosses the exclusion. No alternate passes the drill checks.')
            : proposed && deltaTime !== null ? `The detour avoids ${active.exposure_m - alternate.exposure_m} m of dust exposure and adds ${minutes(deltaTime)} to the return.`
            : active.status !== 'feasible' ? 'The active route fails a required check. Review its constraints before proceeding.'
            : 'The active plan stays in place. Both corridors are evaluated against the drill terrain and reserves.'}
        </p>
        {routes.map(route => <RouteCard key={route.id} route={route} active={route.id === active.id}
          recommended={route.id === proposed} selected={route.id === selected.id} choose={() => setSelection(route.id)}/>)}
        <p className="hazard-confidence">Feasibility uses deterministic checks and scenario assumptions. Safety confidence on Mars is unestablished.</p>
        {stage === 'monitor' ? <>
          <div className="hazard-decision">
            <Action primary disabled={!canApprove} onClick={() => { replay.decide(platform, selected.id); setSelection(null) }}>
              {selected.id === active.id && operator.holding ? 'Resume ' + active.id : 'Approve route ' + selected.id}
            </Action>
            <Action disabled={operator.holding} onClick={() => replay.decide(platform, active.id, true)}>Hold position</Action>
          </div>
          <div className="hazard-decision-record" aria-live="polite">{operator.history.length
            ? operator.history.at(-1)!.kind + ' · Route ' + operator.history.at(-1)!.route
            : 'Route A loaded from the drill plan.'}</div>
        </> : <Action onClick={() => go('monitor')}>Open Monitor to decide</Action>}
        {!!operator.history.length && <details className="hazard-history">
          <summary>Decision log · {operator.history.length}</summary>
          <ol>{operator.history.map((item, index) => <li key={index}>{clock(item.time)} · {item.kind} · Route {item.route}</li>)}</ol>
        </details>}
      </Panel>
    </div>
  </div>
}
