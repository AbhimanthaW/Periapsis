import { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const Explore = lazy(() => import('./explore/Explore'))
const Mission = lazy(() => import('./mission/Mission'))
const params = new URLSearchParams(location.search)
const mission = location.pathname.replace(/\/$/, '') === import.meta.env.BASE_URL + 'mission' &&
  (params.get('view') === 'simulation' || params.get('legacy') === '1')
if (location.pathname.replace(/\/$/, '') === import.meta.env.BASE_URL + 'atlas') {
  history.replaceState(null, '', import.meta.env.BASE_URL + 'explore' + location.search)
}
document.title = mission ? 'Mission · Return Window' : 'Explore Mars · Return Window'
createRoot(document.getElementById('root')!).render(
  <Suspense fallback={<p role="status">Opening Return Window…</p>}>
    {mission ? <Mission/> : <Explore/>}
  </Suspense>)
