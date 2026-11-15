import { useEffect, useRef, useState } from 'react'
import type { PointerEvent } from 'react'

export type Point = [number, number]
export type Layer = 'viking' | 'mola'
const radians = Math.PI / 180
const wrapLongitude = (value: number) => ((value + 540) % 360) - 180
const limitLatitude = (value: number) => Math.max(-90, Math.min(90, value))

function coordinates(x: number, y: number, diameter: number, center: Point, zoom: number): Point | null {
  const east = (2 * x / diameter - 1) / zoom
  const north = (1 - 2 * y / diameter) / zoom
  const depth = 1 - east * east - north * north
  if (depth < 0) return null
  const front = Math.sqrt(depth)
  const latitude = center[1] * radians
  return [
    wrapLongitude(center[0] + Math.atan2(east, front * Math.cos(latitude) - north * Math.sin(latitude)) / radians),
    Math.asin(Math.max(-1, Math.min(1, front * Math.sin(latitude) + north * Math.cos(latitude)))) / radians,
  ]
}

function screenPosition(point: Point, center: Point, size: number, zoom: number): Point | null {
  const lon = (point[0] - center[0]) * radians
  const lat = point[1] * radians
  const tilt = center[1] * radians
  const front = Math.sin(lat) * Math.sin(tilt) + Math.cos(lat) * Math.cos(lon) * Math.cos(tilt)
  if (front < 0) return null
  return [
    size / 2 * (1 + zoom * Math.cos(lat) * Math.sin(lon)),
    size / 2 * (1 - zoom * (Math.sin(lat) * Math.cos(tilt) - Math.cos(lat) * Math.cos(lon) * Math.sin(tilt))),
  ]
}

function loadMosaic(layer: Layer) {
  const canvas = document.createElement('canvas')
  canvas.width = 1024
  canvas.height = 512
  const context = canvas.getContext('2d')!
  return Promise.all(Array.from({ length: 8 }, (_, index) => new Promise<void>((resolve, reject) => {
    const image = new Image()
    const col = index % 4
    const row = Math.floor(index / 4)
    image.onload = () => { context.drawImage(image, col * 256, row * 256); resolve() }
    image.onerror = reject
    image.src = '/atlas/' + layer + '/1/' + col + '/' + row + '.webp'
  }))).then(() => context.getImageData(0, 0, canvas.width, canvas.height))
}

const size = 400
export function Globe({ center, setCenter, layer, selected, base, pick }: {
  center: Point; setCenter: (value: Point) => void; layer: Layer
  selected?: Point; base?: Point; pick: (point: Point) => void
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const gesture = useRef<{ start: Point; last: Point; moved: boolean } | null>(null)
  const [mosaic, setMosaic] = useState<{ layer: Layer; image: ImageData } | null>(null)
  const [failed, setFailed] = useState<Layer | null>(null)
  const [zoom, setZoom] = useState(1)
  const magnify = (step: number) => setZoom(value => Math.min(4, Math.max(1, value + step)))

  useEffect(() => {
    let active = true
    loadMosaic(layer).then(image => { if (active) setMosaic({ layer, image }) }, () => { if (active) setFailed(layer) })
    return () => { active = false }
  }, [layer])

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx) return
    const frame = requestAnimationFrame(() => {
      ctx.clearRect(0, 0, size, size)
      if (mosaic?.layer !== layer) return
      const source = mosaic.image
      const bitmap = ctx.createImageData(size, size)
      const latitude = center[1] * radians
      const sine = Math.sin(latitude)
      const cosine = Math.cos(latitude)
      for (let row = 0; row < size; row++) {
        const north = (1 - (2 * row + 1) / size) / zoom
        for (let col = 0; col < size; col++) {
          const east = ((2 * col + 1) / size - 1) / zoom
          const depth = 1 - east * east - north * north
          if (depth < 0) continue
          const front = Math.sqrt(depth)
          const lon = wrapLongitude(center[0] + Math.atan2(east, front * cosine - north * sine) / radians)
          const lat = Math.asin(Math.max(-1, Math.min(1, front * sine + north * cosine))) / radians
          const sx = Math.min(source.width - 1, Math.floor((lon + 180) * source.width / 360))
          const sy = Math.min(source.height - 1, Math.floor((90 - lat) * source.height / 180))
          const input = 4 * (sy * source.width + sx)
          const output = 4 * (row * size + col)
          bitmap.data[output] = source.data[input]
          bitmap.data[output + 1] = source.data[input + 1]
          bitmap.data[output + 2] = source.data[input + 2]
          bitmap.data[output + 3] = 255
        }
      }
      ctx.putImageData(bitmap, 0, 0)
      for (const [point, color] of [[selected, '#ffffff'], [base, '#ff9f60']] as const) {
        const position = point && screenPosition(point, center, size, zoom)
        if (!position) continue
        ctx.beginPath()
        ctx.arc(...position, color === '#ffffff' ? 7 : 4, 0, 2 * Math.PI)
        ctx.strokeStyle = color
        ctx.lineWidth = 3
        ctx.stroke()
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [mosaic, layer, center, zoom, selected, base])

  function position(event: PointerEvent<HTMLCanvasElement>): Point {
    const box = event.currentTarget.getBoundingClientRect()
    return [(event.clientX - box.left) * size / box.width, (event.clientY - box.top) * size / box.height]
  }
  const rotate = (dx: number, dy: number) => setCenter([wrapLongitude(center[0] + dx), limitLatitude(center[1] + dy)])
  return <div className="cell-globe">
    <canvas ref={canvas} width={size} height={size} tabIndex={0} aria-label="Mars globe. Arrow keys rotate. Enter selects the centre."
      onPointerDown={event => {
        if (event.button !== 0 || gesture.current) return
        const point = position(event)
        gesture.current = { start: point, last: point, moved: false }
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onPointerMove={event => {
        const drag = gesture.current
        if (!drag) return
        const point = position(event)
        if (Math.hypot(point[0] - drag.start[0], point[1] - drag.start[1]) > 4) drag.moved = true
        if (drag.moved) rotate((drag.last[0] - point[0]) * .35 / zoom, (point[1] - drag.last[1]) * .35 / zoom)
        drag.last = point
      }}
      onPointerUp={event => {
        const drag = gesture.current
        gesture.current = null
        if (!drag || drag.moved) return
        const point = coordinates(...position(event), size, center, zoom)
        if (point) pick(point)
      }}
      onPointerCancel={() => { gesture.current = null }}
      onKeyDown={event => {
        const actions: Record<string, () => void> = {
          ArrowLeft: () => rotate(-8, 0), ArrowRight: () => rotate(8, 0),
          ArrowUp: () => rotate(0, 8), ArrowDown: () => rotate(0, -8),
          '+': () => magnify(.25), '-': () => magnify(-.25), Enter: () => pick(center),
        }
        const action = actions[event.key]
        if (action) { event.preventDefault(); action() }
      }}/>
    {failed === layer && mosaic?.layer !== layer && <p role="alert">Basemap assets unavailable. Cell lookup is still available.</p>}
    <div className="cell-toolbar" aria-label="Globe controls">
      <button onClick={() => magnify(.25)} aria-label="Zoom in">+</button>
      <button onClick={() => magnify(-.25)} aria-label="Zoom out">−</button>
      <button onClick={() => { setCenter([0, 0]); setZoom(1) }}>Reset globe</button>
      <button onClick={() => pick(center)}>Select globe centre</button>
    </div>
  </div>
}
