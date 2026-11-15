import { useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ArrowBendDownLeft, Crosshair, Minus, Plus, Stack } from '@phosphor-icons/react'
import { allRegions, exclusions, methods, profiles } from './regions'
import { CELL_COUNT, JEZERO_ANCHOR, areaLabel, cellHref, formatPoint } from './cells'
import type { CellContext, CellSelection, MarsBase, RankedArea } from './cells'
import { BaseLocation } from './BaseLocation'
import type { Exclusion, Method, Profile, Region } from './regions'
import { Badge, IconButton, Metrics, rankingHref, Segmented } from './ui'
import { MethodReview } from './objective-methods/MethodReview'
import { arcadiaScenario } from './objective-methods/arcadia'
import type { GoalId } from './objective-methods/catalog'
import type { AdvisoryProposal } from './objective-methods/recommend'

interface GlobeProps {
  selected?: CellSelection
  targetsEdited: boolean
  context?: CellContext
  shortlist: RankedArea[]
  selectionError: string
  locating: boolean
  base?: MarsBase
  setBase: (base?: MarsBase) => void
  rank: () => void
  retrySelection: () => void
  selectIndicator: (indicator: Region) => void
  select: (cell: CellSelection) => void
  objective: string
  terms: string[]
  method: Method
  excludes: Exclusion[]
  layer: 'viking' | 'mola'
  zoom: number
  setLayer: (layer: 'viking' | 'mola') => void
  setZoom: (zoom: number) => void
  setMethod: (method: Method) => void
  setTerms: (terms: string[]) => void
  applyObjective: (objective: string) => void
  toggleFilter: (filter: Exclusion) => void
  proposal: AdvisoryProposal
  reviewRegionName: string
  arcadiaLoaded: boolean
  arcadiaVisited: boolean
  loadArcadia: () => void
  restoreArcadia: () => void
  useSelectedRegion: () => void
  onConfirmGoals: (goals: readonly GoalId[]) => void
  onProfile: (profile: Profile) => void
  reviewHref: string
}

function ObjectiveControls({
  objective, terms, targetsEdited, method, excludes, setMethod, setTerms, applyObjective, toggleFilter, base, setBase, rank,
  proposal, reviewRegionName, arcadiaLoaded, arcadiaVisited, loadArcadia, restoreArcadia,
  useSelectedRegion, onConfirmGoals, onProfile, reviewHref,
}: GlobeProps) {
  const editor = useRef<HTMLDialogElement>(null)
  const review = useRef<HTMLDialogElement>(null)
  const [draft, setDraft] = useState(objective)
  const [targetDraft, setTargetDraft] = useState('')
  const [reviewSession, setReviewSession] = useState(0)
  function apply(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim()) return
    setDraft(draft.trim())
    applyObjective(draft.trim())
  }
  function saveTargets(event: FormEvent) {
    event.preventDefault()
    setTerms([...new Set(targetDraft.split(/[\n,]/).map(term => term.trim()).filter(Boolean))])
    editor.current?.close()
  }
  return <section className="objective-panel glass" aria-label="Science objective and filters">
    <form className="objective-input" onSubmit={apply}>
      <label className="caption" htmlFor="objective">Objective</label>
      <input id="objective" required value={draft} onChange={event => setDraft(event.target.value)}
        maxLength={160} spellCheck={false} />
      <IconButton aria-label="Apply objective" title="Apply objective" type="submit"><ArrowBendDownLeft size={11} /></IconButton>
    </form>
    <div className="objective-options">
      <div className="objective-row">
        <span className="caption">{targetsEdited ? 'Targets' : 'Read as'}</span>
        <div className="chips interpreted" aria-live="polite">
          {terms.map(term => <span key={term} className="chip active">{term}</span>)}
          <button className="chip" type="button" aria-haspopup="dialog" onClick={() => {
            setTargetDraft(terms.join('\n'))
            editor.current?.showModal()
          }}>Edit targets</button>
          {!targetsEdited && <Badge>EST</Badge>}
        </div>
      </div>
      <div className="objective-row preferences">
        <span className="caption" id="method-label">Method</span>
        <div className="chips" role="group" aria-labelledby="method-label">
          {methods.map(item => <button key={item} type="button" className="chip" aria-pressed={item === method}
            onClick={() => setMethod(item)}>{item}</button>)}
        </div>
        <div className="chips exclusions" role="group" aria-labelledby="excluding-label">
          <span className="caption" id="excluding-label">Exclude</span>
          {exclusions.map(item => <button key={item} type="button" className="chip filter"
            aria-pressed={excludes.includes(item)} onClick={() => toggleFilter(item)}>{item}</button>)}
        </div>
      </div>
      <div className="explore-actions">
        <a className="button compact" href={rankingHref} onClick={rank}>Ranked areas</a>
        <BaseLocation base={base} onChange={setBase} />
        <button type="button" className="button compact review-methods-trigger" aria-haspopup="dialog"
          onClick={() => { setReviewSession(current => current + 1); review.current?.showModal() }}>Review methods</button>
      </div>
    </div>
    <dialog ref={editor} className="dialog" aria-labelledby="targets-title">
      <form onSubmit={saveTargets}>
        <h2 id="targets-title">Edit targets</h2>
        <p>Ranking uses these terms in place of the objective text. Clear the list to use the objective again.</p>
        <label htmlFor="target-terms">Target terms, one per line</label>
        <textarea id="target-terms" value={targetDraft} rows={5} maxLength={300}
          onChange={event => setTargetDraft(event.target.value)} />
        <div className="dialog-actions">
          <button className="button" type="button" onClick={() => editor.current?.close()}>Cancel</button>
          <button className="button primary" type="submit">Apply targets</button>
        </div>
      </form>
    </dialog>
    <dialog ref={review} className="dialog method-dialog" aria-labelledby="review-methods-title">
      <div className="section-heading">
        <h2 id="review-methods-title">Review methods</h2>
        <form method="dialog"><button className="button compact">Close</button></form>
      </div>
      <p>{reviewRegionName} · {objective}</p>
      <div className="method-actions">
        <button type="button" className="button" onClick={arcadiaLoaded ? useSelectedRegion : () => {
          loadArcadia()
          setDraft(arcadiaScenario.objective)
        }}>{arcadiaLoaded ? 'Use selected region' : 'Load Arcadia scenario'}</button>
        {!arcadiaLoaded && arcadiaVisited && <button type="button" className="button"
          onClick={restoreArcadia}>Use Arcadia footprint</button>}
        {arcadiaLoaded && <Segmented items={profiles} value={proposal.context.profile}
          onChange={onProfile} label="Advisory profile" />}
        {arcadiaLoaded && <a className="button primary" href={reviewHref}
          onClick={() => review.current?.close()}>Open Science Tasks</a>}
      </div>
      <MethodReview key={reviewSession + ':' + objective} proposal={proposal} onConfirmGoals={onConfirmGoals} />
    </dialog>
  </section>
}

