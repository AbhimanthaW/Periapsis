import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource/ibm-plex-mono/latin-400.css'
import App from './App'
import './styles.css'
import './mission.css'

const root = createRoot(document.getElementById('root')!)
if (import.meta.env.VITE_PACKAGED_RELEASE === '1' && location.pathname.replace(/\/$/, '') === '/marswalk') {
  void import('./Marswalk').then(({ Marswalk }) => root.render(<Marswalk />))
} else {
  root.render(<StrictMode><App /></StrictMode>)
}
