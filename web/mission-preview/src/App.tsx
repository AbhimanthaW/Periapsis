import { useEffect, useRef, useState } from 'react'
import { List, SquaresFour, Sun, Terminal } from '@phosphor-icons/react'
import { Globe } from './Globe'
import { BaseLocation } from './BaseLocation'
import { EvidenceGallery, SitePack } from './RegionEvidence'
import { initialMission, missionHref } from './mission'
import { AdvisoryScienceTasks, Planning } from './Planning'
import { Analysis } from './Analysis'
import { Monitoring } from './Monitoring'
import { HazardMission } from './hazards/HazardMission'
import { useHazardReplay } from './hazards/replay'
import { Ranking } from './Ranking'
import { CELL_COUNT, JEZERO_ANCHOR, getCell, indicatorPoint, initialBase, isCellId, locateCell, persistBase, rankCells } from './cells'
import type { CellContext, CellSelection, CellSort, RankingState } from './cells'
import { Investigation } from './Investigation'
import {
  allRegions, defaultObjective, initialTerms, interpretObjective, profiles,
} from './regions'
import type { Exclusion, Method, Profile, Region } from './regions'
import { globeHref, IconButton, rankingHref, regionHref, Segmented } from './ui'
import { arcadiaScenario } from './objective-methods/arcadia'
import { confirmGoals, interpretObjective as interpretMethods } from './objective-methods/interpret'
import { recommendMethods } from './objective-methods/recommend'
import type { GoalId } from './objective-methods/catalog'

const advisoryHref = (profile: Profile) => '#route/' + profile.toLowerCase() + '/' + arcadiaScenario.regionId + '/tasks'
const arcadiaDemoHref = (profile: Profile = arcadiaScenario.profile) =>
  profile === 'Rover' ? '#demo/arcadia/rover' : '#demo/arcadia'
const arcadiaDemoIntent = interpretMethods(arcadiaScenario.objective)
const noAreas: NonNullable<RankingState['result']>['areas'] = []

function useScreen() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    function update() { setHash(window.location.hash) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const [stage, mode, id, view = ''] = hash.slice(1).split('/')
  const missionStage = stage === 'route' || stage === 'analysis' || stage === 'monitor'
  const regionId = missionStage ? id : mode
  const arcadiaDemo = hash === arcadiaDemoHref() || hash === arcadiaDemoHref('Rover')
  const advisory = arcadiaDemo
    || ((missionStage || ['pack', 'evidence', 'region'].includes(stage)) && regionId === arcadiaScenario.regionId)
  const rehearsal = missionStage && regionId === '43'
  const planningWithheld = missionStage && !advisory && !rehearsal
  const profileSegment = arcadiaDemo ? id : mode
  const region = advisory ? undefined : allRegions.find(item => item.id === regionId)
  const cellId = stage === 'cell' && isCellId(mode) ? mode : undefined
  const screen = cellId ? 'investigation' : advisory ? 'science-advisory' : planningWithheld ? 'site-withheld' : rehearsal ? stage : region && stage === 'pack' ? 'pack'
    : region && stage === 'evidence' ? 'evidence' : region && stage === 'region' ? 'investigation'
    : hash === rankingHref ? 'ranking' : 'globe'
  return { region, regionId, cellId, screen, view, arcadiaDemo, missionStage: rehearsal,
    routeProfile: profileSegment === 'rover' ? 'Rover' as const
      : advisory || profileSegment === 'astronaut' ? 'Astronaut' as const : 'Rover' as const }
}

