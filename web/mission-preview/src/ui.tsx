import { useId, useRef } from 'react'
import type { ButtonHTMLAttributes, KeyboardEvent, ReactNode } from 'react'

export const globeHref = '#globe'
export const rankingHref = '#ranking'
export const regionHref = (id: string) => '#region/' + id

export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>
}

export function IconButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className="icon-button" {...props}>{children}</button>
}

export function Segmented<T extends string>({ items, value, onChange, label }: {
  items: readonly T[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return <div className="segmented" role="group" aria-label={label}>
    {items.map(item => <button key={item} type="button" aria-pressed={item === value}
      onClick={() => onChange(item)}>{item}</button>)}
  </div>
}

export function Tabs<T extends string>({ items, value, onChange, label, children }: {
  items: readonly T[]
  value: T
  onChange: (value: T) => void
  label: string
  children: ReactNode
}) {
  const prefix = useId()
  const buttons = useRef(new Map<T, HTMLButtonElement>())
  function move(event: KeyboardEvent, index: number) {
    const indices: Record<string, number> = {
      ArrowRight: (index + 1) % items.length,
      ArrowLeft: (index - 1 + items.length) % items.length,
      Home: 0,
      End: items.length - 1,
    }
    const next = indices[event.key]
    if (next === undefined) return
    event.preventDefault()
    onChange(items[next])
    buttons.current.get(items[next])?.focus()
  }
  return <>
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((item, index) => <button key={item} id={prefix + 'tab-' + item} type="button" role="tab"
        ref={element => { if (element) buttons.current.set(item, element) }}
        aria-selected={value === item} aria-controls={prefix + 'panel-' + item}
        tabIndex={value === item ? 0 : -1}
        onClick={() => onChange(item)} onKeyDown={event => move(event, index)}>{item}</button>)}
    </div>
    <div role="tabpanel" id={prefix + 'panel-' + value} aria-labelledby={prefix + 'tab-' + value} tabIndex={0}>{children}</div>
  </>
}

export function Metrics({ children }: { children: ReactNode }) {
  return <dl className="metrics">{children}</dl>
}
