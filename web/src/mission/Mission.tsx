import { useCallback, useEffect, useState } from 'react'
import { getHealth } from './api'
import type { Health } from './api'
import { SiteInvestigation } from './SiteInvestigation'
import { Simulation } from './Simulation'
import './mission.css'

type View = 'site' | 'simulation'
const readView = (): View => new URLSearchParams(location.search).get('view') === 'simulation' ? 'simulation' : 'site'

function useView() {
  const [view, setViewState] = useState<View>(readView)
  useEffect(() => {
    const sync = () => setViewState(readView())
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const setView = useCallback((next: View) => {
    const url = new URL(location.href)
    if (next === 'simulation') url.searchParams.set('view', 'simulation')
    else url.searchParams.delete('view')
    history.pushState(null, '', url)
    setViewState(next)
    window.scrollTo(0, 0)
  }, [])
  return [view, setView] as const
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
  const [view, setView] = useView()
  const simulation = view === 'simulation'
  useEffect(() => {
    document.title = `${simulation ? 'Simulated Marswalk' : 'Site investigation'} · Return Window`
  }, [simulation])
  return (
    <main className="mission-app" data-view={view}>
      <header className="mission-masthead">
        <a className="mission-brand" href="/mission">Return Window</a>
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
          <a href="/atlas">Mars Atlas</a>
          <a href="/">Architecture</a>
        </nav>
      </header>
      {simulation && (
        <p className="mission-sim-banner" role="note">
          <strong>Simulation.</strong> Synthetic fixture with test travel values on its own grid. Not real-site routing, not a safety or navigation prediction.
        </p>
      )}
      {simulation ? <Simulation/> : <SiteInvestigation onEnterSimulation={() => setView('simulation')}/>}
    </main>
  )
}
