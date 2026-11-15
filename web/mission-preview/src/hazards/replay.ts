import { useEffect, useReducer } from 'react'
import data from './replay.json'

export type Platform = 'human' | 'rover'
export type Cell = [row: number, column: number]
export type Span = [row: number, column: number, count: number]
export type RouteId = 'A' | 'B'

export interface RouteAssessment {
  id: RouteId
  cells: Cell[]
  distance_m: number | null
  seconds: number | null
  margin_s: number | null
  energy_margin_wh: number | null
  exposure_m: number
  status: 'blocked' | 'infeasible' | 'feasible'
  reasons: string[]
  checks: { id: string; status: string; reason: string }[]
  crew: { class: string; reason: string | null; margin_s: number | null } | null
}

type ForecastRow = {
  target: string
  label: string
  unit: string
  horizon: string
  valid_utc: string
  p10: number
  p50: number
  p90: number
  status: 'model' | 'climatology' | 'abstained'
  kit: string
  reason: string | null
  track_record: { n: number | null; coverage_p10_p90: number | null }
}
type Forecast = { status: 'unavailable'; reason: string } | {
  status: 'issued'
  model_id: string
  provenance: 'simulated'
  issued_utc: string
  station: { name: string; lat_deg: number; lon_east_deg: number }
  latest: Record<string, { value: number; time_utc: string }>
  sensors_fresh: string[]
  rows: ForecastRow[]
}

export interface Frame {
  schema_version: 1
  scenario_id: string
  index: number
  time_utc: string
  elapsed_s: number
  detail: string
  extent: 'clear' | 'edge' | 'closed' | 'stale'
  footprint: Span[]
  weather: {
    value: number
    observed_utc: string
    age_s: number
    status: 'nominal' | 'caution' | 'warning' | 'stale'
    freshness_limit_s: number
    caution: number
    warning: number
    solar_disabled: boolean
    provenance: 'simulated'
  }
  forecast: Forecast
  routes: Record<Platform, RouteAssessment[]>
}

// The checked-in wire bundle is emitted and verified by runtime.hazards.replay.
const frames = data.frames as unknown as Frame[]
export const terrain = data.terrain as typeof data.terrain & {
  shape: [number, number]; start: Cell; shelter: Cell; elevation: Span[][]; excluded: Span[]; unknown: Span[]
}
export const archive = data.archive

interface Decision {
  frame: number
  time: string
  route: RouteId
  kind: 'Approved' | 'Hold position'
}

interface OperatorState {
  active: RouteId
  holding: boolean
  history: Decision[]
}

interface ReplayState {
  frame: Frame
  playing: boolean
  operators: Record<Platform, OperatorState>
  source: 'bundled' | 'runtime' | 'fallback'
}

type Action = { type: 'play' } | { type: 'advance'; from: number } | { type: 'restart' }
  | { type: 'approve' | 'hold'; platform: Platform; frame: Frame; route: RouteId }
  | { type: 'received'; index: number; frame: Frame | null }

const runtimeEnabled = import.meta.env.VITE_HAZARD_RUNTIME === '1'
export const playbackIntervalMs = 10_000

function initialState(): ReplayState {
  return {
    frame: frames[0], playing: false, source: 'bundled',
    operators: {
      rover: { active: 'A', holding: false, history: [] },
      human: { active: 'A', holding: false, history: [] },
    },
  }
}

export function recommendation(frame: Frame, platform: Platform, activeId: RouteId) {
  const [active, other] = frame.routes[platform][0].id === activeId
    ? frame.routes[platform] : [...frame.routes[platform]].reverse()
  if (frame.weather.status === 'stale' || other.status !== 'feasible') return null
  if (active.status !== 'feasible') return other.id
  // A caution can prompt review when a different corridor removes material
  // exposure. This simulation policy does not infer a travel penalty or safety probability.
  if (frame.weather.status === 'caution' && active.exposure_m - other.exposure_m >= 20) return other.id
  return null
}

