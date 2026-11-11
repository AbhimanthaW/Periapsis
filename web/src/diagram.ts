import { modelChildOrder, modelFamilyNumbers, modelGuides, modelViews } from './model-layout'
import { childOrder, layoutKey, lenses, lensSummaries, pipelineNumbers, systemRepresentatives } from './pipeline-layout'
import type { PipelineRoute } from './pipeline-layout'
import type { Architecture, Component, Connection, Group, Point, ViewSettings } from './schema'

export const viewLabels = {
  system: 'Complete system', pipeline: 'Data pipeline', models: 'Scientific models',
  runtime: 'Application runtime', decision: 'Corridor closure',
}
export const viewCopy = {
  system: 'From archived Mars observations to a crew decision.',
  pipeline: 'From original assets to an immutable, validated site pack.',
  models: 'Terrain screening, directed routing, feasibility and abstention.',
  runtime: 'One same-origin application, with a local data pack and no network dependency.',
  decision: 'Follow a simulated field report through replanning and review.',
}
export type Box = Point & {
  id: string; w: number; h: number; title: string; sub: string; tone: Group['tone'];
  kind: 'group' | 'component' | 'caption'; group?: Group; component?: Component; count?: number;
  expanded?: boolean; step?: number; regionHeight?: number; groupOrigin?: Point; subsystemNumber?: string;
}
export type Link = {
  id: string; source: string; target: string; label: string; links: Connection[];
  kind: Connection['kind']; tone?: 'trace'; lane?: number; route?: PipelineRoute; hideLabel?: boolean;
}
export const groupKey = (key: string) => 'group:' + key
const systemRows = [['sources','ingest','prep','pack'],['ui','api','decision','routing'],['deploy','validate']]
const focusedRows = {
  pipeline: [['sources','ingest','prep','pack']],
  models: [['prep','routing','decision']],
  runtime: [['pack','api','ui','deploy'], ['routing','decision']],
}
const runtimeOpen = ['api','ui','deploy']
const columnPitch = 309
const groupWidth = 218
const detailW = 186
const detailH = 54
const detailPitch = 68
const headH = 90
const groupTag: Record<string,string> = { sources:'01', ingest:'02', prep:'03', pack:'04', routing:'05', decision:'06', api:'07', ui:'08', deploy:'09', validate:'10' }
export const numberFor = (id: string) => groupTag[id] ?? '—'
export const toneFor = (component: Component, group: Group): Group['tone'] => {
  if (component.classification === 'Simulation' || component.id === 'abstain') return 'constraint'
  if (component.classification === 'Decision') return 'decision'
  return group.tone
}
const backbone: [string, string, string, string?][] = [
  ['sources','ingest','archives'],['ingest','prep','validated data'],['prep','pack','artifacts'],
  ['pack','api','local pack'],
  ['routing','decision','travel times'],['decision','api','decision'],
  ['api','ui','plan result','response'],['ui','api','crew state','request'],['api','routing','terrain + state','closure'],
  ['deploy','ui','same origin'],['validate','routing','solver checks'],
]

