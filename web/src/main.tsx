import { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const Explore = lazy(() => import('./explore/Explore'))
const Atlas = lazy(() => import('./atlas/Atlas'))
const Architecture = lazy(() => import('./App'))
const Mission = lazy(() => import('./mission/Mission'))
const route = (path: string) => location.pathname === path || location.pathname === `${path}/`
const atlas = route('/atlas')
const mission = route('/mission')
const explore = route('/explore') || mission && new URLSearchParams(location.search).has('cell')
if (atlas) document.title = 'Mars Research Atlas · Return Window'
if (mission) document.title = 'Mission · Return Window'
createRoot(document.getElementById('root')!).render(explore
  ? <Suspense fallback={<p role="status">Opening Explore…</p>}><Explore/></Suspense> : atlas
  ? <Suspense fallback={<p role="status">Opening Mars Research Atlas…</p>}><Atlas/></Suspense>
  : mission
    ? <Suspense fallback={<p role="status">Opening Mission…</p>}><Mission/></Suspense>
    : <Suspense fallback={<p role="status">Opening Architecture Workspace…</p>}><Architecture/></Suspense>)
