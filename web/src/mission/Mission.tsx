import { useCallback, useEffect, useState } from 'react'
import { getHealth } from './api'
import type { Health } from './api'
import { SiteInvestigation } from './SiteInvestigation'
import { Simulation } from './Simulation'
import { byRegion, profiles } from '../atlas/data'
import type { Profile } from '../atlas/data'
import { primaryRegion } from './site'
import './mission.css'

type View = 'site' | 'simulation'
type Selection = { regionId: string; profile: Profile; view: View }

function readSelection(): Selection {
  const params = new URLSearchParams(location.search)
  const profile = params.get('profile') as Profile | null
  return {
    regionId: params.get('region') ?? primaryRegion,
    profile: profile && profiles.includes(profile) ? profile : 'human',
    view: params.get('view') === 'simulation' ? 'simulation' : 'site',
  }
}

function useSelection() {
  const [selection, setSelection] = useState(readSelection)
  useEffect(() => {
    const sync = () => setSelection(readSelection())
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const update = useCallback((next: Selection) => {
    const url = new URL(location.href)
    url.searchParams.set('legacy', '1')
    url.searchParams.set('region', next.regionId)
    url.searchParams.set('profile', next.profile)
    if (next.view === 'simulation') url.searchParams.set('view', next.view)
    else url.searchParams.delete('view')
    history.pushState(null, '', url)
    setSelection(next)
    window.scrollTo(0, 0)
  }, [])
  return [selection, update] as const
}

function ServiceStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(setHealth, () => {})
    return () => controller.abort()
  }, [])
  const state = health?.state ?? 'checking'
  const label = health === null ? 'Checking service' : health.state === 'ready' ? 'Service ready' : 'Service unavailable'
  return (
    <span className="mission-health" data-state={state} role="status" title={health?.state === 'unavailable' ? health.reason : undefined}>
      <i aria-hidden="true"/>{label}
    </span>
  )
}

export default function Mission() {
  const [selection, update] = useSelection()
  const { view, regionId, profile } = selection
  const region = byRegion.get(regionId)
  const simulation = view === 'simulation'
  const exploreHref = region ? '/explore?' + new URLSearchParams({ region: region.id }) : '/explore'
  const setView = (view: View) => update({ ...selection, view })
  useEffect(() => {
    document.title = `${simulation ? 'Simulated Marswalk' : 'Site investigation'} · Return Window`
  }, [simulation])
  return (
    <main className="mission-app" data-view={view}>
      <header className="mission-masthead">
        <a className="mission-brand" href={exploreHref}>Return Window</a>
        <div className="mission-crumbs">
          {simulation ? (
            <>
              <button className="mission-link" onClick={() => setView('site')}>Site investigation</button>
              <span aria-hidden="true">/</span>
              <span>Simulated Marswalk</span>
              <span className="mission-sim-tag" data-testid="simulation-tag">Simulation</span>
            </>
          ) : <span>Site investigation</span>}
        </div>
        <nav className="mission-nav" aria-label="Workspaces">
          <ServiceStatus/>
          <a href={exploreHref}>Explore Mars</a>
        </nav>
      </header>
      {simulation && (
        <p className="mission-sim-banner" role="note">
          <strong>Simulation.</strong> Synthetic fixture with test travel values on its own grid. Not real-site routing, not a safety or navigation prediction.
        </p>
      )}
      {simulation ? <Simulation/> : region
        ? <SiteInvestigation key={region.id} region={region} profile={profile}
          onChange={regionId => update({ ...selection, regionId })} onEnterSimulation={() => setView('simulation')}/>
        : <section className="mission-card" role="alert">
          <h1>Unknown Atlas region</h1>
          <p>Choose a valid region in the <a href={exploreHref}>Mars Atlas</a>.</p>
        </section>}
    </main>
  )
}
