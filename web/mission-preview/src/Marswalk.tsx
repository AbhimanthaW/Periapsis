import { useEffect, useState } from 'react'
import { Sortie } from '../../src/explore/Sortie'
import display from '../../../pipeline/evidence/arcadia-planitia/display-metadata.json' with { type: 'json' }
import { cellHref, coordinates, isCellId, locateCell } from './cells'
import '../../src/mission/mission.css'
import '../../src/explore/explore.css'

const params = new URLSearchParams(location.search)
const demo = params.get('demo') === '1'
const expectedCell = params.get('cell')
const [longitude, latitude] = demo ? display.center_lon_lat_deg.map(String) : (params.get('base') ?? '').split(',')
const point = coordinates(latitude ?? '', longitude ?? '')
const stage = (['Route', 'Analysis', 'Monitor'] as const).find(item => item.toLowerCase() === params.get('walk'))

export function Marswalk() {
  const [cellId, setCellId] = useState<string>()
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    document.title = 'Simulated Marswalk · Return Window'
    if (!point || (!demo && !isCellId(expectedCell))) {
      setError('Set a Mars base in Explore to open this simulation.')
      return
    }
    const controller = new AbortController()
    setError('')
    locateCell(point, controller.signal).then(cell => {
      if (controller.signal.aborted) return
      if (!demo && cell.id !== expectedCell) {
        setError('The base coordinates fall outside the requested cell. Set the base again in Explore.')
        return
      }
      setCellId(cell.id)
    }).catch(failure => {
      if (!controller.signal.aborted) setError(failure.message)
    })
    return () => controller.abort()
  }, [attempt])

  const returnHref = demo ? '/#demo/arcadia' : isCellId(expectedCell) ? '/' + cellHref(expectedCell) : '/'
  return <main className="mission-app cell-workspace">
    <header className="mission-masthead">
      <a className="wordmark" href="/" aria-label="Return Window">
        <img className="brand-logo" src="/brand/nasa-logo.svg" width="110" height="92" alt="" />
        <span>Return Window</span>
      </a>
      <a href={returnHref}>{demo ? 'Arcadia evidence' : 'Explore'}</a>
    </header>
    {point && cellId ? <Sortie cellId={cellId} marsPoint={point} demo={demo} initialStage={stage}
      scienceObjective={demo ? 'shallow subsurface ice' : (params.get('objective') ?? '').slice(0, 300)}
      methodInput={params.get('method')} exclusionsInput={params.get('exclude')?.split(',')}
      initialLayer={demo || params.get('layer') === 'mola' ? 'mola' : 'viking'} tileBase="/legacy/atlas/"
      onStageChange={next => {
        const url = new URL(location.href)
        url.searchParams.set('walk', next.toLowerCase())
        url.hash = ''
        history.replaceState(null, '', url)
      }} />
      : <section className="mission-card">
        {error ? <><p role="alert">{error}</p>
          {point && (demo || isCellId(expectedCell)) && <button onClick={() => setAttempt(value => value + 1)}>Retry base lookup</button>}
        </> : <p role="status">Checking the Mars base with the local service…</p>}
      </section>}
  </main>
}
