import { useEffect, useId, useRef, useState } from 'react'
import { MapPin } from '@phosphor-icons/react'
import { coordinates, formatPoint, locateCell } from './cells'
import type { MarsBase } from './cells'

export function BaseLocation({ base, onChange }: { base?: MarsBase; onChange: (base?: MarsBase) => void }) {
  const titleId = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  const request = useRef<AbortController>(null)
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => () => request.current?.abort(), [])
  return <>
    <button className="button compact base-trigger" aria-haspopup="dialog" type="button" onClick={() => {
      setLat(base ? String(base.coordinates[1]) : '')
      setLon(base ? String(base.coordinates[0]) : '')
      setError('')
      dialog.current?.showModal()
    }}><MapPin size={13} />{base ? 'Edit Mars base' : 'Set Mars base'}</button>
    {base && <span className="mono muted base-readout" title={base.cell.id}>{formatPoint(base.coordinates, 4)}</span>}
    <dialog ref={dialog} className="dialog" aria-labelledby={titleId} onClose={() => {
      request.current?.abort()
      setPending(false)
    }}>
      <form onSubmit={async event => {
        event.preventDefault()
        const point = coordinates(lat, lon)
        if (!point) { setError('Enter a latitude from −90 to 90 and a longitude from −180 to 180.'); return }
        request.current?.abort()
        const controller = new AbortController()
        request.current = controller
        setPending(true)
        setError('')
        try {
          const cell = await locateCell(point, controller.signal)
          if (controller.signal.aborted) return
          onChange({ coordinates: point, cell })
          dialog.current?.close()
        } catch (cause) {
          if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not resolve the base cell.')
        } finally {
          if (!controller.signal.aborted) setPending(false)
        }
      }}>
        <h2 id={titleId}>Mars base coordinates</h2>
        <p>Set the Marswalker’s starting location. Enter Mars planetocentric degrees; north and east are positive.</p>
        <div className="base-fields">
          <label>Latitude <input name="latitude" inputMode="decimal" required value={lat} autoFocus
            placeholder="−90 to 90" onChange={e => setLat(e.target.value)} /></label>
          <label>Longitude <input name="longitude" inputMode="decimal" required value={lon}
            placeholder="−180 to 180" onChange={e => setLon(e.target.value)} /></label>
        </div>
        {error && <p role="alert" className="base-error">{error}</p>}
        {base && <p className="mono">Saved starting cell · {base.cell.id}</p>}
        <div className="dialog-actions">
          {base && <button className="button base-clear" type="button" onClick={() => { onChange(); dialog.current?.close() }}>Clear base</button>}
          <button className="button" type="button" onClick={() => dialog.current?.close()}>Cancel</button>
          <button className="button primary" type="submit" disabled={pending}>{pending ? 'Locating…' : 'Set base'}</button>
        </div>
      </form>
    </dialog>
  </>
}