function RegionSummary({ selected, context, locating, selectionError, retrySelection, rank }: GlobeProps) {
  const cell = context?.cell
  const evidence = context?.cell_context
  const jezero = selected?.id === JEZERO_ANCHOR
  return <aside className="region-summary glass" aria-label="Selected cell" aria-busy={locating}>
    <div className="summary-heading">
      <h1>{selected?.label ?? selected?.id ?? 'Explore Mars'}</h1>
    </div>
    {selected && <div className="region-coords">{selected.label && <span className="mono">{selected.id}</span>}
      {cell && <span className="mono muted">{formatPoint(cell.centroid)}</span>}<Badge>GRID</Badge></div>}
    {locating && <p role="status" className="muted">Locating the Mars cell…</p>}
    {selectionError && <div className="selection-error"><p role="alert">{selectionError}</p>
      <button className="button compact" onClick={retrySelection}>Retry</button></div>}
    {!selected ? <>
      <p className="muted selection-empty">Choose a landmark on the globe or search for areas with a science objective.</p>
      <section className="summary-section data-summary">
        <div className="section-heading"><span className="caption">Search grid</span><Badge>GRID</Badge></div>
        <Metrics><dt>HEALPix cells</dt><dd className="mono">{CELL_COUNT.toLocaleString('en-US')}</dd><dt>Resolution</dt><dd className="mono">Nside 128</dd></Metrics>
      </section>
    </> : <>
      <section className="summary-section cell-evidence-summary">
        <div className="section-heading"><span className="caption">Cell evidence</span><Badge>{evidence ? 'OBS' : 'N/A'}</Badge></div>
        <Metrics>
          <dt>Science</dt><dd>{evidence?.science_environment.tier ?? 'Unavailable'}</dd>
          <dt>Terrain</dt><dd>{evidence?.terrain.tier ?? 'Unavailable'}</dd>
          <dt>Elevation</dt><dd className="mono">{evidence?.mola_elevation_m == null ? '—' : evidence.mola_elevation_m.toLocaleString('en-US') + ' m'}</dd>
          <dt>MOLA points</dt><dd className="mono">{evidence?.mola_observation_count?.toLocaleString('en-US') ?? '—'}</dd>
          <dt>Cell area</dt><dd className="mono">{cell ? cell.area_km2.toFixed(1) + ' km²' : '—'}</dd>
        </Metrics>
      </section>
      <section className="summary-section data-summary">
        <div className="section-heading"><span className="caption">Data</span><Badge>OBS</Badge></div>
        <Metrics>
          <dt>Viking colour</dt><dd className="mono">232 m</dd>
          <dt>MOLA relief</dt><dd className="mono">463 m</dd>
          <dt>CTX optical</dt><dd className="mono">{jezero ? '6 m · subset' : '—'}</dd>
          <dt>Local routing</dt><dd className="caution">Withheld</dd>
        </Metrics>
      </section>
      <div className="summary-actions">
        <a className="button primary" href={cellHref(selected.id)}>Investigate</a>
        <a className="button" href={rankingHref} onClick={rank}>Compare</a>
      </div>
    </>}
  </aside>
}

