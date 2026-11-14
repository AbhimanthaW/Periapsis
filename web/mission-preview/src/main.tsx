import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource/ibm-plex-mono/latin-400.css'
import App from './App'
import './styles.css'
import './mission.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
