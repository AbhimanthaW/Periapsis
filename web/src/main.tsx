import { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const Atlas = lazy(() => import('./atlas/Atlas'))
const Architecture = lazy(() => import('./App'))
const atlas = location.pathname === '/atlas' || location.pathname === '/atlas/'
if (atlas) document.title = 'Mars Research Atlas · Return Window'
createRoot(document.getElementById('root')!).render(atlas
  ? <Suspense fallback={<p role="status">Opening Mars Research Atlas…</p>}><Atlas/></Suspense>
  : <Suspense fallback={<p role="status">Opening Architecture Workspace…</p>}><Architecture/></Suspense>)
