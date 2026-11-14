import type { Profile, Region } from './regions'

export const missionHref = (screen: string, profile: Profile, region: Region, view = '') =>
  '#' + screen + '/' + profile.toLowerCase() + '/' + region.id + (view ? '/' + view : '')

export interface MissionRevision {
  number: number
  run: string
  change: string
  decision: string
  route: string
  task: string
}

export interface MissionState {
  rover: string
  roverSettings?: Record<string, string>
  task: string
  route: string
  plan: string
  closure: string
  decision: string
  revision: number
  history: MissionRevision[]
  writeTrace: boolean
}
export const initialMission: MissionState = {
  rover: 'LR-1', task: 'Delta front', route: 'A', plan: 'R-012', closure: '', decision: '', revision: 3, history: [], writeTrace: true,
}
export interface MissionProps {
  region: Region
  profile: Profile
  objective: string
  terms: string[]
  view: string
  mission: MissionState
  update: (change: Partial<MissionState>) => void
  go: (screen: string, view?: string, profile?: Profile) => void
}
