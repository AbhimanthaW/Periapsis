import { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const Atlas = lazy(() => import('./atlas/Atlas'))
const Architecture = lazy(() => import('./App'))
const Mission = lazy(() => import('./mission/Mission'))
const Explore = lazy(() => import('./Explore'))
const route = (path: string) => location.pathname === path || location.pathname === `${path}/`
const atlas = route('/atlas')
const mission = route('/mission')
const explore = route('/explore')
if (atlas) document.title = 'Mars Research Atlas · Return Window'
if (mission) document.title = 'Mission · Return Window'
if (explore) document.title = 'Explore Mars cells · Return Window'
createRoot(document.getElementById('root')!).render(atlas
  ? <Suspense fallback={<p role="status">Opening Mars Research Atlas…</p>}><Atlas/></Suspense>
  : explore
    ? <Suspense fallback={<p role="status">Opening Explore…</p>}><Explore/></Suspense>
  : mission
    ? <Suspense fallback={<p role="status">Opening Mission…</p>}><Mission/></Suspense>
    : <Suspense fallback={<p role="status">Opening Architecture Workspace…</p>}><Architecture/></Suspense>)
