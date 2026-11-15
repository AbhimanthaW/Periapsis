import { useRef, useState } from 'react'
import type { Region, Profile } from './regions'
import { Badge, Metrics, rankingHref, Tabs } from './ui'
import { areaLabel, cellHref, distanceFromBase, formatPoint } from './cells'
import type { CellContext, CellSelection, MarsBase, RankedArea } from './cells'
import { DustOutlookSection } from './DustOutlook'
import { missionHref } from './mission'

import { EvidenceBody, PlanButtons, regionTabs } from './RegionEvidence'
import type { RegionTab } from './RegionEvidence'

const landmarks = [
  { name: 'Neretva Vallis', x: 278, y: 255, description: 'Valley approaching the western crater rim.' },
  { name: 'Delta front', x: 700, y: 270, description: 'Orbital view of the western delta deposits.' },
  { name: 'Mars 2020 landing site', x: 765, y: 388, description: 'Landing area of the Perseverance rover.' },
  { name: 'Crater floor', x: 930, y: 560, description: 'Crater-floor context east of the delta.' },
]

const sources = [
  { label: 'Viking MDIM 2.1 colour mosaic', url: 'https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m' },
  { label: 'Mars MGS MOLA shaded relief', url: 'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_global_color_shaded_relief_463m' },
  { label: 'Mars 2020 Jezero CTX orthomosaic', url: 'https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars' },
]

function DataTable({ jezero }: { jezero: boolean }) {
  const rows = [
    { name: 'Viking colour', res: '232 m', coverage: 'Full' },
    { name: 'MOLA relief', res: '463 m', coverage: 'Full' },
    { name: 'CTX optical', res: jezero ? '6 m' : '—', coverage: jezero ? 'Partial' : 'Not packaged' },
    { name: 'HiRISE', res: '—', coverage: 'Not packaged' },
    { name: 'Elevation model', res: '—', coverage: 'Not packaged' },
  ]
  return <div className="data-table-wrap"><table className="data-table">
    <colgroup><col /><col /><col /><col /><col /></colgroup>
    <thead><tr><th scope="col">Dataset</th><th scope="col">Res.</th><th scope="col">Coverage</th>
      <th scope="col">Quality</th><th scope="col"><span className="sr-only">Evidence type</span></th></tr></thead>
    <tbody>{rows.map(row => {
      const present = row.res !== '—'
      return <tr key={row.name}>
        <th scope="row">{row.name}</th><td className={`mono${present ? '' : ' muted'}`}>{row.res}</td>
        <td className={present ? row.coverage === 'Partial' ? 'caution' : '' : 'muted'}>
          {present ? row.coverage : <>Not <br />packaged</>}</td>
        <td className="muted">{present ? <>Not <br />evaluated</> : '—'}</td>
        <td><Badge>{present ? 'OBS' : 'N/A'}</Badge></td>
      </tr>
    })}</tbody>
  </table></div>
}

