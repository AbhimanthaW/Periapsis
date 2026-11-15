import { useEffect, useRef, useState } from 'react'
import { List, SquaresFour, Sun, Terminal } from '@phosphor-icons/react'
import { Globe } from './Globe'
import { EvidenceGallery, SitePack } from './RegionEvidence'
import { initialMission, missionHref } from './mission'
import { Planning } from './Planning'
import { Analysis } from './Analysis'
import { Monitoring } from './Monitoring'
import { HazardMission } from './hazards/HazardMission'
import { useHazardReplay } from './hazards/replay'
import { Ranking } from './Ranking'
import { Investigation } from './Investigation'
import {
  allRegions, defaultObjective, initialTerms, interpretObjective, isExcluded, profiles, rankRegions,
} from './regions'
import type { Exclusion, Method, Profile, Sort } from './regions'
import { globeHref, IconButton, rankingHref, regionHref, Segmented } from './ui'

function useScreen() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    function update() { setHash(window.location.hash) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const [stage, mode, id, view = ''] = hash.slice(1).split('/')
  const missionStage = stage === 'route' || stage === 'analysis' || stage === 'monitor'
  const region = allRegions.find(item => item.id === (missionStage ? id : mode))
  const screen = missionStage ? stage : region && stage === 'pack' ? 'pack'
    : region && stage === 'evidence' ? 'evidence' : region && stage === 'region' ? 'investigation'
    : hash === rankingHref ? 'ranking' : 'globe'
  return { region, screen, view, missionStage, routeProfile: mode === 'astronaut' ? 'Astronaut' as const : 'Rover' as const }
}