function reducer(state: ReplayState, action: Action): ReplayState {
  switch (action.type) {
    case 'play':
      return state.frame.index === frames.length - 1 ? state : { ...state, playing: !state.playing }
    case 'restart':
      return initialState()
    case 'advance': {
      if (action.from !== state.frame.index || action.from >= frames.length - 1) return state
      const index = action.from + 1
      return { ...state, frame: frames[index], source: 'bundled', playing: state.playing && index < frames.length - 1 }
    }
    case 'received':
      if (action.index !== state.frame.index) return state
      return action.frame ? { ...state, frame: action.frame, source: 'runtime' } : { ...state, source: 'fallback' }
    case 'approve':
    case 'hold': {
      if (action.frame !== state.frame) return state
      const operator = state.operators[action.platform]
      const holding = action.type === 'hold'
      const route = holding ? operator.active : action.route
      const candidate = state.frame.routes[action.platform].find(item => item.id === route)
      if (holding && operator.holding) return state
      if (!holding && (state.frame.weather.status === 'stale' || candidate?.status !== 'feasible'
        || (!operator.holding && route === operator.active))) return state
      const history = [...operator.history, {
        frame: state.frame.index, time: state.frame.time_utc, route, kind: holding ? 'Hold position' : 'Approved',
      } satisfies Decision]
      return { ...state, operators: { ...state.operators, [action.platform]: { active: route, holding, history } } }
    }
  }
}

function compatibleFrame(value: Frame, offline: Frame): boolean {
  // The bundled frame defines the exact replay exercise, geometry and approval inputs.
  // Refuse drifting servers rather than combine a new route with an old local grid.
  if (value?.schema_version !== 1 || value.scenario_id !== offline.scenario_id || value.index !== offline.index) return false
  const { forecast, ...routeInputs } = value
  const { forecast: bundledForecast, ...bundledInputs } = offline
  const forecastOkay = forecast?.status === 'unavailable' && typeof forecast.reason === 'string'
    || forecast?.status === 'issued' && bundledForecast.status === 'issued'
      && JSON.stringify(forecast) === JSON.stringify(bundledForecast)
  return forecastOkay && JSON.stringify(routeInputs) === JSON.stringify(bundledInputs)
}

export function useHazardReplay(enabled: boolean) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState)
  const index = state.frame.index

  useEffect(() => {
    if (!state.playing) return
    const timer = window.setTimeout(() => dispatch({ type: 'advance', from: index }), playbackIntervalMs)
    return () => window.clearTimeout(timer)
  }, [state.playing, index])

  useEffect(() => {
    if (!enabled || !runtimeEnabled) return
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 3500)
    let current = true
    async function refresh() {
      try {
        const response = await fetch('/api/v1/hazard-replay/' + index, {
          headers: { Accept: 'application/json' }, signal: controller.signal, cache: 'no-store',
        })
        if (!response.ok) throw new Error('Replay frame unavailable')
        const frame = await response.json() as Frame
        if (!compatibleFrame(frame, frames[index])) throw new Error('Replay frame mismatch')
        if (current) dispatch({ type: 'received', index, frame })
      } catch {
        if (current) dispatch({ type: 'received', index, frame: null })
      } finally {
        window.clearTimeout(timeout)
      }
    }
    void refresh()
    return () => {
      current = false
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [enabled, index])

  return {
    ...state,
    complete: index === frames.length - 1,
    count: frames.length,
    toggle: () => dispatch({ type: 'play' }),
    advance: () => dispatch({ type: 'advance', from: index }),
    restart: () => dispatch({ type: 'restart' }),
    decide: (platform: Platform, route: RouteId, hold = false) =>
      dispatch({ type: hold ? 'hold' : 'approve', platform, frame: state.frame, route }),
  }
}

export type HazardReplay = ReturnType<typeof useHazardReplay>
