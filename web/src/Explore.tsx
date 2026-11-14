import { useEffect, useRef, useState } from 'react'
import Map from 'ol/Map.js'
import View from 'ol/View.js'
import Projection from 'ol/proj/Projection.js'
import { addProjection } from 'ol/proj.js'
import TileLayer from 'ol/layer/Tile.js'
import VectorLayer from 'ol/layer/Vector.js'
import XYZ from 'ol/source/XYZ.js'
import VectorSource from 'ol/source/Vector.js'
import TileGrid from 'ol/tilegrid/TileGrid.js'
import Feature from 'ol/Feature.js'
import Point from 'ol/geom/Point.js'
import Style from 'ol/style/Style.js'
import CircleStyle from 'ol/style/Circle.js'
import Fill from 'ol/style/Fill.js'
import 'ol/ol.css'
import { atlasAsset, globalExtent } from './atlas/data'
import './explore.css'

type Concept = { state: string; support: number; relation: string; status: string; flags: string[] }
type Area = { rank: number; tile: number; cells: string[]; best_cell: string; tier: string;
  match_mean: number; match_best: number; concepts: Record<string, Concept>;
  records: Record<string, number>; method: string; sparse: boolean; label: string | null;
  point_features: Record<string, string[]>; demo: boolean }
type Answer = { request_id: string; pack: { version: string; sha256: string; synthetic_layers: unknown[] };
  parse: { concepts: { id: string }[]; demo: { id: string; included: boolean }[];
    unsupported: { id: string }[]; unknown: string[]; confidence: number };
  abstain: boolean; counts: { direct_cells: number; partial_cells: number; excluded: Record<string, number> };
  areas: Area[]; heat_nside32: string }

const projection = new Projection({ code: 'RETURN-WINDOW:MARS-PLANETOCENTRIC-EAST', units: 'degrees',
  extent: globalExtent, global: true, metersPerUnit: 3396190 * Math.PI / 180 })
addProjection(projection)
const grid = new TileGrid({ extent: globalExtent, origin: [-180, 90],
  resolutions: [360 / 512, 360 / 1024, 360 / 2048], tileSize: 256 })
const color = (value: number) => `rgba(255,${Math.round(193 - value * .42)},${Math.round(94 - value * .27)},${Math.min(.9, .25 + value / 330)})`
const styles = Array.from({ length: 16 }, (_, index) => new Style({ image: new CircleStyle({
  radius: 3.5, fill: new Fill({ color: color(index * 16) }),
}) }))