export function Investigation({ region, selection, cellContext, loading, error, retry, areas, match, objective, terms, onPlan, profile, base, walkHref }: {
  region?: Region
  selection?: CellSelection
  cellContext?: CellContext
  loading: boolean
  error: string
  retry: () => void
  areas: RankedArea[]
  match?: RankedArea
  objective: string
  terms: string[]
  profile: Profile
  base?: MarsBase
  walkHref?: string
  onPlan: (profile: Profile, tasks?: boolean) => void
}) {
  const [tab, setTab] = useState<RegionTab>('Data')
  const [landmark, setLandmark] = useState(1)
  const [landmarkOpen, setLandmarkOpen] = useState(false)
  const sourcesDialog = useRef<HTMLDialogElement>(null)
  const jezero = region?.id === '43'
  const title = region?.name ?? selection?.label ?? selection?.id ?? 'Cell investigation'
  const data = cellContext?.cell_context
  const startDistance = base && cellContext ? distanceFromBase(base.coordinates, cellContext.cell.centroid) : undefined
  return <div className="investigation">
    <div className={`terrain-viewport${jezero ? ' jezero-map' : ' context-map'}`}>
      {jezero ? <div className="terrain-image">
        <img src="./maps/jezero-ctx.webp" alt="CTX orbital mosaic of the western Jezero Crater and delta" />
        {landmarks.map((item, index) => <button key={item.name} type="button" className="terrain-marker"
          style={{ left: item.x / 14.4 + '%', top: item.y / 9 + '%' }}
          aria-pressed={landmark === index} aria-expanded={landmark === index && landmarkOpen} onClick={() => {
            setLandmarkOpen(landmark !== index || !landmarkOpen)
            setLandmark(index)
          }}>
          <span className="marker-dot" /><span>{item.name}</span>
        </button>)}
        {landmarkOpen && <div className="terrain-tooltip glass" role="status"
          style={{ left: landmarks[landmark].x / 14.4 + '%', top: landmarks[landmark].y / 9 + '%' }}>
          {landmarks[landmark].description}
        </div>}
      </div> : <img className="regional-context" src="./maps/mars-viking.webp" alt="Viking colour overview of Mars" />}
    </div>

    <div className="investigation-heading">
      <h1>{title}</h1>
      <p className="mono muted">{selection ? <>
        {selection.id}{cellContext && ' · ' + formatPoint(cellContext.cell.centroid)}{jezero && ' · CTX subset'}
      </> : region && <>{region.id} · {region.type} · {region.coords}{jezero && ' · ⌀ 47.52 km'}</>}</p>
      <div className="segmented map-mode" role="group" aria-label="Region map mode">
        <button type="button" aria-pressed="true" onClick={() => { setLandmark(1); setLandmarkOpen(false) }}>Map</button><button type="button" disabled>3D · N/A</button>
      </div>
      {!jezero && <p className="context-note">Planetary context · local imagery unavailable</p>}
    </div>

    <aside className="investigation-panel glass" aria-label="Region investigation panel" aria-busy={!!selection && loading}>
      {selection && error && <div className="investigation-message"><p role="alert">{error}</p>
        <button className="button compact" onClick={retry}>Retry cell evidence</button></div>}
      <Tabs items={regionTabs} value={tab} onChange={setTab} label="Investigation details">
        {tab === 'Data' && <>
          <DataTable jezero={jezero} />
          <div className="limits">
            <div className="section-heading">
              <span className="caption">Limits</span>
              <button type="button" className="button compact" aria-haspopup="dialog"
                onClick={() => sourcesDialog.current?.showModal()}>Sources</button>
            </div>
            <Metrics>
              <dt>Slope, roughness</dt><dd className="caution">Unavailable without elevation</dd>
              <dt>Routing support</dt><dd className="caution">{jezero ? 'Optical context only' : 'Planetary context only'}</dd>
              <dt>Survey uncertainty</dt><dd>{jezero ? 'Low in observed areas, higher elsewhere' : 'Local uncertainty unassessed'}</dd>
            </Metrics>
            {base && <div className="investigation-base">
              <Metrics>
                <dt>Mars base</dt><dd className="mono">{formatPoint(base.coordinates, 4)}</dd>
                {startDistance !== undefined && <><dt>To cell centre</dt><dd>~{Math.round(startDistance).toLocaleString('en-US')} km direct</dd></>}
              </Metrics>
              {walkHref && <a className="button primary" href={walkHref}>Open Marswalk from base</a>}
            </div>}
            {jezero && !base && <PlanButtons onPlan={onPlan} />}
            {!jezero && !base && <p className="routing-note muted">Set a Mars base on the globe to start a simulated Marswalk.</p>}
          </div>
        </>}
        {tab !== 'Data' && (region && !selection ?
          <EvidenceBody {...{ tab, region, objective, terms, profile }} onPlan={next => onPlan(next, tab === 'Science')} onSources={() => sourcesDialog.current?.showModal()} />
          : <div className="detail-copy">
            {tab === 'Science' && <>
              <h2>Science objective</h2><p>{objective}</p>
              {!!terms.length && <p className="muted">{terms.join(' · ')}</p>}
              <Metrics><dt>Science environment</dt><dd>{data?.science_environment.tier ?? 'Unavailable'}</dd>
                <dt>Match tier</dt><dd>{match?.tier ?? 'Not in the current ranking'}</dd></Metrics>
              {jezero && <>
                <DustOutlookSection regionId="43" />
                <div className="explore-actions">
                  <a className="button compact" href="#pack/43">Site pack readiness</a>
                  <a className="button compact" href="#evidence/43">Evidence panels</a>
                  {!base && <button className="button compact primary" onClick={() => onPlan(profile, true)}>Choose science task</button>}
                </div>
              </>}
            </>}
            {tab === 'Terrain' && <><h2>Orbital terrain context</h2>
              <Metrics>
                <dt>MOLA elevation</dt><dd>{data?.mola_elevation_m == null ? 'Unavailable' : data.mola_elevation_m.toLocaleString('en-US') + ' m'}</dd>
                <dt>MOLA observations</dt><dd>{data?.mola_observation_count?.toLocaleString('en-US') ?? '—'}</dd>
                <dt>Terrain tier</dt><dd>{data?.terrain.tier ?? 'Unavailable'}</dd>
              </Metrics><p className="muted">Regional measurements do not qualify local terrain for routing.</p>
            </>}
            {tab === 'Suitability' && <><h2>Local route suitability</h2>
              <p className="caution">Withheld until a qualified local terrain pack is available.</p>
              <Metrics><dt>Method screening</dt><dd>{match?.method ?? 'Not evaluated for this selection'}</dd>
                <dt>Live hazards</dt><dd>Unavailable</dd></Metrics>
              {walkHref && <a className="button" href={walkHref}>Open Marswalk from base</a>}
            </>}
          </div>)}
      </Tabs>
    </aside>

    <div className="investigation-footer">
      <nav className="site-shortlist glass" aria-label="Shortlist">
        <span className="caption">{areas.length > 0 ? 'Shortlist' : 'Map context'}</span>
        {areas.length > 0 ? areas.map(area => <a key={area.best_cell} href={cellHref(area.best_cell)}
          aria-current={area.best_cell === selection?.id ? 'page' : undefined}>{areaLabel(area)}</a>) : <span>{title}</span>}
        <a href={rankingHref} className="button">Compare</a>
      </nav>
      {jezero && <div className="map-scale mono" aria-label="Map scale 5 kilometres"><span />5 km</div>}
    </div>

    <dialog ref={sourcesDialog} className="dialog" aria-labelledby="sources-title">
      <h2 id="sources-title">Imagery sources</h2>
      <ul>{sources.slice(0, jezero ? 3 : 2).map(source => <li key={source.url}>
        <a href={source.url} target="_blank" rel="noreferrer">{source.label}</a>
      </li>)}</ul>
      {jezero && region && <a href={missionHref('monitor', profile, region, 'hazards')}
        onClick={() => sourcesDialog.current?.close()}>Jezero hazard drill</a>}
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>
  </div>
}
