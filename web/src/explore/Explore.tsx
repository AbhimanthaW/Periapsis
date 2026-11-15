import { useEffect, useRef, useState } from 'react'
import { regions } from '../atlas/data'
import RankedAreas from '../atlas/RankedAreas'
import { describeFailure, getCellContext, getRegionEvidence, hpxId, locateCell } from '../mission/api'
import type { CellContext } from '../mission/api'
import { EvidencePanel, RegionalContext } from '../mission/SiteInvestigation'
import { SiteMap } from '../mission/SiteMap'
import { contextFor, pinnedSite } from '../mission/site'
import { arcadiaScenario } from '../../mission-preview/src/objective-methods/arcadia'
import display from '../../../pipeline/evidence/arcadia-planitia/display-metadata.json' with { type: 'json' }
import { Globe } from './Globe'
import type { Layer, Point } from './Globe'
import { Sortie } from './Sortie'
import type { Stage } from './Sortie'
import '../mission/mission.css'
import '../atlas/atlas.css'
import './explore.css'

const signed = ([lon, lat]: Point): Point => [lon >= 180 ? lon - 360 : lon, lat]
const arcadiaPoint = signed(display.center_lon_lat_deg as Point)
function initialSelection() {
  const params = new URLSearchParams(location.search)
  const cell = params.get('cell') ?? ''
  const parts = params.get('base')?.split(',')
  const coords = parts?.length === 2 && parts.every(part => part.trim()) ? parts.map(Number) : undefined
  const base = coords && Math.abs(coords[0]) <= 180 && Math.abs(coords[1]) <= 90 ? coords as Point : undefined
  const stage = ({ route: 'Route', analysis: 'Analysis', monitor: 'Monitor' } as Record<string, Stage | undefined>)[params.get('walk') ?? '']
  return { cell, base, stage, objective: params.get('objective')?.trim().slice(0, 300) ?? '',
    method: params.get('method'), excludes: params.get('exclude')?.split(','),
    layer: params.get('layer') === 'mola' ? 'mola' as const : 'viking' as const, region: params.get('region'), demo: params.get('demo') === '1', ranking: params.get('panel') === 'ranking' }
}