export function Globe(props: GlobeProps) {
  const { selected, shortlist, select, selectIndicator, layer, setLayer, zoom, setZoom } = props
  const [layerMenu, setLayerMenu] = useState(false)
  const layerButton = useRef<HTMLButtonElement>(null)
  function changeZoom(change: number) {
    setZoom(Math.max(.7, Math.min(1.6, Math.round((zoom + change) * 10) / 10)))
  }
  function globeKeys(event: KeyboardEvent) {
    if (!['+', '=', '-', '0'].includes(event.key)) return
    event.preventDefault()
    if (event.key === '0') setZoom(1)
    else changeZoom(event.key === '-' ? -.1 : .1)
  }
  return <div className="explore">
    <div className="globe-viewport" role="group" aria-label="Mars globe and regions" onKeyDown={globeKeys}>
      <div className="globe-disc" style={{ '--zoom': zoom } as React.CSSProperties}>
        <img src={`./maps/mars-${layer}.webp`} alt="" draggable={false} />
        {allRegions.map(region => {
          const active = selected?.markerId === region.id
          return <button key={region.id} type="button" className={`globe-marker${region.id === '46' ? ' label-left' : ''}`}
            style={{ left: region.position[0] / 7.74 + '%', top: region.position[1] / 7.74 + '%' }}
            aria-label={region.name} title={region.name + ' · map landmark'}
            aria-pressed={active} onClick={() => selectIndicator(region)}>
            <span className="marker-dot" />
            <span className="marker-label">{region.name}</span>
          </button>
        })}
      </div>
    </div>
    <RegionSummary {...props} />
    <div className="explore-center">
      {shortlist.length > 0
        ? <section className="shortlist glass" aria-label="Top ranked cells">
          {shortlist.map(area => <button key={area.best_cell} type="button"
            aria-pressed={selected?.id === area.best_cell} onClick={() => select({ id: area.best_cell, label: area.label ?? undefined })}>
            <span className="shortlist-name"><span>{area.rank}</span>{areaLabel(area)}</span>
            <span className="shortlist-coords">{area.label ? area.best_cell : 'HEALPix Nside 128'}</span>
            <span className="shortlist-match mono">{area.tier} match{area.sparse ? ' · sparse' : ''}</span>
          </button>)}
        </section>
        : <section className="shortlist glass" aria-label="Map landmarks">
          {allRegions.slice(0, 3).map(region => <button key={region.id} type="button"
            aria-pressed={selected?.markerId === region.id} onClick={() => selectIndicator(region)}>
            <span className="shortlist-name">{region.name}</span>
            <span className="shortlist-coords">{region.type} · {region.coords}</span>
            <span className="shortlist-match mono">Map landmark</span>
          </button>)}
        </section>}
      <ObjectiveControls {...props} />
    </div>
    <div className="layer-control" onKeyDown={event => {
      if (event.key === 'Escape' && layerMenu) {
        setLayerMenu(false)
        layerButton.current?.focus()
      }
    }}>
      <button type="button" className="glass layer-trigger" ref={layerButton} aria-expanded={layerMenu}
        aria-controls="map-layers" onClick={() => setLayerMenu(value => !value)}>
        <span>{layer === 'viking' ? 'Viking colour' : 'MOLA relief'}</span>
        <span className="mono muted">{layer === 'viking' ? '232 m' : '463 m'}</span><Badge>OBS</Badge>
        <Stack size={17} weight="bold" />
      </button>
      {layerMenu && <div id="map-layers" className="glass layer-choices" role="group" aria-label="Map layers">
        <button aria-pressed={layer === 'viking'} onClick={() => { setLayer('viking'); setLayerMenu(false); layerButton.current?.focus() }}>Viking colour</button>
        <button aria-pressed={layer === 'mola'} onClick={() => { setLayer('mola'); setLayerMenu(false); layerButton.current?.focus() }}>MOLA relief</button>
      </div>}
    </div>
    <div className="zoom-control glass" role="group" aria-label="Globe zoom">
      <IconButton aria-label="Zoom in" title="Zoom in" disabled={zoom >= 1.6} onClick={() => changeZoom(.1)}><Plus size={17} weight="bold" /></IconButton>
      <IconButton aria-label="Zoom out" title="Zoom out" disabled={zoom <= .7} onClick={() => changeZoom(-.1)}><Minus size={17} weight="bold" /></IconButton>
      <IconButton aria-label="Reset globe view" title="Reset globe view" onClick={() => setZoom(1)}><Crosshair size={17} weight="bold" /></IconButton>
    </div>
  </div>
}
