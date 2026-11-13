import { useEffect, useState } from 'react'
import { getHealth } from './api'
import type { Health } from './api'
import { configuredSite } from './site'
import './mission.css'

function SiteStatus() {
  const selection = configuredSite
  if (selection.state === 'unset') return (
    <section className="mission-card" aria-labelledby="mission-site">
      <p className="mission-kicker" id="mission-site">Site · unset</p>
      <h2>No site selected</h2>
      <p className="mission-muted">Primary site awaiting qualification and approval.</p>
    </section>
  )
  if (selection.state === 'invalid') return (
    <section className="mission-card mission-warn" aria-labelledby="mission-site">
      <p className="mission-kicker" id="mission-site">Site · invalid</p>
      <h2>Unknown site “{selection.value}”</h2>
      <p className="mission-muted">VITE_RW_SITE does not match a registered site.</p>
    </section>
  )
  const { site } = selection
  const control = site.role === 'engineering_control'
  return (
    <section className="mission-card" aria-labelledby="mission-site">
      <p className="mission-kicker" id="mission-site">Site · {control ? 'engineering control' : 'primary'}</p>
      <h2>{site.label}</h2>
      {control && <p className="mission-muted">Engineering control only. Not the primary demo site.</p>}
    </section>
  )
}

function ServiceStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(setHealth, () => {})
    return () => controller.abort()
  }, [])
  const label = health === null ? 'Checking…' : health.state === 'ready' ? 'Ready' : 'Unavailable'
  return (
    <section className="mission-card" aria-labelledby="mission-service">
      <p className="mission-kicker" id="mission-service">Planning service</p>
      <h2 role="status" data-state={health?.state ?? 'checking'}>{label}</h2>
      {health?.state === 'unavailable' && <p className="mission-muted">{health.reason}</p>}
    </section>
  )
}

export default function Mission() {
  return (
    <main className="mission-app">
      <header className="mission-masthead">
        <p className="mission-brand">Return Window</p>
        <nav className="mission-nav" aria-label="Workspaces">
          <a href="/atlas">Mars Atlas</a>
          <a href="/">Architecture</a>
        </nav>
      </header>
      <div className="mission-body">
        <h1>Mission</h1>
        <SiteStatus/>
        <ServiceStatus/>
      </div>
    </main>
  )
}
