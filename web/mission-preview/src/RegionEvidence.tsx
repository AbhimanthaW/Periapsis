import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Region, Profile } from './regions'
import { Badge, Metrics, Tabs, regionHref } from './ui'

export const regionTabs = ['Science', 'Data', 'Terrain', 'Suitability'] as const
export type RegionTab = (typeof regionTabs)[number]

export function Readouts({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return <Metrics>{rows.map(([label, value], i) => <div className="metric-pair" key={i}><dt>{label}</dt><dd>{value}</dd></div>)}</Metrics>
}
export const Warn = ({ children }: { children: ReactNode }) => <span className="caution">{children}</span>
export function Section({ title, status, children }: { title: string; status?: ReactNode; children: ReactNode }) {
  return <section className="mission-section"><div className="section-heading"><span className="caption">{title}</span>{status}</div>{children}</section>
}
export function PlanButtons({ onPlan }: { onPlan: (profile: Profile) => void }) {
  return <div className="simulation-actions">{(['Rover', 'Astronaut'] as const).map(profile =>
    <button key={profile} className={'button' + (profile === 'Rover' ? ' primary' : '')} onClick={() => onPlan(profile)}>{profile} · simulated terrain</button>)}</div>
}

export function EvidenceBody({ tab, region, objective, terms, standalone, onPlan, onSources, profile = 'Rover' }: {
  tab: RegionTab; region: Region; objective: string; terms: string[]; standalone?: boolean
  onPlan: (profile: Profile) => void; onSources: () => void; profile?: Profile
}) {
  const jez = region.id === '43'
  if (tab === 'Science') return <div className="evidence-body">
    <Section title="Scientific interest" status={<Badge>EST</Badge>}>
      <p className="science-lead">{jez ? 'Very high for ancient habitability, sedimentology and planetary geology' : region.scienceSummary}</p>
      <Readouts rows={[
        ['Opportunity', jez ? 'Ancient habitability, water-related geological history' : region.scienceSummary],
        ['Matches objective', <span className="mono accent">“{region.phrase}”</span>],
        ['Method fit', region.preferred + ' · supported by survey'],
      ]}/>
      {!standalone && <p className="muted">{objective}{terms.length > 0 && ' · ' + terms.join(', ')}</p>}
    </Section>
    <Section title="Missions here" status={<Badge>OBS</Badge>}>
      <Readouts rows={[[jez ? 'Mars 2020 Perseverance' : 'Mission record', <span className="mono">{jez ? 'landed 18 Feb 2021' : 'Unavailable'}</span>], ['Salvage target', <span className="muted">{jez ? 'No · vehicle in operation' : 'Unassessed'}</span>]]}/>
    </Section>
    <Section title="Evidence" status={<button className="button compact" onClick={onSources}>{jez ? '19 sources' : 'Sources'}</button>}>
      <Readouts rows={[[ 'Claims checked', <Warn>Not validated per source</Warn> ]]}/>
    </Section>
    {!standalone && <div className="mission-actions"><a className="button" href={'#pack/' + region.id}>Site pack readiness</a><a className="button" href={'#evidence/'+region.id}>Evidence panels</a><button className="button primary" onClick={() => onPlan(profile)}>Choose science task</button></div>}
  </div>
  if (tab === 'Terrain') return <div className="evidence-body">
    <Section title="Measured" status={<Badge>N/A</Badge>}><Readouts rows={[
      ['Elevation', <Warn>No elevation model in pack</Warn>], ['Slope', <span className="muted">Needs elevation</span>], ['Roughness', <span className="muted">Needs elevation at supported scale</span>],
    ]}/></Section>
    <Section title="Survey description" status={<Badge>EST</Badge>}><Readouts rows={[
      ['Surfaces', jez ? 'Crater-floor bedrock, ancient river delta' : 'Unassessed'], ['Obstacles', jez ? 'Rocks, sand, steep scarps, sustained climbing' : 'Unassessed'], ['Size', <span className="mono">{jez ? '⌀ 47.52 km' : '—'}</span>],
    ]}/></Section>
    <div className="section-heading mission-section muted">Routing here runs on simulated terrain <Badge>SIM</Badge></div>
  </div>
  return <div className="evidence-body">
    {tab === 'Data' ? <Section title="Pack evidence" status={<Badge>OBS</Badge>}><Readouts rows={[[ 'Optical', jez ? 'CTX subset' : 'Planetary context' ], ['Elevation model', <Warn>Not packaged</Warn>]]}/></Section> : <>
      <Section title="Rover" status={<Badge>EST</Badge>}><Readouts rows={[[ 'Traversal', jez ? 'Low to moderate on favourable floor' : 'Unassessed' ], ['At obstacles', <Warn>High to very high</Warn>], ['Level', <span className="muted">None assigned by survey</span>]]}/></Section>
      <Section title="Astronaut" status={<Badge>N/A</Badge>}><Readouts rows={[[ 'Traversal', <Warn>Not evaluated · survey covers rovers only</Warn> ]]}/></Section>
      <Section title="Reachable targets" status={<Badge>OBS</Badge>}><Readouts rows={jez ? [['Delta front', <span className="mono">in CTX subset</span>], ['Neretva Vallis', <span className="mono">in CTX subset</span>], ['Crater rim, east', <span className="mono caution">outside subset</span>]] : [['Local targets', 'Not packaged']]}/></Section>
    </>}
    <PlanButtons onPlan={onPlan}/>
    {!standalone && <a className="button compact" href={'#pack/' + region.id}>Site pack readiness</a>}
  </div>
}

function EvidenceCard(props: Omit<Parameters<typeof EvidenceBody>[0], 'tab'> & { initial: RegionTab }) {
  const [tab, setTab] = useState(props.initial)
  return <article className="glass evidence-card"><Tabs items={regionTabs} value={tab} onChange={setTab} label={props.initial + ' evidence panel'}>
    <EvidenceBody {...props} tab={tab} />
  </Tabs></article>
}
export function EvidenceGallery(props: Omit<Parameters<typeof EvidenceBody>[0], 'tab' | 'standalone'>) {
  return <div className="evidence-gallery">{(['Science','Terrain','Suitability'] as const).map(initial => <EvidenceCard key={initial} {...props} initial={initial} standalone />)}
    <a className="review-back" href={regionHref(props.region.id)}>Back to region</a>
  </div>
}
const gates = [
  ['Source integrity','Acquisition','Map · Route'], ['Metadata and coordinates','Spatial reference','Map · Route'],
  ['Geographic coverage','Acquisition','Map · Route'], ['Terrain resolution and support','Terrain preparation','Route'],
  ['Cross-layer alignment','Integration','Route'], ['Observation provenance','Evidence review','Science tasks'],
  ['Regional readiness','Capability review','Route · Tasks'], ['Output schema','Release validation','All'],
  ['Package integrity','Release validation','All'], ['Runtime compatibility','Smoke check','All'],
]
export function SitePack({ region, onPlan }: { region: Region; onPlan: () => void }) {
  return <div className="pack-grid paper-screen">
    <section><div className="section-heading pack-title"><h1>Release gates</h1><span className="mono muted">0 passed · 0 failed · 10 not evaluated</span></div>
      <div className="table-scroll"><table className="mission-table"><thead><tr>{['Gate','Check','Stage','Needed for','Result'].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{gates.map(([name,stage,needed],i) => <tr key={name}><td className="mono">G{i+1}</td><th scope="row">{name}</th><td className="muted">{stage}</td><td className="muted">{needed}</td><td className={i === 3 || i === 6 ? 'caution' : 'muted'}>{i === 3 ? 'Blocked · no elevation model' : i === 6 ? 'Waits on G2 to G5' : 'Not evaluated'}</td></tr>)}</tbody>
      </table></div>
    </section>
    <aside>
      <Section title="Pack"><Readouts rows={[[ 'Region', region.id+' · '+region.name ], ['Pack',<Warn>None published</Warn>],['Frame','Mars planetocentric, east-positive']]}/></Section>
      <Section title="Capabilities"><Readouts rows={[[ 'Atlas and regional map',<span className="good">Available · display only</span> ],['Route on real terrain',<span className="bad">Withheld</span>],['Route on simulated terrain',<Warn>Allowed · labelled SIM</Warn>],['Science tasks',<span className="bad">Withheld · no reviewed stations</span>]]}/></Section>
      <Section title="Files expected in a pack"><Readouts rows={['site.json','terrain.npz','stations.json'].map<[ReactNode, ReactNode]>(name => [<span className="mono">{name}</span>,<span className="muted">missing</span>]).concat([[<span>Display imagery</span>, <span>{region.id==='43'?'CTX subset':'Planetary context'} · <Badge>OBS</Badge></span>]])}/></Section>
      <div className="mission-actions fill"><a className="button" href={regionHref(region.id)}>Back to region</a><button className="button primary" onClick={onPlan}>Plan on SIM terrain</button></div>
    </aside>
  </div>
}
