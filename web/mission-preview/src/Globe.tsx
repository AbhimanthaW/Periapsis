import { useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ArrowBendDownLeft, Crosshair, Minus, Plus, Stack } from '@phosphor-icons/react'
import { allRegions, exclusions, isExcluded, methods } from './regions'
import type { Exclusion, Method, Profile, Region } from './regions'
import { Badge, IconButton, Metrics, rankingHref, regionHref } from './ui'
import { missionHref } from './mission'

interface GlobeProps {
  selected: Region
  profile: Profile
  shortlist: Region[]
  objective: string
  terms: string[]
  method: Method
  excludes: Exclusion[]
  layer: 'viking' | 'mola'
  zoom: number
  select: (id: string) => void
  setLayer: (layer: 'viking' | 'mola') => void
  setZoom: (zoom: number) => void
  setMethod: (method: Method) => void
  setTerms: (terms: string[]) => void
  applyObjective: (objective: string) => void
  toggleFilter: (filter: Exclusion) => void
}

function ObjectiveControls({ objective, terms, method, excludes, setMethod, setTerms, applyObjective, toggleFilter }: GlobeProps) {
  const editor = useRef<HTMLDialogElement>(null)
  const [draft, setDraft] = useState(objective)
  const [targetDraft, setTargetDraft] = useState('')
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
        <span className="caption">Read as</span>
        <div className="chips interpreted" aria-live="polite">
          {terms.map(term => <span key={term} className="chip active">{term}</span>)}
          <button className="chip" type="button" aria-haspopup="dialog" onClick={() => {
            setTargetDraft(terms.join('\n'))
            editor.current?.showModal()
          }}>Edit targets</button>
          <Badge>EST</Badge>
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
      <a className="button compact" href={rankingHref} title="Open the local sample ranking">All 56 ranked</a>
    </div>
    <dialog ref={editor} className="dialog" aria-labelledby="targets-title">
      <form onSubmit={saveTargets}>
        <h2 id="targets-title">Edit targets</h2>
        <label htmlFor="target-terms">Target terms, one per line</label>
        <textarea id="target-terms" value={targetDraft} rows={5} maxLength={500}
          onChange={event => setTargetDraft(event.target.value)} />
        <div className="dialog-actions">
          <button className="button" type="button" onClick={() => editor.current?.close()}>Cancel</button>
          <button className="button primary" type="submit">Apply targets</button>
        </div>
      </form>
    </dialog>
  </section>
}

function RegionSummary({ region, profile }: { region: Region; profile: Profile }) {
  const jezero = region.id === '43'
  return <aside className="region-summary glass" aria-label="Selected region">
    <div className="summary-heading">
      <h1>{region.name}</h1>
      <span className="mono muted">{region.id}</span>
    </div>
    <div className="region-coords"><span className="muted">{region.type}</span>
      <span className="mono">{region.coords}</span><Badge>OBS</Badge></div>
    <section className="summary-section">
      <div className="section-heading"><span className="caption">Survey</span><Badge>EST</Badge></div>
      <Metrics>
        <dt>Science</dt><dd>{region.scienceSummary}</dd>
        <dt>Records</dt><dd>{typeof region.records === 'number' ? region.records === 5 ? 'Very high' : 'High' : region.records}</dd>
        <dt>Traversal</dt><dd>{region.traversalSummary}</dd>
      </Metrics>
    </section>
    <section className="summary-section data-summary">
      <div className="section-heading"><span className="caption">Data</span><Badge>OBS</Badge></div>
      <Metrics>
        <dt>Viking colour</dt><dd className="mono">232 m</dd>
        <dt>MOLA relief</dt><dd className="mono">463 m</dd>
        <dt>CTX optical</dt><dd className="mono">{jezero ? '6 m · subset' : '—'}</dd>
        <dt>Terrain model</dt><dd className="caution">none</dd>
      </Metrics>
    </section>
    <div className="summary-actions">
      <a className="button primary" href={regionHref(region.id)}>Investigate</a>
      <a className="button" href={rankingHref}>Compare</a>
      {jezero && <a className="button region-hazard-link" href={missionHref('monitor', profile, region, 'hazards')}>Hazard drill</a>}
    </div>
  </aside>
}

export function Globe(props: GlobeProps) {
  const { selected, shortlist, excludes, select, layer, setLayer, zoom, setZoom } = props
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
          const rank = shortlist.findIndex(item => item.id === region.id) + 1
          const active = selected.id === region.id
          const excluded = isExcluded(region, excludes)
          return <button key={region.id} type="button" className={`globe-marker${rank ? ' ranked' : ''}${region.id === '46' ? ' label-left' : ''}`}
            style={{ left: region.position[0] / 7.74 + '%', top: region.position[1] / 7.74 + '%' }}
            disabled={excluded} aria-label={region.name + (excluded ? ' · Excluded' : '')}
            aria-pressed={active} onClick={() => select(region.id)}>
            <span className="marker-dot" />
            <span className="marker-label">{rank > 0 && <span>{rank}</span>}{region.name}</span>
          </button>
        })}
      </div>
    </div>
    <RegionSummary region={selected} profile={props.profile} />
    <div className="explore-center">
      <section className="shortlist glass" aria-label="Top matching regions">
        {shortlist.map((region, index) => <button key={region.id} type="button"
          aria-pressed={selected.id === region.id} onClick={() => select(region.id)}>
          <span className="shortlist-name"><span>{index + 1}</span>{region.name}</span>
          <span className="shortlist-coords">{region.type} · {region.coords}</span>
          <span className="shortlist-match mono">“{region.phrase}”</span>
        </button>)}
      </section>
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
