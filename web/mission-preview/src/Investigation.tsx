import { useRef, useState } from 'react'
import type { Region, Profile } from './regions'
import { Badge, Metrics, rankingHref, regionHref, Tabs } from './ui'
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

export function Investigation({ region, shortlist, objective, terms, onPlan, profile }: {
  region: Region
  shortlist: Region[]
  objective: string
  terms: string[]
  profile: Profile
  onPlan: (profile: Profile, tasks?: boolean) => void
}) {
  const [tab, setTab] = useState<RegionTab>('Data')
  const [landmark, setLandmark] = useState(1)
  const [landmarkOpen, setLandmarkOpen] = useState(false)
  const sourcesDialog = useRef<HTMLDialogElement>(null)
  const jezero = region.id === '43'
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
      <h1>{region.name}</h1>
      <p className="mono muted">{region.id} · {region.type} · {region.coords}{jezero && ' · ⌀ 47.52 km'}</p>
      <div className="segmented map-mode" role="group" aria-label="Region map mode">
        <button type="button" aria-pressed="true">Map</button><button type="button" disabled>3D · N/A</button>
      </div>
      {!jezero && <p className="context-note">Planetary context · local imagery unavailable</p>}
    </div>

    <aside className="investigation-panel glass" aria-label="Region investigation panel">
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
            <PlanButtons onPlan={onPlan} />
            {jezero && <a className="button region-hazard-link" href={missionHref('monitor', profile, region, 'hazards')}>Hazard drill</a>}
          </div>
        </>}
        {tab !== 'Data' && <EvidenceBody {...{ tab, region, objective, terms, profile }} onPlan={profile => onPlan(profile, tab === 'Science')} onSources={() => sourcesDialog.current?.showModal()} />}
      </Tabs>
    </aside>

    <div className="investigation-footer">
      <nav className="site-shortlist glass" aria-label="Shortlist">
        <span className="caption">Shortlist</span>
        {shortlist.map(item => <a key={item.id} href={regionHref(item.id)}
          aria-current={item.id === region.id ? 'page' : undefined}>{item.name}</a>)}
        <a href={rankingHref} className="button">Compare</a>
      </nav>
      {jezero && <div className="map-scale mono" aria-label="Map scale 5 kilometres"><span />5 km</div>}
    </div>

    <dialog ref={sourcesDialog} className="dialog" aria-labelledby="sources-title">
      <h2 id="sources-title">Imagery sources</h2>
      <ul>{sources.slice(0, jezero ? 3 : 2).map(source => <li key={source.url}>
        <a href={source.url} target="_blank" rel="noreferrer">{source.label}</a>
      </li>)}</ul>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>
  </div>
}