export default function Explore() {
  const [initial] = useState(initialSelection)
  const [cellId, setCellId] = useState(initial.cell)
  const [cell, setCell] = useState<CellContext | null>(null)
  const [base, setBase] = useState(initial.base)
  const [center, setCenter] = useState<Point>([0, 0])
  const [layer, setLayer] = useState<Layer>(initial.layer)
  const [pickBase, setPickBase] = useState(false)
  const [objective, setObjective] = useState(initial.objective)
  const [demoPreset, setDemoPreset] = useState(false)
  const [draftId, setDraftId] = useState(initial.cell)
  const [orientation, setOrientation] = useState<string>()
  const [rank, setRank] = useState(initial.ranking)
  const [simulation, setSimulation] = useState(Boolean(initial.stage && initial.base))
  const [baseChecked, setBaseChecked] = useState(!initial.stage || !initial.base)
  const [fault, setFault] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [locating, setLocating] = useState(false)
  const [position, setPosition] = useState<Point>()
  const request = useRef<AbortController | null>(null)
  const lastPick = useRef<(() => void) | null>(null)

  function select(id: string, point?: Point, nextBase?: Point, namedFeature?: string, preset = false) {
    setCellId(id)
    setDraftId(id)
    setPosition(point)
    setOrientation(namedFeature)
    setBase(nextBase)
    setSimulation(false)
    setRank(false)
    setPickBase(false)
    setDemoPreset(preset)
    setFault('')
    const params = new URLSearchParams({ cell: id })
    if (nextBase) params.set('base', nextBase.join(','))
    if (preset) params.set('demo', '1')
    const globeLink = location.pathname === '/' && location.hash === '#globe'
    history.replaceState(null, '', globeLink ? '/?' + params + '#globe' : '/explore?' + params)
  }

  async function pick(point: Point, forBase: boolean, recenter = false, preset = false, namedFeature?: string) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    lastPick.current = () => { void pick(point, forBase, recenter, preset, namedFeature) }
    setLocating(true)
    setSimulation(false)
    setFault('')
    try {
      const response = await locateCell(point, controller.signal)
      if (controller.signal.aborted) return
      if (!response.ok) { setFault(describeFailure(response)); return }
      lastPick.current = null
      select(response.data.id, point, forBase ? point : undefined, namedFeature, preset)
      if (recenter) setCenter(point)
    } catch (error) {
      if (!controller.signal.aborted) setFault(String(error))
    } finally {
      if (!controller.signal.aborted) setLocating(false)
    }
  }

  function demo() {
    setObjective(arcadiaScenario.objective)
    setLayer('mola')
    setCenter(arcadiaPoint)
    void pick(arcadiaPoint, true, true, true)
  }

  useEffect(() => {
    const alias = new AbortController()
    if (initial.demo) demo()
    else if (initial.region && !initial.cell) {
      request.current = alias
      const resolveAlias = () => {
        setLocating(true)
        getRegionEvidence(initial.region!, alias.signal).then(response => {
          if (alias.signal.aborted) return
          setLocating(false)
          if (response.ok) {
            select(response.data.anchor_cell_id, undefined, undefined, initial.region ?? undefined)
            lastPick.current = null
          } else setFault(describeFailure(response))
        }, () => {})
      }
      lastPick.current = resolveAlias
      resolveAlias()
    }
    return () => { request.current?.abort(); alias.abort() }
    // The preset applies only on the initial deep link or an explicit button press.
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    if (!cellId) return
    setCell(null)
    if (!hpxId.safeParse(cellId).success) { setFault('Enter a valid Nside 128 cell ID.'); return }
    getCellContext(cellId, controller.signal).then(response => {
      if (controller.signal.aborted) return
      if (response.ok && response.data.cell.id === cellId) {
        setCell(response.data)
        if (!position) setCenter(signed(response.data.cell.centroid))
      } else setFault(response.ok ? 'The service returned a different cell.' : describeFailure(response))
    }, () => {})
    return () => controller.abort()
  }, [cellId, attempt])

  useEffect(() => {
    if (!initial.base || !initial.cell) return
    const controller = new AbortController()
    locateCell(initial.base, controller.signal).then(response => {
      if (controller.signal.aborted) return
      if (!response.ok || response.data.id !== initial.cell) setBase(value => value === initial.base ? undefined : value)
      setBaseChecked(true)
    }, () => { if (!controller.signal.aborted) { setBase(undefined); setBaseChecked(true) } })
    return () => controller.abort()
  }, [initial])

  const context = !locating && cell?.cell.id === cellId ? cell : null
  const evidence = context?.local_evidence
  const site = context?.evidence_site_id ? pinnedSite(context.evidence_site_id) : undefined
  const asset = contextFor(site)
  const trusted = evidence && site && evidence.package_sha256 === site.package_sha256 &&
    evidence.query_sha256 === site.query_sha256 && evidence.result.package_id === site.package_id &&
    evidence.result.package_version === site.package_version
  const feature = context?.evidence_site_id && regions.find(region => region.id === context.evidence_site_id)
  const namedFeature = regions.find(region => region.id === orientation)
  const selectedPoint = context ? position ?? signed(context.cell.centroid) : undefined

  return <main className="mission-app cell-workspace">
    <header className="mission-masthead">
      <a className="mission-brand" href="/explore">Return Window</a>
      <nav className="mission-nav" aria-label="Workspaces">
        <button className="mission-link" onClick={() => { setRank(false); setSimulation(false) }}>Explore</button>
        <button className="mission-link" onClick={() => { setRank(true); setSimulation(false) }}>Ranked cells</button>
        {import.meta.env.VITE_PACKAGED_RELEASE === '1' && <a href="/demo/">Operations UI</a>}
        <button className="mission-button mission-button-primary" onClick={demo}>Demo</button>
      </nav>
    </header>
    {rank ? <RankedAreas initialObjective={objective} back={() => setRank(false)} openCell={id => {
      request.current?.abort()
      lastPick.current = null
      setLocating(false)
      select(id)
    }}/> : simulation && base && baseChecked ? <Sortie key={cellId + '/' + base.join(',')} cellId={cellId} marsPoint={base} demo={demoPreset} initialStage={initial.stage}
      scienceObjective={demoPreset ? 'shallow subsurface ice' : objective} methodInput={initial.method}
      exclusionsInput={initial.excludes} initialLayer={layer}/> :
      <div className="mission-site">
        <div className="mission-site-main">
          <section className="mission-card">
            <h1>Explore Mars</h1>
            <form className="cell-toolbar" onSubmit={event => {
              event.preventDefault()
              request.current?.abort()
              lastPick.current = null
              setLocating(false)
              select(draftId.trim())
            }}>
              <label>HEALPix cell <input value={draftId} onChange={event => setDraftId(event.target.value)} placeholder="HPX128:…"/></label>
              <button type="submit" disabled={!draftId.trim()}>Open cell</button>
            </form>
            <label>Named feature for orientation <select value="" onChange={event => {
              const feature = regions.find(item => item.id === event.target.value)
              if (feature) void pick(feature.geography.center, false, true, false, feature.id)
            }}>
              <option value="">Choose an approximate location</option>
              {regions.map(region => <option key={region.id} value={region.id}>{region.name}</option>)}
            </select></label>
            <label>Basemap <select value={layer} onChange={event => setLayer(event.target.value as Layer)}>
              <option value="viking">Viking colour</option><option value="mola">MOLA relief</option>
            </select></label>
            <Globe {...{ center, setCenter, layer, base }} selected={selectedPoint} pick={point => void pick(point, pickBase)}/>
            <div className="cell-toolbar">
              <button aria-pressed={pickBase} onClick={() => setPickBase(value => !value)}>Set base</button>
              {pickBase && <span>Pick a point on the globe or select the globe centre.</span>}
              {context && <button onClick={() => void pick(signed(context.cell.centroid), true)}>Use cell centre as base</button>}
            </div>
          </section>
          <form className="mission-card" onSubmit={event => { event.preventDefault(); setRank(true) }}>
            <label>Science objective <input value={objective} onChange={event => setObjective(event.target.value)} maxLength={300}/></label>
            <button>Review ranking</button>
          </form>
        </div>
        <div className="mission-site-side">
          {locating && <p role="status">Resolving Mars coordinates…</p>}
          {fault && <section className="mission-card"><p role="alert">{fault}</p><button onClick={() => {
            setFault('')
            if (lastPick.current) lastPick.current()
            else setAttempt(value => value + 1)
          }}>Retry lookup</button></section>}
          {context && <>
            <section className="mission-card">
              <h2>{feature ? feature.name + ' · ' : ''}{cellId}</h2>
              {namedFeature && <p>{namedFeature.name} · approximate research label</p>}
              {base ? <p>Candidate base {base[1].toFixed(5)}°, {base[0].toFixed(5)}° east longitude.</p>
                : <p>Set a base to record an exact Mars position.</p>}
              <p><strong>Tactical routing withheld.</strong> A qualified terrain pack is required for the base and route.</p>
              {base && <button className="mission-button mission-button-primary" onClick={() => setSimulation(true)}>
                Enter simulated Marswalk
              </button>}
              <p className="mission-muted">The Marswalker rehearsal uses its own terrain grid and carries this Mars cell as context.</p>
            </section>
            <RegionalContext data={{ anchor_cell_id: cellId, cell_context: context.cell_context }}/>
            <section className="mission-card">
              <h2>Local calculation evidence</h2>
              {trusted ? <>
                {asset && <SiteMap asset={asset} query={evidence.result.query.geometry} support={[]}/>}
                <EvidencePanel data={evidence}/>
              </> : <p>{evidence
                ? 'Evidence identity mismatch. Local results withheld.'
                : 'No reviewed local query for this cell. Use the regional evidence to scope a coverage search.'}</p>}
            </section>
          </>}
        </div>
      </div>}
  </main>
}