function decideLayout(doc: Architecture, items: Component[], groups: Map<string, Group>, settings: ViewSettings) {
  const boxes: Box[] = []
  const links: Link[] = []
  const steps = doc.decisionSteps
  const visible = new Map(items.map(item => [item.id, item]))
  steps.forEach((step, index) => {
    const item = visible.get(step.componentId)
    if (!item) return
    const group = groups.get(item.groupId)!
    const row = Math.floor(index / 4)
    const col = row % 2 ? 3 - index % 4 : index % 4
    boxes.push({
      id: item.id, x: col * columnPitch, y: row * 206 + 70, w: groupWidth, h: 88,
      title: item.name, sub: item.technology.join(' · '), kind: 'component', group, component: item,
      tone: toneFor(item,group), step: index + 1, ...doc.layout.decision?.[item.id],
    })
  })
  const ids = new Set(boxes.map(box => box.id))
  const byId = new Map(doc.connections.map(edge => [edge.id, edge]))
  steps.slice(1).forEach((step, index) => {
    const prev = steps[index]
    if (!ids.has(prev.componentId) || !ids.has(step.componentId)) return
    const actual = doc.connections.filter(edge => edge.source === prev.componentId && edge.target === step.componentId)
    const backed = step.connectionIds.map(id => byId.get(id)).filter((edge): edge is Connection => Boolean(edge))
    const reached = new Set([prev.componentId])
    for (let pass = 0; pass < backed.length; pass++) {
      for (const edge of backed) if (reached.has(edge.source)) reached.add(edge.target)
    }
    if (reached.has(step.componentId) || actual.length) {
      const edges = reached.has(step.componentId) ? backed : actual
      links.push({ id: 'trace:' + step.componentId, source: prev.componentId, target: step.componentId,
        label: step.transition || edges[0].label, links: edges, kind: 'Control', tone: 'trace' })
    }
  })
  const used = new Set(links.flatMap(link => link.links.map(edge => edge.id)))
  for (const edge of doc.connections) {
    if (edge.id.startsWith('link-') && ids.has(edge.source) && ids.has(edge.target) && !used.has(edge.id)) {
      links.push({ id:edge.id,source:edge.source,target:edge.target,label:edge.label,links:[edge],kind:edge.kind,lane:1 })
    }
  }
  if (boxes.length && !settings.category && !settings.status) {
    boxes.unshift(caption('event','FIELD UPDATE',0,20),caption('outcome','REVISED DECISION',0,226))
  }
  return { boxes, links }
}
function caption(id: string, title: string, x: number, y: number): Box {
  return { id: 'caption:' + id, title, sub: '', x, y, w: 214, h: 18, kind:'caption', tone:'neutral' }
}

