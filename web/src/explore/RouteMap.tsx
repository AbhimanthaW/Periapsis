import { useEffect, useRef, useState } from 'react'
import type { Layer, Point } from './Globe'

const wrap = (longitude: number) => ((longitude + 180) % 360 + 360) % 360 - 180
const modulo = (value: number, period: number) => ((value % period) + period) % period

export function RouteMap({ base, target, layer, showSeparation = false }: { base: Point; target?: Point; layer: Layer; showSeparation?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState([840, 520])
  const [failedLayers, setFailedLayers] = useState<Layer[]>([])
  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0) setSize([width, height])
    })
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  // Copy the target into the world's nearest longitude band before framing the pair.
  const start = wrap(base[0])
  const end = target ? start + wrap(target[0] - start) : start
  const endLat = target?.[1] ?? base[1]
  const ratio = size[0] / size[1]
  const width = Math.max(7, Math.abs(end - start) * 1.38, Math.abs(endLat - base[1]) * ratio * 1.4)
  const height = width / ratio
  const west = (start + end - width) / 2
  const north = height >= 180 ? height / 2 : Math.min(90, Math.max(-90 + height, (base[1] + endLat + height) / 2))
  const x = (lon: number) => (lon - west) / width * size[0]
  const y = (lat: number) => (north - lat) / height * size[1]
  const zoom = width > 175 ? 1 : 2
  const rows = 2 ** zoom, cols = rows * 2
  const step = 180 / rows
  const tiles = []
  for (let row = Math.max(0, Math.floor((90 - north) / step)); row < Math.min(rows, Math.ceil((90 - north + height) / step)); row++) {
    for (let col = Math.floor((west + 180) / step); col < Math.ceil((west + width + 180) / step); col++) {
      tiles.push(<image key={col + '/' + row} href={'/atlas/' + layer + '/' + zoom + '/' + modulo(col, cols) + '/' + row + '.webp'}
        x={x(-180 + col * step)} y={y(90 - row * step)} width={step / width * size[0] + .35} height={step / height * size[1] + .35}
        preserveAspectRatio="none" onError={() => setFailedLayers(previous => previous.includes(layer) ? previous : [...previous, layer])}/>)
    }
  }

  const same = target && Math.hypot(x(start) - x(end), y(base[1]) - y(endLat)) < 26
  const marker = (label: string, lon: number, lat: number, offset = 0) =>
    <g transform={`translate(${x(lon)} ${y(lat)})`} className="corridor-pin">
      <circle r={8}/>
      <text y={offset || -18} textAnchor="middle">{label}</text>
    </g>
  return <div className="corridor-map" ref={ref}>
    <svg viewBox={`0 0 ${size[0]} ${size[1]}`} role="img" aria-label="Mars map of the saved base and science destination">
      {tiles}
      <rect width={size[0]} height={size[1]} fill="#1d140c" opacity=".16"/>
      {showSeparation && target && !same &&
        <line className="corridor-separation" x1={x(start)} y1={y(base[1])} x2={x(end)} y2={y(endLat)}/>}
      {marker(same ? 'Base / nearby target' : 'Base', start, base[1])}
      {target && !same && marker('Science target', end, endLat)}
    </svg>
    {failedLayers.includes(layer) && <p className="corridor-imagery-warning">Some basemap tiles are unavailable.</p>}
  </div>
}
