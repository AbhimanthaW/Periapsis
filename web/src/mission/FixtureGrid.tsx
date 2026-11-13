import type { Cell, FixtureSite } from './api'

type Props = {
  site: FixtureSite
  activeClosures: readonly string[]
  route: readonly Cell[] | null
  /** The service returned a path for inspection only (for example over reserve). */
  inspectOnly?: boolean
}

/** The synthetic fixture grid in its own local-metre frame. Never placed on Mars geography. */
export function FixtureGrid({ site, activeClosures, route, inspectOnly = false }: Props) {
  const [rows, cols] = site.grid.shape
  const [a, b, c, d, e, f] = site.grid.affine
  // Affine maps [col, row] (cell corner) to local metres; cell centres sit at [c+0.5, r+0.5].
  const toLocal = (col: number, row: number) => [a * col + b * row + c, d * col + e * row + f] as const
  const corners = [toLocal(0, 0), toLocal(cols, 0), toLocal(0, rows), toLocal(cols, rows)]
  const xs = corners.map(([x]) => x), ys = corners.map(([, y]) => y)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const cellSize = Math.max(Math.hypot(a, d), Math.hypot(b, e))
  const pad = cellSize * 0.6
  const screen = (x: number, y: number) => [x - minX + pad, maxY - y + pad] as const
  const point = (col: number, row: number) => screen(...toLocal(col, row))
  const centre = ([row, col]: Cell) => point(col + 0.5, row + 0.5)
  const width = maxX - minX + pad * 2, height = maxY - minY + pad * 2

  const closureCells = new Map<string, { id: string; active: boolean }>()
  for (const closure of site.closures) {
    for (const [row, col] of closure.cells) closureCells.set(`${row},${col}`, { id: closure.id, active: activeClosures.includes(closure.id) })
  }
  const polygon = (row: number, col: number) =>
    [point(col, row), point(col + 1, row), point(col + 1, row + 1), point(col, row + 1)].map(p => p.join(',')).join(' ')
  const [checkX, checkY] = centre(site.checkpoint_cell)
  const [homeX, homeY] = centre(site.shelter_cell)
  const marker = cellSize * 0.26

  return (
    <figure className="mission-grid">
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Synthetic fixture grid, ${rows} by ${cols} cells${route ? `, return route through ${route.length} cells` : ', no route shown'}`}>
        <defs>
          <pattern id="mission-hatch" width={cellSize / 5} height={cellSize / 5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2={cellSize / 5} className="mission-hatch-line"/>
          </pattern>
        </defs>
        {Array.from({ length: rows }, (_, row) => Array.from({ length: cols }, (_, col) => {
          const closure = closureCells.get(`${row},${col}`)
          return (
            <g key={`${row}-${col}`}>
              <polygon points={polygon(row, col)} className={`mission-cell${closure ? closure.active ? ' mission-cell-closed' : ' mission-cell-closable' : ''}`}/>
              {closure?.active && <polygon points={polygon(row, col)} fill="url(#mission-hatch)" className="mission-cell-hatch"/>}
              {closure && (
                <text x={centre([row, col])[0]} y={centre([row, col])[1] + cellSize * 0.36} className="mission-cell-label" textAnchor="middle">
                  {closure.id}
                </text>
              )}
            </g>
          )
        }))}
        {route && route.length > 1 && (
          <polyline data-testid="mission-route" data-inspect-only={inspectOnly} className={`mission-route${inspectOnly ? ' mission-route-inspect' : ''}`} points={route.map(cell => centre(cell).join(',')).join(' ')}/>
        )}
        <circle cx={checkX} cy={checkY} r={marker} className="mission-marker mission-marker-crew"/>
        <text x={checkX} y={checkY} className="mission-marker-text" textAnchor="middle" dominantBaseline="central">C</text>
        <circle cx={homeX} cy={homeY} r={marker} className="mission-marker mission-marker-home"/>
        <text x={homeX} y={homeY} className="mission-marker-text" textAnchor="middle" dominantBaseline="central">H</text>
      </svg>
      <figcaption>
        <span className="mission-badge">SIM</span>
        Synthetic {rows} × {cols} grid · {cellSize} m cells · local metres, not Mars coordinates · C checkpoint <code>{site.checkpoint_id}</code> · H shelter <code>{site.shelter_id}</code> · hatched cells are closed
        {route && inspectOnly && <span className="mission-fail-text">Dashed route: computed for inspection only, not recommended</span>}
      </figcaption>
    </figure>
  )
}