export function buildDiagram(doc: Architecture, settings: ViewSettings) {
  const groups = new Map(doc.groups.map(group => [group.id, group]))
  const items = doc.components.filter(item => (!settings.category || item.category === settings.category) && (!settings.status || item.status === settings.status))
  const onlyMatches = Boolean(settings.category || settings.status)
  if (settings.view === 'decision' && !settings.focus) return decideLayout(doc, items, groups, settings)
  const pipeline = Boolean(settings.view === 'pipeline' && doc.pipelineRevision)
  const models = Boolean(settings.view === 'models' && doc.modelRevision)
  const sectioned = pipeline || models
  const lens = settings.pipelineLens ?? 'complete'
  const modelLens = settings.modelLens ?? 'complete'
  const allLinks = models ? settings.modelAllLinks : settings.pipelineAllLinks
  const complete = (pipeline && lens === 'complete' || models && modelLens === 'complete') && !settings.focus && !onlyMatches
  const collapsedPipeline = pipeline && complete && !settings.expanded.length
  const guide = sectioned && !settings.focus && !onlyMatches ? models ? modelGuides[modelLens] : lensSummaries[lens] : undefined
  const byGroup = Map.groupBy(items, item => models ? item.modelFamily ?? item.groupId : item.groupId)
  const membership = new Map(items.map(item => [item.id,item.groupId]))
  const projectedGroups = doc.pipelineRevision && !models && !settings.focus && settings.view === 'models' ? { terrain:'prep',spatial:'prep' } : {}
  for (const [id, target] of Object.entries(projectedGroups)) {
    const moved = byGroup.get(id) ?? []
    byGroup.set(target!,[...(byGroup.get(target!) ?? []),...moved])
  }
  const rows = settings.focus ? [[settings.focus]] : settings.view === 'system' ? systemRows :
    settings.view === 'decision' ? [] : pipeline ? lenses[lens].rows : models ? modelViews[modelLens].rows : focusedRows[settings.view]
  const unknown = settings.view === 'system' && !settings.focus ?
    doc.groups.filter(group => !rows.flat().includes(group.id) && !(doc.pipelineRevision && systemRepresentatives[group.id]) && !(doc.modelRevision && modelFamilyNumbers[group.id])).map(group => group.id) : []
  const layoutRows = [...rows, ...Array.from({ length: Math.ceil(unknown.length / 4) }, (_,i) => unknown.slice(i * 4, i * 4 + 4))]
  const positions = doc.layout[layoutKey(settings,doc.pipelineRevision,doc.modelRevision)] ?? {}
  const boxes: Box[] = []
  const endpoint = new Map<string, string>()
  const groupOfEndpoint = new Map<string,string>()
  const detailed = new Set<string>()
  const collapsedSystem = settings.view === 'system' && !settings.focus && !settings.expanded.length && !onlyMatches
  const isExpanded = (id: string) => Boolean(settings.focus || onlyMatches || settings.expanded.includes(id))
  const numberOfColumns = (id: string) => sectioned && isExpanded(id) && (byGroup.get(id)?.length ?? 0) >= 10 ? 2 : 1
  const widthOf = (id: string) => groupWidth + (numberOfColumns(id)-1)*(detailW+18)
  const pipelineColumnStarts: number[] = []
  const pipelineColumnY: number[] = []
  const pipelineWidths: number[] = []
  if (sectioned) {
    for (const row of layoutRows) row.forEach((id,i)=>{ if (id) pipelineWidths[i] = Math.max(pipelineWidths[i] ?? groupWidth,widthOf(id)) })
    let next = 0
    for (let i=0; i<pipelineWidths.length; i++) {
      pipelineColumnStarts[i] = next
      next += (pipelineWidths[i] ?? groupWidth) + (complete ? 65 : 104)
    }
  }
  let y = sectioned ? 48 : 58
  for (const [rowIndex, row] of layoutRows.entries()) {
    if (collapsedSystem && rowIndex < 3) boxes.push(caption(String(rowIndex), ['OFFLINE DATA BUILD','OFFLINE-CAPABLE RUNTIME','DEPLOYMENT & ASSURANCE'][rowIndex], 0, y - 30))
    if (collapsedPipeline) boxes.push(caption('pipeline-'+rowIndex,['REGIONAL SCIENCE','PLANETARY DATA','TERRAIN & RELEASE'][rowIndex],0,y-25))
    if (models && complete && !settings.expanded.length) boxes.push(caption('model-row-'+rowIndex,['INPUTS & EVIDENCE','MOBILITY & ROUTING','MISSION DECISION'][rowIndex],0,y-25))
    let rowHeight = headH
    row.forEach((id, col) => {
      if (!id) return
      const group = groups.get(id)
      const unordered = byGroup.get(id) ?? []
      const order = (pipeline ? childOrder[id] : models ? modelChildOrder[id] : undefined) ?? []
      const index = (key: string) => order.includes(key) ? order.indexOf(key) : order.length
      const children = order.length ? [...unordered].sort((a,b)=>index(a.id)-index(b.id)) : unordered
      if (!group || (onlyMatches && !children.length)) return
      const key = groupKey(id)
      const x = sectioned ? pipelineColumnStarts[col] : (rowIndex === 2 && collapsedSystem ? col + 1 : col) * columnPitch
      const origin = positions[key] ?? { x, y: sectioned && !complete ? pipelineColumnY[col] ?? 48 : y }
      const expanded = isExpanded(id)
      const columns = numberOfColumns(id)
      const rowsPerColumn = Math.ceil(children.length/columns)
      const localPositions = children.map((item,i) => positions[item.id] ?? {
        x:16 + Math.floor(i/rowsPerColumn)*(detailW+18),
        y:65 + (i%rowsPerColumn)*detailPitch,
      })
      const height = expanded ? Math.max(106, ...localPositions.map(pos => pos.y + detailH + 16)) : headH
      const width = sectioned ? widthOf(id) : groupWidth
      boxes.push({ id:key, ...origin, w:width, h:expanded ? 50 : headH, title:group.name, sub:group.summary,
        tone:group.tone, kind:'group', group, count:children.length, expanded, regionHeight:height, subsystemNumber:pipeline ? pipelineNumbers[id] ?? (group.phase === 'runtime' ? 'runtime' : undefined) : models ? modelFamilyNumbers[id] : undefined })
      rowHeight = Math.max(rowHeight,height)
      if (sectioned && !complete) pipelineColumnY[col] = (pipelineColumnY[col] ?? 48) + height + 92
      children.forEach((item, i) => {
        endpoint.set(item.id, expanded ? item.id : key)
        groupOfEndpoint.set(item.id,key)
        if (!expanded) return
        detailed.add(item.id)
        const pos = localPositions[i]
        boxes.push({
          id:item.id, x:origin.x + pos.x, y:origin.y + pos.y, w:detailW, h:detailH, title:item.name,
          sub:item.gate?.result ?? (item.technology.join(' · ') || item.category), kind:'component', group, component:item,
          tone:toneFor(item,group), groupOrigin:origin,
        })
      })
    })
    y += rowHeight + (sectioned ? complete ? 95 : 83 : rowIndex === 0 && collapsedSystem ? 116 : 96)
  }
  if (doc.pipelineRevision && settings.view === 'system' && !settings.focus && !onlyMatches) {
    const present = new Set(boxes.map(box=>box.id))
    for (const item of items) {
      const alias = systemRepresentatives[item.groupId]
      if (!endpoint.has(item.id) && alias && present.has(groupKey(alias))) {
        endpoint.set(item.id,groupKey(alias))
        membership.set(item.id,alias)
      }
    }
  }

  const pairs = new Map<string, Connection[]>()
  for (const edge of doc.connections) {
    if (models && edge.scope === 'Jezero reference') continue
    let source = endpoint.get(edge.source), target = endpoint.get(edge.target)
    if (!source || !target || source === target) continue
    const a = groupOfEndpoint.get(edge.source), b = groupOfEndpoint.get(edge.target)
    if (sectioned && a && b && a !== b && (!detailed.has(source) || !detailed.has(target))) {
      source = a; target = b
    }
    const key = source + '>' + target
    const pair = pairs.get(key)
    if (pair) pair.push(edge)
    else pairs.set(key,[edge])
  }
  const links: Link[] = []
  for (const [key, entries] of pairs) {
    const [source,target] = key.split('>')
    const a = membership.get(entries[0].source), b = membership.get(entries[0].target)
    const preset = backbone.find(([from,to]) => from === a && to === b)
    if (collapsedSystem && !preset && entries.every(edge => !edge.id.startsWith('link-'))) continue
    const groupPair = source.startsWith('group:') && target.startsWith('group:')
    const pipelinePreset = guide && groupPair ? guide[source.slice(6)+'>'+target.slice(6)] : undefined
    if (guide && groupPair && !pipelinePreset && !allLinks && entries.every(edge=>!edge.id.startsWith('link-'))) continue
    const isDirect = detailed.has(source) && detailed.has(target)
    const grouped = !isDirect && (entries.length > 1 || collapsedSystem || (sectioned && groupPair))
    if (grouped) {
      links.push({ id:'bundle:' + key, source, target, label:pipelinePreset?.label ?? preset?.[2] ?? entries[0].label, kind:pipelinePreset?.kind ?? entries[0].kind, links:entries, route:pipelinePreset?.route, hideLabel:Boolean(guide && !pipelinePreset && !entries.some(edge=>edge.id.startsWith('link-'))) })
    } else entries.forEach((entry,i) => links.push({ id:entry.id, source, target, label:entry.label, kind:entry.kind, links:[entry], lane:i }))
  }
  return { boxes, links }
}