function HeatMap({ heat, selectTile }: { heat: string | null; selectTile: (tile: number) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const source = useRef(new VectorSource({ wrapX: true }))
  const map = useRef<Map | null>(null)
  useEffect(() => {
    if (!container.current) return
    const base = new TileLayer({ source: new XYZ({ projection, tileGrid: grid, wrapX: true,
      tileUrlFunction: coordinate => atlasAsset(`viking/${coordinate[0]}/${coordinate[1]}/${coordinate[2]}.webp`),
    }) })
    const layer = new VectorLayer({ source: source.current, style: feature => styles[Math.min(15, Math.floor(Number(feature.get('value')) / 16))] })
    const instance = new Map({ target: container.current, layers: [base, layer],
      view: new View({ projection, center: [0, 0], zoom: 1, minZoom: 0, maxZoom: 8,
        maxResolution: 360 / 256, multiWorld: true, extent: [-1800, -90, 1800, 90] }) })
    instance.on('singleclick', event => {
      const feature = instance.forEachFeatureAtPixel(event.pixel, value => value)
      if (feature) selectTile(Number(feature.get('tile')))
    })
    map.current = instance
    return () => { instance.setTarget(undefined); map.current = null }
  }, [selectTile])
  useEffect(() => {
    if (!heat) { source.current.clear(); return }
    let cancelled = false
    Promise.all([fetch(atlasAsset('cell-centres-nside32.bin')).then(response => response.arrayBuffer()),
      Promise.resolve(Uint8Array.from(atob(heat), character => character.charCodeAt(0)))])
      .then(([buffer, values]) => {
        if (cancelled) return
        const coordinates = new Float32Array(buffer)
        if (coordinates.length !== 24576 || values.length !== 12288) throw new Error('Heat layer has unexpected dimensions')
        const features: Feature<Point>[] = []
        for (let tile = 0; tile < values.length; tile++) {
          if (!values[tile]) continue
          const lon = coordinates[2 * tile] > 180 ? coordinates[2 * tile] - 360 : coordinates[2 * tile]
          const feature = new Feature(new Point([lon, coordinates[2 * tile + 1]]))
          feature.setProperties({ tile, value: values[tile] })
          features.push(feature)
        }
        source.current.clear()
        source.current.addFeatures(features)
      })
    return () => { cancelled = true }
  }, [heat])
  return <div className="explore-map" ref={container} aria-label="Mars cell match heat map" />
}

export default function Explore() {
  const [objective, setObjective] = useState('ancient water and delta deposits')
  const [method, setMethod] = useState('')
  const [polar, setPolar] = useState(false)
  const [volcanic, setVolcanic] = useState(false)
  const [includeDemo, setIncludeDemo] = useState(false)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [selected, setSelected] = useState<Area | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const rank = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true); setError(''); setDetail(null); setSelected(null)
    try {
      const response = await fetch('/api/v1/rank', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema_version: 1, request_id: crypto.randomUUID(), objective,
          method: method || null, exclude: [polar ? 'polar' : null, volcanic ? 'volcanic' : null].filter(Boolean),
          limit: 50, include_demo: includeDemo }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.message ?? `HTTP ${response.status}`)
      setAnswer(data as Answer)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Ranking failed') }
    finally { setBusy(false) }
  }
  const selectArea = async (area: Area) => {
    setSelected(area); setDetail(null)
    try {
      const response = await fetch(`/api/v1/cell/${area.best_cell}`)
      if (response.ok) setDetail(await response.json())
    } catch { /* The area result remains usable without detail. */ }
  }
  const selectTile = (tile: number) => {
    const area = answer?.areas.find(item => item.tile === tile)
    if (area) void selectArea(area)
  }
  return <main className="explore">
    <header><a href="/">← Architecture</a><h1>Explore Mars cells</h1><p>Objective match, records and method compatibility are separate criteria. Cells with missing survey coverage remain unknown.</p></header>
    <form onSubmit={rank}>
      <label>Science objective<input value={objective} maxLength={300} onChange={event => setObjective(event.target.value)} required /></label>
      <label>Method<select value={method} onChange={event => setMethod(event.target.value)}><option value="">Any method</option><option value="sample-rock">Sample rock</option><option value="investigate-ice">Investigate ice</option><option value="remote-survey">Remote survey</option></select></label>
      <label className="check"><input type="checkbox" checked={polar} onChange={event => setPolar(event.target.checked)} />Exclude polar</label>
      <label className="check"><input type="checkbox" checked={volcanic} onChange={event => setVolcanic(event.target.checked)} />Exclude volcanic</label>
      <label className="check"><input type="checkbox" checked={includeDemo} onChange={event => setIncludeDemo(event.target.checked)} />Include DEMO data</label>
      <button disabled={busy}>{busy ? 'Ranking…' : 'Rank cells'}</button>
    </form>
    {error && <p role="alert" className="explore-error">{error}</p>}
    {answer && <>
      <section className="explore-parse"><h2>Objective parse</h2><p>Understood: {answer.parse.concepts.map(x => x.id).join(', ') || 'none'}.
        {answer.parse.demo.length > 0 && <> DEMO: {answer.parse.demo.map(x => `${x.id}${x.included ? ' included' : ' excluded'}`).join(', ')}.</>}
        {answer.parse.unsupported.length > 0 && <> No cell data yet: {answer.parse.unsupported.map(x => x.id).join(', ')}.</>}
        {answer.parse.unknown.length > 0 && <> Not understood: {answer.parse.unknown.join(', ')}.</>}</p>
        <p>{answer.abstain ? 'No supported concept; no ranking.' : `${answer.counts.direct_cells.toLocaleString()} Direct cells; ${answer.counts.partial_cells.toLocaleString()} Partial cells.`}</p></section>
      <div className="explore-layout"><HeatMap heat={answer.heat_nside32} selectTile={selectTile} />
        <div className="explore-results"><h2>Ranked areas</h2><p>Heat marks Nside-32 tile centres. Select a row for cell evidence.</p>
          <table><thead><tr><th>Rank</th><th>Area</th><th>Match</th><th>Records</th><th>Method</th></tr></thead><tbody>
            {answer.areas.map(area => <tr key={`${area.tile}:${area.best_cell}`} onClick={() => void selectArea(area)} aria-selected={selected === area}>
              <td>{area.rank}</td><td>{area.label ?? area.best_cell}{area.demo ? ' · DEMO' : ''}<small>{area.tier} · {area.cells.length} cells{area.sparse ? ' · sparse' : ''}</small></td>
              <td>{area.match_mean.toLocaleString()}</td><td>{Object.entries(area.records).map(([key, value]) => `${key} ${value}`).join(' · ')}</td><td>{area.method}</td>
            </tr>)}</tbody></table>
          {selected && <section className="explore-detail"><h3>{selected.best_cell}</h3>
            {Object.entries(selected.concepts).map(([name, value]) => <p key={name}>{name}: {value.state}, support {value.support.toFixed(2)} ({value.relation}){value.status === 'DEMO' ? ' · DEMO' : ''}{value.flags.length ? ` · ${value.flags.join('; ')}` : ''}</p>)}
            {detail && <details><summary>Full cell record</summary><pre>{JSON.stringify(detail, null, 2)}</pre></details>}</section>}
        </div></div>
      <p className="explore-version">Pack {answer.pack.version} · {answer.pack.sha256.slice(0, 12)} · {answer.pack.synthetic_layers.length ? 'contains optional DEMO layers' : 'source data only'}</p>
    </>}
  </main>
}