export default function App() {
  const { region, screen, view, missionStage, routeProfile } = useScreen()
  const [selection, setSelection] = useState('43')
  const [objective, setObjective] = useState(defaultObjective)
  const [terms, setTerms] = useState(initialTerms)
  const [method, setMethod] = useState<Method>('Sample rock')
  const [excludes, setExcludes] = useState<Exclusion[]>(['Polar'])
  const [sort, setSort] = useState<Sort>('Match')
  const [localProfile, setProfile] = useState<Profile>('Rover')
  const profile = missionStage ? routeProfile : localProfile
  const [mission, setMission] = useState(initialMission)
  const hazardView = missionStage && view === 'hazards' && region?.id === '43'
  const hazards = useHazardReplay(hazardView)
  const [layer, setLayer] = useState<'viking' | 'mola'>('viking')
  const [zoom, setZoom] = useState(1)
  const [contrast, setContrast] = useState(false)
  const mobileTools = useRef<HTMLDialogElement>(null)
  const shortcuts = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLElement>(null)
  const previousScreen = useRef(screen)
  const ranked = rankRegions(terms, method, excludes, sort, profile)
  const shortlist = rankRegions(terms, method, excludes, 'Match', profile)
    .filter(item => !isExcluded(item, excludes)).slice(0, 3)
  const selected = region ?? allRegions.find(item => item.id === selection) ?? ranked[0]

  useEffect(() => {
    if (previousScreen.current !== screen) heading.current?.focus()
    previousScreen.current = screen
  }, [screen])

  useEffect(() => {
    if (region) setSelection(region.id)
    document.title = screen === 'investigation' ? region?.name + ' · Return Window'
      : screen === 'ranking' ? 'Region Ranking · Return Window' : 'Return Window · Mars Exploration'
  }, [region, screen])

  function go(stage: string, nextView = '', nextProfile = profile) {
    if (nextProfile !== profile) setProfile(nextProfile)
    window.location.hash = missionHref(stage, nextProfile, selected, nextView)
  }

  function startPlanning(nextProfile: Profile, tasks = false) {
    setProfile(nextProfile)
    go('route', tasks ? 'tasks' : '', nextProfile)
  }

  const activeNav = missionStage ? screen : 'globe'
  const missionProps = {
    region: selected, profile, objective, terms, view, mission,
    update: (change: Partial<typeof mission>) => setMission(current => ({ ...current, ...change })),
    go,
  }

  function toggleFilter(filter: Exclusion) {
    const next = excludes.includes(filter) ? excludes.filter(item => item !== filter) : [...excludes, filter]
    setExcludes(next)
    if (isExcluded(selected, next)) {
      const firstEligible = ranked.find(item => !isExcluded(item, next))
      if (firstEligible) setSelection(firstEligible.id)
    }
  }

  function applyObjective(next: string) {
    setObjective(next)
    setTerms(interpretObjective(next))
  }

  return <div className={`shell screen-${screen}${hazardView ? ' hazard-shell' : ''}${contrast ? ' high-contrast' : ''}`}>
    {screen !== 'evidence' && !(screen === 'route' && ['states','constraints'].includes(view)) && <header className="topbar">
        <a className="wordmark" href={globeHref}>
        <img className="brand-logo" src="./brand/nasa-logo.png" alt="" />
        <span className="wordmark-full">Return Window</span><span className="wordmark-short" aria-hidden="true">RW</span>
      </a>
      <nav className="mission-nav" aria-label="Mission stages">
        <a href={globeHref} aria-current={activeNav==='globe'||undefined}>Explore</a>
        {['Route', 'Analysis', 'Monitor'].map(item => <a key={item}
          href={missionHref(item.toLowerCase(), profile, selected, hazardView ? 'hazards' : '')} aria-current={screen === item.toLowerCase() || undefined}>{item}</a>)}
      </nav>
      {screen==='monitor'&&view==='layout'?<span className="chip filter accent">Editing layout</span>:missionStage ? <nav className="breadcrumbs mission-breadcrumbs" aria-label="Mission">
        <a href={screen==='route'&&['compare','tasks'].includes(view)?missionHref('route',profile,selected):screen==='monitor'&&view==='salvage'?missionHref('monitor',profile,selected,'contingency'):regionHref(selected.id)}>{screen==='route'&&view==='compare'?'Routes':screen==='route'&&view==='tasks'?'Route':screen==='monitor'&&view==='salvage'?'Contingency':selected.name}</a>
        {screen==='monitor'&&view==='salvage'?<><span>/</span><span>Salvage targets</span></>:screen==='route'&&['compare','tasks'].includes(view)?<><span aria-hidden="true">/</span><span>{view==='compare'?'Compare':'Science tasks'}</span></>:<span className="mono muted">{hazardView ? 'North ramp drill' : <>{screen==='analysis'&&view==='record'?'Mission M-03 · revision '+(mission.decision?Math.max(4,mission.revision):4):profile === 'Rover' ? (screen==='monitor'&&view==='contingency'?'R-013':mission.plan) : 'EVA-A'}{screen==='analysis'&&view!=='record'&&profile==='Rover'?' · Rover '+mission.rover:''}{screen === 'monitor' && profile === 'Rover' ? (view==='contingency'?' · replan':' · Route ' + mission.route) : ''}</>}</span>}
        {screen==='analysis'&&!view&&<span className="chip filter caution">Terrain SIM · weather dummy · illustrative result</span>}
        {screen === 'monitor' && !hazardView && <><span className="badge">{profile === 'Rover' ? 'SIMULATED PLAYBACK' : 'SIMULATION'}</span>{profile==='Astronaut'&&!view&&<span className="badge">LINK DELAY N/A</span>}</>}
      </nav> : screen !== 'globe' && <nav className="breadcrumbs" aria-label="Explore">
        <a href={screen === 'pack' ? regionHref(selected.id) : globeHref}>{screen === 'ranking' ? 'Globe' : screen === 'pack' ? selected.name : 'Mars'}</a>
        <span aria-hidden="true">/</span><span aria-current="page">{screen === 'ranking' ? 'Ranking' : screen === 'pack' ? 'Site pack' : region?.name}</span>
      </nav>}
      {screen==='route'&&!hazardView&&<IconButton className="icon-button compact-header-menu" aria-label="Planning menu" onClick={()=>mobileTools.current?.showModal()}><List size={17}/></IconButton>}
      <div className="topbar-end">
        {screen === 'globe' && <span className="event-name">NASA Space Apps Challenge 2026</span>}
        {missionStage && selected.id === '43' && !hazardView &&
          <a className="button hazard-entry" href={missionHref(screen, profile, selected, 'hazards')}>Hazard drill</a>}
        {hazardView && <a className="button hazard-entry" href={missionHref(screen, profile, selected)}>Exit drill view</a>}
        {screen==='monitor'&&view==='contingency'?<span className="chip filter bad">Route {mission.route} invalid · rover holding</span>:screen==='monitor'&&view==='tradeoff'?<span className="mono">01:32:10</span>:screen==='monitor'&&['layout','salvage'].includes(view)?null:screen==='analysis'||screen==='route'&&['profiles','compare','tasks'].includes(view)?null:screen === 'pack' ? <span className="chip filter caution">Routing capability withheld</span> : screen !== 'investigation' &&
          <Segmented items={profiles} value={profile} onChange={next => missionStage ? go(screen, hazardView ? 'hazards' : '', next) : setProfile(next)} label="Mission profile" />}
        {screen==='monitor'&&profile==='Astronaut'&&!view&&<span className="chip filter caution eva-overrun">⚠ Stop 1 overrun 0:13</span>}
        {!(screen==='monitor'&&['contingency','tradeoff','salvage','layout'].includes(view)) && screen !== 'ranking' && screen !== 'pack' && !(screen==='analysis'&&view) && !(screen==='route'&&['profiles','compare','tasks'].includes(view)) && <div className="utility">
          <IconButton aria-label="Keyboard shortcuts" title="Keyboard shortcuts"
            onClick={() => shortcuts.current?.showModal()}><Terminal size={16} weight="bold" /></IconButton>
          {!hazardView&&(screen==='route'||screen==='monitor'||screen==='analysis')&&<IconButton aria-label="Edit layout" title="Edit layout" onClick={()=>go('monitor','layout')}><SquaresFour size={16} weight="bold"/></IconButton>}
          <IconButton aria-label="High contrast" title="High contrast" aria-pressed={contrast}
            onClick={() => setContrast(value => !value)}><Sun size={17} weight="bold" /></IconButton>
        </div>}
      </div>
    </header>}

    <main ref={heading} tabIndex={-1} className="screen-content" aria-label={
      screen === 'globe' ? 'Planetary Explore' : screen === 'ranking' ? 'Region Ranking' : screen === 'investigation' ? 'Region Investigation' : screen
    }>
      {screen === 'globe' && <Globe {...{ selected, shortlist, terms, objective, method, excludes, layer, zoom, profile }}
        select={setSelection} setLayer={setLayer} setZoom={setZoom} setMethod={setMethod} setTerms={setTerms}
        applyObjective={applyObjective} toggleFilter={toggleFilter} />}
      {screen === 'ranking' && <Ranking {...{ ranked, selected, objective, terms, method, excludes, sort, profile }}
        select={setSelection} setSort={setSort} />}
      {screen === 'investigation' && region && <Investigation key={region.id} {...{ region, shortlist, objective, terms, profile }} onPlan={startPlanning} />}
      {screen === 'evidence' && <EvidenceGallery region={selected} {...{ objective, terms }} onPlan={startPlanning} onSources={() => { window.location.hash = regionHref(selected.id) }} />}
      {screen === 'pack' && <SitePack region={selected} onPlan={() => startPlanning(profile)} />}
      {hazardView && (screen === 'route' || screen === 'analysis' || screen === 'monitor') &&
        <HazardMission key={profile + screen} replay={hazards} platform={profile === 'Rover' ? 'rover' : 'human'}
          stage={screen} go={stage => go(stage, 'hazards')} />}
      {!hazardView && screen === 'route' && <Planning key={profile} {...missionProps} />}
      {!hazardView && screen === 'analysis' && <Analysis {...missionProps} />}
      {!hazardView && screen === 'monitor' && <Monitoring key={profile} {...missionProps} />}
    </main>

    <dialog ref={mobileTools} className="dialog" aria-labelledby="planning-menu-title">
      <h2 id="planning-menu-title">Planning menu</h2>
      <div className="vertical-actions">
        {[['Rover profiles','profiles'],['Science tasks','tasks'],['Route result states','states']].map(([label,key])=>
          <button className="button" key={key} onClick={()=>{mobileTools.current?.close();go('route',key)}}>{label}</button>)}
        {selected.id === '43' && <button className="button" onClick={()=>{mobileTools.current?.close();go('route','hazards')}}>Hazard drill</button>}
        <button className="button" onClick={()=>{mobileTools.current?.close();go('route','',profile==='Rover'?'Astronaut':'Rover')}}>Switch to {profile==='Rover'?'Astronaut':'Rover'}</button>
      </div>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>

    <dialog ref={shortcuts} className="dialog" aria-labelledby="shortcut-title">
      <h2 id="shortcut-title">Keyboard shortcuts</h2>
      <p>Tab to move between controls. Enter or Space activates the focused button. On the globe, use + and − to zoom and 0 to reset. In the investigation tabs, use the arrow keys to switch panels.</p>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>
  </div>
}
