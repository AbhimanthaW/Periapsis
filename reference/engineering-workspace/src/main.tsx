/// <reference types="vite/client" />

import { lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const atlas = /^\/atlas\/?$/.test(location.pathname)
const Workspace = atlas ? lazy(() => import('./atlas/Atlas')) : lazy(() => import('./App'))
const title = atlas ? 'Mars Research Atlas' : 'Architecture Workspace'
document.title = `${title} · Return Window`

createRoot(document.getElementById('root')!).render(
  <Suspense fallback={<p role="status">Opening {title}…</p>}><Workspace/></Suspense>,
)