export function switchSettings(settings: ViewSettings, view: ViewSettings['view'], revision?: number, modelRevision?: number): ViewSettings {
  return { ...settings, view, focus:'', viewport:undefined, expanded: view === 'pipeline' ? (revision ? lenses[settings.pipelineLens ?? 'complete'].open : ['sources','ingest','prep','pack']) :
    view === 'models' ? (modelRevision ? modelViews[settings.modelLens ?? 'complete'].open : ['prep','routing','decision']) : view === 'runtime' ? runtimeOpen : [] }
}

export function curve(link: Link, a: Box, b: Box, dual: boolean) {
  const cx = (n:Box) => n.x + n.w / 2
  const cy = (n:Box) => n.y + n.h / 2
  const dx = cx(b) - cx(a), dy = cy(b) - cy(a)
  const offset = ((link.lane ?? 0) * 8) % 24
  if (link.route === 'left-gutter' || link.route === 'right-gutter') {
    const sign = link.route === 'left-gutter' ? -1 : 1
    const from = sign < 0 ? a.x : a.x+a.w
    const to = sign < 0 ? b.x : b.x+b.w
    const x = (sign < 0 ? Math.min(from,to) : Math.max(from,to)) + 27*sign
    const y1 = cy(a), y2 = cy(b)
    const bend = Math.min(8,Math.abs(y2-y1)/4)*(Math.sign(y2-y1)||1)
    return { d:`M ${from},${y1} H ${x-8*sign} Q ${x},${y1} ${x},${y1+bend} V ${y2-bend} Q ${x},${y2} ${x-8*sign},${y2} H ${to}`,x,y:y1+(y2-y1)*.27 }
  }
  if (link.route === 'above') {
    const x1 = cx(a), x2 = cx(b), y = Math.min(a.y,b.y)-28
    const bend = Math.min(8,Math.abs(x2-x1)/3)*(Math.sign(x2-x1)||1)
    return {d:`M ${x1},${a.y} V ${y+8} Q ${x1},${y} ${x1+bend},${y} H ${x2-bend} Q ${x2},${y} ${x2},${y+8} V ${b.y}`,x:(x1+x2)/2,y:y-10}
  }
  const sameCol = Math.abs(dx) < 56
  const groupToGroup = a.kind === 'group' && b.kind === 'group'
  const skipDown = groupToGroup && a.group?.id === 'pack' && b.group?.id === 'api' && dy > 0
  const closureBack = groupToGroup && a.group?.id === 'api' && b.group?.id === 'routing' && Math.abs(dy) < 40
  const assurance = groupToGroup && a.group?.phase === 'assurance' && b.group?.phase === 'runtime' && dy < 0
  const vertical = sameCol || skipDown || closureBack || assurance
  const sign = vertical ? Math.sign(dy) || 1 : Math.sign(dx) || 1
  if (skipDown || closureBack || assurance) {
    const x1 = cx(a), x2 = cx(b)
    const y1 = a.y
    const y2 = closureBack ? b.y : skipDown ? b.y : b.y + b.h
    const elbow = closureBack ? a.y - 42 : skipDown ? a.y + a.h + 40 : a.y - (b.group?.id === 'routing' ? 26 : 38)
    const start = skipDown ? a.y + a.h : y1
    const bend = Math.min(14,Math.abs(x2-x1)/4)
    const hsign = Math.sign(x2-x1) || 1
    const first = Math.sign(elbow-start) || 1, last = Math.sign(y2-elbow) || 1
    return { d:`M ${x1},${start} V ${elbow-first*bend} Q ${x1},${elbow} ${x1+hsign*bend},${elbow} H ${x2-hsign*bend} Q ${x2},${elbow} ${x2},${elbow+last*bend} V ${y2}`, x:(x1+x2)/2, y:elbow-10 }
  }
  const loop = sameCol && Math.abs(dy) > 110 && a.kind === 'component' && b.kind === 'component' && a.group?.id === b.group?.id && !link.tone
  if (loop) {
    const direction = dy > 0 ? 1 : -1
    const x1 = direction > 0 ? a.x+a.w : a.x
    const x2 = direction > 0 ? b.x+b.w : b.x
    const x = (direction > 0 ? Math.max(x1,x2) : Math.min(x1,x2)) + direction * (25 + offset)
    return { d:`M ${x1},${cy(a)} C ${x},${cy(a)} ${x},${cy(b)} ${x2},${cy(b)}`, x, y:(cy(a)+cy(b))/2 }
  }
  const x1 = vertical ? cx(a)+offset : sign > 0 ? a.x+a.w : a.x
  const x2 = vertical ? cx(b)+offset : sign > 0 ? b.x : b.x+b.w
  const y1 = vertical ? sign > 0 ? a.y+a.h : a.y : cy(a) + (dual ? sign*16 : 0) + offset
  const y2 = vertical ? sign > 0 ? b.y : b.y+b.h : cy(b) + (dual ? sign*16 : 0) + offset
  const x = (x1+x2)/2, y = (y1+y2)/2
  const label = vertical ? { x:x+43,y } : { x,y:y-11 }
  return { d: vertical ? `M ${x1},${y1} C ${x1},${y} ${x2},${y} ${x2},${y2}` : `M ${x1},${y1} C ${x},${y1} ${x},${y2} ${x2},${y2}`, ...label }
}
