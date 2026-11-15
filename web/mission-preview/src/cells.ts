import type { Exclusion, Method } from './regions'

export const CELL_COUNT = 196_608
export const JEZERO_ANCHOR = 'HPX128:96506'
export type Point = [longitude: number, latitude: number]
export type GridCell = { id: string; centroid: Point; area_km2: number; nside: 128 }
export type CellSelection = { id: string; label?: string; markerId?: string }
export type MarsBase = { coordinates: Point; cell: GridCell }
type Axis = { tier: string; bounds: { lower: number; upper: number } }
export type CellContext = {
  cell: GridCell
  evidence_site_id: string | null
  cell_context: null | {
    pack: { version: string }
    terrain: Axis
    science_environment: Axis
    mola_elevation_m: number | null
    mola_observation_count: number | null
    stereo_topography: { status: string; observed_fraction: number; usable_fraction: number }
  }
}
type Concept = { id: string; included?: boolean }
export type RankedArea = {
  rank: number
  best_cell: string
  tier: 'Direct' | 'Partial' | 'Thematic'
  match_best: number
  concepts: Record<string, { state: string; relation: 'exact' | 'broader'; broader_support?: number }>
  records: Record<'ctx' | 'hirise' | 'dtm' | 'crism', number>
  method: 'compatible' | 'not established'
  sparse: boolean
  label: string | null
  terrain_screening?: { score: number | null; evaluated_cells: number; total_cells: number }
}
export type RankResult = {
  schema_version: 1
  request_id: string
  pack: { version: string; demo_enabled: boolean }
  parse: { concepts: Concept[]; unsupported: Concept[]; demo: Concept[]; negated: Concept[]; unknown: string[] }
  abstain: boolean
  areas: RankedArea[]
  counts: { direct_cells: number; partial_cells: number; thematic_cells: number; excluded: Record<string, number> }
}
export const cellSorts = ['Match', 'Records', 'Terrain'] as const
export type CellSort = (typeof cellSorts)[number]
export type RankingState = { status: 'idle' | 'loading' | 'ready' | 'error'; result?: RankResult; error?: string }

export function isCellId(value: unknown): value is string {
  return typeof value === 'string' && /^HPX128:(0|[1-9]\d{0,5})$/.test(value) && Number(value.slice(7)) < CELL_COUNT
}

export function formatPoint([lon, lat]: Point, decimals = 2) {
  const signed = lon > 180 ? lon - 360 : lon
  return `${Math.abs(lat).toFixed(decimals)}°${lat < 0 ? 'S' : 'N'} ${Math.abs(signed).toFixed(decimals)}°${signed < 0 ? 'W' : 'E'}`
}

export function indicatorPoint(coords: string): Point | undefined {
  const match = /^(\d+(?:\.\d+)?)°([NS]) (\d+(?:\.\d+)?)°([EW])$/.exec(coords)
  if (match) return [Number(match[3]) * (match[4] === 'W' ? -1 : 1), Number(match[1]) * (match[2] === 'S' ? -1 : 1)]
}

export function coordinates(lat: string, lon: string): Point | undefined {
  const values = [lat, lon].map(value => value.trim().replace(/^−/, '-'))
  if (!values.every(value => /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value))) return
  const [latitude, longitude] = values.map(Number)
  if (Math.abs(latitude) > 90 || longitude < -180 || longitude > 360) return
  return [longitude >= 180 ? longitude - 360 : longitude, latitude]
}

export function distanceFromBase(base: Point, destination: Point) {
  const rad = Math.PI / 180
  const [aLon, aLat] = base
  const [bLon, bLat] = destination
  const a = Math.sin((bLat - aLat) * rad / 2) ** 2
    + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin((bLon - aLon) * rad / 2) ** 2
  return 2 * 3389.5 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))))
}

const methodIds: Record<Method, string> = {
  'Sample rock': 'sample-rock', 'Investigate ice': 'investigate-ice', 'Remote survey': 'remote-survey',
}

async function request<T>(path: string, signal: AbortSignal, body?: object): Promise<T> {
  const response = await fetch(path, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
    ...(body && { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    const failure = await response.json().catch(() => null)
    throw new Error(failure?.message ?? `Cell service unavailable (HTTP ${response.status}).`)
  }
  return response.json()
}

export async function rankCells(objective: string, method: Method, exclude: Exclusion[], signal: AbortSignal) {
  const request_id = crypto.randomUUID()
  const result = await request<RankResult>('/api/v1/rank', signal, {
    schema_version: 1, request_id, objective, method: methodIds[method],
    exclude: exclude.map(item => item.toLowerCase()), limit: 20, include_demo: false,
  })
  if (result.schema_version !== 1 || result.request_id !== request_id || result.pack?.demo_enabled !== false
    || !Array.isArray(result.areas) || !result.areas.every(area => isCellId(area.best_cell))
    || !result.parse || !result.counts) throw new Error('The cell service returned an invalid ranking.')
  return result
}

function validCell(cell: GridCell, id?: string) {
  return cell?.nside === 128 && isCellId(cell.id) && (!id || cell.id === id)
    && Array.isArray(cell.centroid) && cell.centroid.length === 2 && cell.centroid.every(Number.isFinite)
    && Math.abs(cell.centroid[0]) <= 360 && Math.abs(cell.centroid[1]) <= 90
    && Number.isFinite(cell.area_km2) && cell.area_km2 > 0
}

export async function locateCell([lon, lat]: Point, signal: AbortSignal) {
  const cell = await request<GridCell>('/api/v1/cell-at?' + new URLSearchParams({ lon: String(lon), lat: String(lat) }), signal)
  if (!validCell(cell)) throw new Error('The cell service returned invalid coordinates.')
  return cell
}

export async function getCell(id: string, signal: AbortSignal) {
  const data = await request<CellContext>('/api/v1/cell-context/' + encodeURIComponent(id), signal)
  if (!validCell(data.cell, id)) throw new Error('The cell service returned a different cell.')
  return data
}

export const cellHref = (id: string) => '#cell/' + id
export const areaLabel = (area: RankedArea) => area.label ?? area.best_cell
export const conceptLabel = (id: string) => id.replace(/-/g, ' ')
export const recordsTotal = (area: RankedArea) => Object.values(area.records).reduce((sum, count) => sum + count, 0)

export function orderedAreas(areas: RankedArea[], sort: CellSort) {
  return [...areas].sort((a, b) => {
    const difference = sort === 'Records' ? recordsTotal(b) - recordsTotal(a)
      : sort === 'Terrain' ? (a.terrain_screening?.score ?? Infinity) - (b.terrain_screening?.score ?? Infinity)
      : 0
    return difference || a.rank - b.rank
  })
}

export function initialBase(): MarsBase | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem('rw-mars-base') ?? 'null')
    if (value && validCell(value.cell) && Array.isArray(value.coordinates) && value.coordinates.length === 2
      && value.coordinates.every(Number.isFinite) && coordinates(String(value.coordinates[1]), String(value.coordinates[0]))) return value
  } catch { /* Storage is optional. */ }
}

export function persistBase(base: MarsBase | undefined) {
  try {
    if (base) sessionStorage.setItem('rw-mars-base', JSON.stringify(base))
    else sessionStorage.removeItem('rw-mars-base')
  } catch { /* In-memory state remains available. */ }
}