export default function App() {
  useEffect(() => {
    if (import.meta.env.BASE_URL !== '/demo/') return
    if (location.hash.startsWith('#demo/arcadia')) location.replace('/explore?demo=1')
  }, [])
  const { region, regionId, cellId, screen, view, arcadiaDemo, missionStage, routeProfile } = useScreen()
  const [selection, setSelection] = useState<CellSelection>()
  const [cellContext, setCellContext] = useState<CellContext>()
  const [base, setBase] = useState(initialBase)
  const [locating, setLocating] = useState(false)
  const [cellBusy, setCellBusy] = useState(false)
  const [locateError, setLocateError] = useState('')
  const [cellError, setCellError] = useState('')
  const [cellRetry, setCellRetry] = useState(0)
  const markerRequest = useRef<AbortController>(null)
  const lastIndicator = useRef<Region | undefined>(undefined)
  const [ranking, setRanking] = useState<RankingState>({ status: 'idle' })
  const [rankRevision, setRankRevision] = useState(0)
  const [editedTerms, setEditedTerms] = useState(false)
  const [objective, setObjective] = useState(defaultObjective)
  const [intent, setIntent] = useState(() => interpretMethods(defaultObjective))
  const [arcadiaLoaded, setArcadiaLoaded] = useState(false)
  const [arcadiaVisited, setArcadiaVisited] = useState(false)
  const [advisoryProfile, setAdvisoryProfile] = useState<Profile>(arcadiaScenario.profile)
  const [terms, setTerms] = useState(initialTerms)
  const [method, setMethod] = useState<Method>('Sample rock')
  const [excludes, setExcludes] = useState<Exclusion[]>(['Polar'])
  const [sort, setSort] = useState<CellSort>('Match')
  const [localProfile, setProfile] = useState<Profile>('Rover')
  const profile = missionStage ? routeProfile : localProfile
  const [mission, setMission] = useState(initialMission)
  const packaged = import.meta.env.BASE_URL === '/demo/'
  const sourceSelection = new URLSearchParams(location.search)
  const sourceRegion = sourceSelection.get('region')
  const sourceCell = sourceSelection.get('cell')
  const sourceProfile = sourceSelection.get('profile')
  const hazardView = missionStage && view === 'hazards' && region?.id === '43'
  const hazards = useHazardReplay(hazardView)
  const [layer, setLayer] = useState<'viking' | 'mola'>('viking')
  const [zoom, setZoom] = useState(1)
  const [contrast, setContrast] = useState(false)
  const mobileTools = useRef<HTMLDialogElement>(null)
  const shortcuts = useRef<HTMLDialogElement>(null)
  const missionEntry = useRef<HTMLDialogElement>(null)
  const [entryStage, setEntryStage] = useState('Route')
  const heading = useRef<HTMLElement>(null)
  const screenKey = screen + '/' + (cellId ?? region?.id ?? '')
  const previousScreen = useRef(screenKey)
  const availableAreas = ranking.status === 'ready' ? ranking.result?.areas ?? noAreas : noAreas
  const topAreas = availableAreas.slice(0, 3)
  const activeCell = cellId
    ? selection?.id === cellId ? selection : { id: cellId, label: availableAreas.find(area => area.best_cell === cellId)?.label ?? undefined }
    : selection
  const context = cellContext?.cell.id === activeCell?.id ? cellContext : undefined
  // The published CTX crop is keyed to the explicitly opened Jezero anchor.
  // Mission fixture links remain available through their existing direct routes.
  const selected = region ?? allRegions.find(item =>
    item.id === (activeCell?.id === JEZERO_ANCHOR ? '43' : activeCell?.markerId))
  const fixture = selected ?? allRegions[0]
  const displayRegion = region ?? (activeCell?.id === JEZERO_ANCHOR ? fixture : undefined)
  const browseSlice = ['globe', 'ranking', 'investigation'].includes(screen)
  const advisoryScreen = screen === 'science-advisory'
  const reviewProfile = advisoryScreen ? routeProfile : arcadiaLoaded ? advisoryProfile : profile
  const proposal = recommendMethods(arcadiaDemo ? arcadiaDemoIntent : intent, arcadiaLoaded || advisoryScreen ? {
    regionId: arcadiaScenario.regionId, footprint: arcadiaScenario.footprint, profile: reviewProfile,
  } : { regionId: activeCell?.id ?? 'unselected', profile: reviewProfile })
  const reviewRegionName = arcadiaLoaded || advisoryScreen ? arcadiaScenario.regionName : activeCell?.label ?? activeCell?.id ?? 'No cell selected'

  useEffect(() => {
    if (previousScreen.current !== screenKey) heading.current?.focus()
    previousScreen.current = screenKey
  }, [screenKey])

  useEffect(() => {
    if (cellId && cellId !== selection?.id) {
      setSelection({ id: cellId, label: availableAreas.find(area => area.best_cell === cellId)?.label ?? undefined })
    }
  }, [cellId, selection?.id, availableAreas])

  useEffect(() => {
    document.title = advisoryScreen ? 'Arcadia Science Tasks · Return Window'
      : screen === 'investigation' ? (displayRegion?.name ?? activeCell?.label ?? cellId) + ' · Return Window'
      : screen === 'ranking' ? 'Ranked Areas · Return Window' : 'Return Window · Mars Exploration'
  }, [displayRegion, activeCell?.label, cellId, screen, advisoryScreen])

  useEffect(() => {
    const id = activeCell?.id
    if (!id) return
    const controller = new AbortController()
    setCellError('')
    setCellBusy(true)
    getCell(id, controller.signal).then(data => {
      if (!controller.signal.aborted) setCellContext(data)
    }).catch(error => {
      if (!controller.signal.aborted) setCellError(error instanceof Error ? error.message : 'Cell evidence unavailable.')
    }).finally(() => {
      if (!controller.signal.aborted) setCellBusy(false)
    })
    return () => controller.abort()
  }, [activeCell?.id, cellRetry])

  useEffect(() => () => markerRequest.current?.abort(), [])

  useEffect(() => {
    if (screen === 'ranking') setRankRevision(revision => revision || 1)
  }, [screen])

  const rankQuery = editedTerms ? terms.join(' ') : objective
  useEffect(() => {
    if (!rankRevision) return
    const controller = new AbortController()
    setRanking({ status: 'loading' })
    rankCells(rankQuery, method, excludes, controller.signal).then(result => {
      if (!controller.signal.aborted) setRanking({ status: 'ready', result })
    }).catch(error => {
      if (!controller.signal.aborted) setRanking({ status: 'error', error: error instanceof Error ? error.message : 'Ranking unavailable.' })
    })
    return () => controller.abort()
  }, [rankRevision, rankQuery, method, excludes])

  function rank() { setRankRevision(revision => revision || 1) }

  function chooseCell(next: CellSelection) {
    markerRequest.current?.abort()
    lastIndicator.current = undefined
    setLocating(false)
    setLocateError('')
    setSelection(current => current?.id === next.id
      ? { ...current, ...next, label: next.label ?? current.label }
      : next)
    setArcadiaLoaded(false)
  }

  async function selectIndicator(indicator: Region) {
    const point = indicatorPoint(indicator.coords)
    if (!point) return
    markerRequest.current?.abort()
    const controller = new AbortController()
    markerRequest.current = controller
    lastIndicator.current = indicator
    setLocating(true)
    setLocateError('')
    try {
      const cell = await locateCell(point, controller.signal)
      if (!controller.signal.aborted) chooseCell({ id: cell.id, markerId: indicator.id, label: indicator.name })
    } catch (error) {
      if (!controller.signal.aborted) setLocateError(error instanceof Error ? error.message : 'Could not locate the landmark.')
    } finally {
      if (!controller.signal.aborted) setLocating(false)
    }
  }

  function retrySelection() {
    if (lastIndicator.current) void selectIndicator(lastIndicator.current)
    else setCellRetry(value => value + 1)
  }

  function updateTargets(next: string[]) {
    setEditedTerms(next.length > 0)
    setTerms(next.length ? next : interpretObjective(objective))
    rank()
  }

  const walkParams = base && new URLSearchParams({
    cell: base.cell.id, base: base.coordinates.join(','),
  })
  const walkOrigin = packaged ? '' : (import.meta.env.VITE_MARSWALK_ORIGIN ?? 'http://127.0.0.1:4175')
  const walkHref = walkParams ? walkOrigin + '/explore?' + walkParams : undefined
  function updateBase(next?: typeof base) {
    setBase(next)
    persistBase(next)
  }

  function go(stage: string, nextView = '', nextProfile = profile) {
    if (nextProfile !== profile) setProfile(nextProfile)
    window.location.hash = missionHref(stage, nextProfile, fixture, nextView)
  }

  function startPlanning(nextProfile: Profile, tasks = false) {
    setProfile(nextProfile)
    go('route', tasks ? 'tasks' : '', nextProfile)
  }

  const activeNav = missionStage ? screen : 'globe'
  const missionProps = {
    region: fixture, profile, objective, terms, view, mission,
    update: (change: Partial<typeof mission>) => setMission(current => ({ ...current, ...change })),
    go,
  }

  function toggleFilter(filter: Exclusion) {
    const next = excludes.includes(filter) ? excludes.filter(item => item !== filter) : [...excludes, filter]
    setExcludes(next)
    rank()
  }

  function applyObjective(next: string) {
    setObjective(next)
    setTerms(interpretObjective(next))
    setIntent(interpretMethods(next))
    setEditedTerms(false)
    rank()
  }

  function loadArcadia() {
    applyObjective(arcadiaScenario.objective)
    setArcadiaLoaded(true)
    setArcadiaVisited(true)
    setAdvisoryProfile(arcadiaScenario.profile)
  }

  function setReviewProfile(next: Profile) {
    setAdvisoryProfile(next)
    if (advisoryScreen) window.location.hash = arcadiaDemo ? arcadiaDemoHref(next) : advisoryHref(next)
  }

  function updateGoals(goals: readonly GoalId[]) {
    setIntent(current => confirmGoals(current, goals))
  }

  return <div className={`shell screen-${screen}${hazardView ? ' hazard-shell' : ''}${contrast ? ' high-contrast' : ''}`}>
    {screen !== 'evidence' && !(screen === 'route' && ['states','constraints'].includes(view)) && <header className="topbar">
        <a className="wordmark" href={globeHref} aria-label="Return Window">
        <img className="brand-logo" src={import.meta.env.BASE_URL + 'brand/nasa-logo.svg'} width="110" height="92" alt="" />
        <span className="wordmark-full">Return Window</span><span className="wordmark-short" aria-hidden="true">RW</span>
      </a>
      <nav className="mission-nav" aria-label="Mission stages">
        <a href={globeHref} aria-current={activeNav === 'globe' && !advisoryScreen ? 'page' : undefined}>Explore</a>
        {packaged && (arcadiaDemo || (hazardView && sourceRegion)) &&
          <a href={'/mission?' + new URLSearchParams({
            region: hazardView && sourceRegion ? sourceRegion : arcadiaDemo ? arcadiaScenario.regionId : fixture.id,
            profile: hazardView && sourceProfile ? sourceProfile : (arcadiaDemo ? reviewProfile : profile) === 'Rover' ? 'rover' : 'human',
          })}>Atlas evidence workspace</a>}
        {packaged && hazardView && sourceCell && <a href={'/explore?' + sourceSelection}>Return to cell evidence</a>}
        {!advisoryScreen && screen !== 'site-withheld' && ['Route', 'Analysis', 'Monitor'].map(item => {
          if (browseSlice && item === 'Route' && walkHref) return <a key={item} href={walkHref}>Route</a>
          if (browseSlice && !displayRegion && activeCell?.id !== JEZERO_ANCHOR) return <button key={item} aria-haspopup="dialog"
            onClick={() => { setEntryStage(item); missionEntry.current?.showModal() }}>{item}</button>
          return <a key={item} href={missionHref(item.toLowerCase(), profile, fixture, hazardView ? 'hazards' : '')}
            aria-current={screen === item.toLowerCase() || undefined}>{item}</a>
        })}
      </nav>
      {screen==='monitor'&&view==='layout'?<span className="chip filter accent">Editing layout</span>:missionStage ? <nav className="breadcrumbs mission-breadcrumbs" aria-label="Mission">
        <a href={screen==='route'&&['compare','tasks'].includes(view)?missionHref('route',profile,fixture):screen==='monitor'&&view==='salvage'?missionHref('monitor',profile,fixture,'contingency'):regionHref(fixture.id)}>{screen==='route'&&view==='compare'?'Routes':screen==='route'&&view==='tasks'?'Route':screen==='monitor'&&view==='salvage'?'Contingency':fixture.name}</a>
        {screen==='monitor'&&view==='salvage'?<><span>/</span><span>Salvage targets</span></>:screen==='route'&&['compare','tasks'].includes(view)?<><span aria-hidden="true">/</span><span>{view==='compare'?'Compare':'Science tasks'}</span></>:<span className="mono muted">{hazardView ? 'North ramp drill' : <>{screen==='analysis'&&view==='record'?'Mission M-03 · revision '+(mission.decision?Math.max(4,mission.revision):4):profile === 'Rover' ? (screen==='monitor'&&view==='contingency'?'R-013':mission.plan) : 'EVA-A'}{screen==='analysis'&&view!=='record'&&profile==='Rover'?' · Rover '+mission.rover:''}{screen === 'monitor' && profile === 'Rover' ? (view==='contingency'?' · replan':' · Route ' + mission.route) : ''}</>}</span>}
        {screen==='analysis'&&!view&&<span className="chip filter caution">Terrain SIM · weather dummy · illustrative result</span>}
        {screen === 'monitor' && !hazardView && <><span className="badge">{profile === 'Rover' ? 'SIMULATED PLAYBACK' : 'SIMULATION'}</span>{profile==='Astronaut'&&!view&&<span className="badge">LINK DELAY N/A</span>}</>}
      </nav> : advisoryScreen ? <nav className="breadcrumbs" aria-label="Science Tasks">
        <span>Arcadia Planitia · Science Tasks</span>
      </nav> : screen !== 'globe' && <nav className="breadcrumbs" aria-label="Explore">
        <a href={screen === 'pack' ? regionHref(fixture.id) : globeHref}>{screen === 'ranking' ? 'Globe' : screen === 'pack' ? fixture.name : 'Mars'}</a>
        <span aria-hidden="true">/</span><span aria-current="page">{screen === 'ranking' ? 'Ranked areas' : screen === 'pack' ? 'Site pack' : displayRegion?.name ?? activeCell?.label ?? cellId}</span>
      </nav>}
      {screen==='route'&&!hazardView&&<IconButton className="icon-button compact-header-menu" aria-label="Planning menu" onClick={()=>mobileTools.current?.showModal()}><List size={17}/></IconButton>}
      <div className="topbar-end">
        {packaged && screen === 'globe' && <a className="button primary" href="/explore?demo=1">Demo</a>}
        {screen === 'globe' && <span className="event-name">NASA Space Apps Challenge 2026</span>}
        {screen === 'ranking' && ranking.status === 'ready' && ranking.result && <span className="mono muted ranking-pack">
          {CELL_COUNT.toLocaleString('en-US')} cells in grid · {ranking.result.pack.version}
        </span>}
        {missionStage && fixture.id === '43' && !hazardView &&
          <a className="button hazard-entry" href={missionHref(screen, profile, fixture, 'hazards')}>Hazard drill</a>}
        {hazardView && <a className="button hazard-entry" href={missionHref(screen, profile, fixture)}>Exit drill view</a>}
        {!advisoryScreen && (screen==='monitor'&&view==='contingency'?<span className="chip filter bad">Route {mission.route} invalid · rover holding</span>:screen==='monitor'&&view==='tradeoff'?<span className="mono">01:32:10</span>:screen==='monitor'&&['layout','salvage'].includes(view)?null:screen==='analysis'||screen==='route'&&['profiles','compare','tasks'].includes(view)?null:screen === 'pack' ? <span className="chip filter caution">Routing capability withheld</span> : screen !== 'investigation' && screen !== 'ranking' &&
          <Segmented items={profiles} value={profile} onChange={next => missionStage ? go(screen, hazardView ? 'hazards' : '', next) : setProfile(next)} label="Mission profile" />)}
        {screen==='monitor'&&profile==='Astronaut'&&!view&&<span className="chip filter caution eva-overrun">⚠ Stop 1 overrun 0:13</span>}
        {!(screen==='monitor'&&['contingency','tradeoff','salvage','layout'].includes(view)) && screen !== 'ranking' && screen !== 'pack' && !(screen==='analysis'&&view) && !(screen==='route'&&['profiles','compare','tasks'].includes(view)) && <div className="utility">
          <IconButton aria-label="Keyboard shortcuts" title="Keyboard shortcuts and demo links"
            onClick={() => shortcuts.current?.showModal()}><Terminal size={16} weight="bold" /></IconButton>
          {!hazardView&&(screen==='route'||screen==='monitor'||screen==='analysis')&&<IconButton aria-label="Edit layout" title="Edit layout" onClick={()=>go('monitor','layout')}><SquaresFour size={16} weight="bold"/></IconButton>}
          <IconButton aria-label="High contrast" title="High contrast" aria-pressed={contrast}
            onClick={() => setContrast(value => !value)}><Sun size={17} weight="bold" /></IconButton>
        </div>}
      </div>
    </header>}

    <main ref={heading} tabIndex={-1} className="screen-content" aria-label={
      screen === 'globe' ? 'Planetary Explore' : screen === 'ranking' ? 'Ranked Areas' : screen === 'investigation' ? 'Region Investigation' : advisoryScreen ? 'Arcadia Science Tasks' : screen
    }>
      {screen === 'globe' && <Globe selected={activeCell} shortlist={topAreas}
        context={context} targetsEdited={editedTerms} selectionError={locateError || cellError} locating={locating || cellBusy}
        retrySelection={retrySelection} selectIndicator={selectIndicator} select={chooseCell} rank={rank}
        {...{ base, terms, objective, method, excludes, layer, zoom }}
        setBase={updateBase}
        setLayer={setLayer} setZoom={setZoom} setMethod={next => { setMethod(next); rank() }} setTerms={updateTargets}
        applyObjective={applyObjective} toggleFilter={toggleFilter}
        {...{ proposal, reviewRegionName, arcadiaLoaded, arcadiaVisited, loadArcadia }}
        useSelectedRegion={() => setArcadiaLoaded(false)} restoreArcadia={() => setArcadiaLoaded(true)}
        onConfirmGoals={updateGoals}
        onProfile={setReviewProfile} reviewHref={advisoryHref(reviewProfile)} />}
      {screen === 'ranking' && <Ranking {...{ ranking, objective, method, excludes, sort }}
        termsEdited={editedTerms} selected={activeCell} select={chooseCell} setSort={setSort} retry={() => setRankRevision(value => value + 1)} />}
      {screen === 'investigation' && (cellId || region) && <Investigation key={cellId ?? region?.id}
        region={displayRegion} selection={cellId ? activeCell : undefined} {...{ objective, terms, profile, base, walkHref }}
        cellContext={context} loading={cellBusy} error={cellError} retry={retrySelection} areas={topAreas}
        match={availableAreas.find(area => area.best_cell === activeCell?.id)}
        onPlan={startPlanning} />}
      {screen === 'evidence' && <EvidenceGallery region={fixture} {...{ objective, terms }} onPlan={startPlanning} onSources={() => { window.location.hash = regionHref(fixture.id) }} />}
      {screen === 'pack' && <SitePack region={fixture} onPlan={() => startPlanning(profile)} />}
      {hazardView && (screen === 'route' || screen === 'analysis' || screen === 'monitor') &&
        <HazardMission key={profile + screen} replay={hazards} platform={profile === 'Rover' ? 'rover' : 'human'}
          stage={screen} go={stage => go(stage, 'hazards')} />}
      {!hazardView && screen === 'route' && <Planning key={profile} {...missionProps} />}
      {!hazardView && screen === 'analysis' && <Analysis {...missionProps} />}
      {!hazardView && screen === 'monitor' && <Monitoring key={profile} {...missionProps} />}
      {screen === 'site-withheld' && <section className="paper-screen">
        <h1>Regional planning withheld{region && ' · ' + region.name}</h1>
        <p>A qualified local terrain pack is required. The available mission and hazard replays use a separate simulated grid.</p>
        {packaged && regionId && <a className="button" href={'/mission?' + new URLSearchParams({
          region: regionId, profile: routeProfile === 'Rover' ? 'rover' : 'human',
        })}>Investigate Atlas region</a>}
        <a className="button" href="#route/rover/43">Open the Jezero simulation</a>
      </section>}
      {advisoryScreen && <AdvisoryScienceTasks proposal={arcadiaDemo || arcadiaLoaded ? proposal : undefined}
        profile={reviewProfile} onProfile={setReviewProfile} />}
    </main>

    <dialog ref={mobileTools} className="dialog" aria-labelledby="planning-menu-title">
      <h2 id="planning-menu-title">Planning menu</h2>
      <div className="vertical-actions">
        {[['Rover profiles','profiles'],['Science tasks','tasks'],['Route result states','states']].map(([label,key])=>
          <button className="button" key={key} onClick={()=>{mobileTools.current?.close();go('route',key)}}>{label}</button>)}
        {fixture.id === '43' && <button className="button" onClick={()=>{mobileTools.current?.close();go('route','hazards')}}>Hazard drill</button>}
        <button className="button" onClick={()=>{mobileTools.current?.close();go('route','',profile==='Rover'?'Astronaut':'Rover')}}>Switch to {profile==='Rover'?'Astronaut':'Rover'}</button>
      </div>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>

    <dialog ref={missionEntry} className="dialog" aria-labelledby="mission-entry-title">
      <h2 id="mission-entry-title">{entryStage} workspace</h2>
      <p>Set a Mars base to open the simulated Marswalk workspace, or open the separate Jezero rehearsal.</p>
      <div className="shortcut-links">
        {walkHref ? <a className="button primary" href={walkHref} onClick={() => missionEntry.current?.close()}>Open simulated Marswalk</a>
          : <BaseLocation onChange={updateBase} />}
        <a className="button" href={missionHref(entryStage.toLowerCase(), profile, allRegions[0])}
          onClick={() => missionEntry.current?.close()}>Open Jezero rehearsal</a>
      </div>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>
    <dialog ref={shortcuts} className="dialog" aria-labelledby="shortcut-title">
      <h2 id="shortcut-title">Keyboard shortcuts</h2>
      <p>Tab to move between controls. Enter or Space activates the focused button. On the globe, use + and − to zoom and 0 to reset. In the investigation tabs, use the arrow keys to switch panels.</p>
      <div className="shortcut-links">
        {!packaged && <a href={arcadiaDemoHref()} onClick={() => shortcuts.current?.close()}>Arcadia demo</a>}
        {(displayRegion?.id === '43' || activeCell?.id === JEZERO_ANCHOR) && <a href={missionHref('monitor', profile, fixture, 'hazards')}
          onClick={() => shortcuts.current?.close()}>Jezero hazard drill</a>}
      </div>
      <form method="dialog" className="dialog-actions"><button className="button">Close</button></form>
    </dialog>
  </div>
}
