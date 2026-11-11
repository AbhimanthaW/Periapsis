import { architectureSchema } from './schema'
import type { Architecture, Connection, Point, LayoutKey } from './schema'
import { baselineArchitecture, pipelineArchitecture, initialArchitecture } from './initial'

export const storageKey = 'return-window-blueprint/v1'
export function loadDocument(): { doc: Architecture; error: string } {
  try {
    const value = localStorage.getItem(storageKey)
    return { doc:value ? upgradeArchitecture(architectureSchema.parse(JSON.parse(value))) : initialArchitecture, error:'' }
  } catch {
    return { doc:initialArchitecture, error:'The saved document could not be opened. The default blueprint is available. Import a backup or reset to resume saving.' }
  }
}
export function renameNode(doc: Architecture, oldId: string, id: string): Architecture {
  const replace = (value: string) => value === oldId ? id : value
  return {
    ...doc,
    components:doc.components.map(node => ({
      ...node,id:replace(node.id),dependencies:node.dependencies.map(replace),
      inputs:node.inputs.map(entry => ({ ...entry,componentId:replace(entry.componentId) })),
      outputs:node.outputs.map(entry => ({ ...entry,componentId:replace(entry.componentId) })),
    })),
    connections:doc.connections.map(edge => ({ ...edge,source:replace(edge.source),target:replace(edge.target),dependencies:edge.dependencies.map(replace) })),
    decisionSteps:doc.decisionSteps.map(step => ({ ...step,componentId:replace(step.componentId) })),
    layout:Object.fromEntries(Object.entries(doc.layout).map(([view,positions]) =>
      [view,Object.fromEntries(Object.entries(positions).map(([key,point]) => [replace(key),point]))])),
  }
}
export function removeItems(doc: Architecture, nodes: string[], edges: string[]): Architecture {
  const drop = new Set(nodes), links = new Set(edges)
  const keep = (id: string) => !drop.has(id)
  const connections = doc.connections.filter(edge => !links.has(edge.id) && keep(edge.source) && keep(edge.target))
  const kept = new Set(connections.map(edge => edge.id))
  return {
    ...doc,
    components:doc.components.filter(node => keep(node.id)).map(node => ({
      ...node,dependencies:node.dependencies.filter(keep),
      inputs:node.inputs.map(entry => keep(entry.componentId) ? entry : { ...entry,componentId:'' }),
      outputs:node.outputs.map(entry => keep(entry.componentId) ? entry : { ...entry,componentId:'' }),
    })),
    connections:connections.map(edge => ({ ...edge,dependencies:edge.dependencies.filter(keep) })),
    decisionSteps:doc.decisionSteps.filter(step => keep(step.componentId)).map(step => ({ ...step,connectionIds:step.connectionIds.filter(id => kept.has(id)) })),
    layout:Object.fromEntries(Object.entries(doc.layout).map(([view,positions]) =>
      [view,Object.fromEntries(Object.entries(positions).filter(([id]) => keep(id)))])),
  }
}
export function setPositions(doc: Architecture, view: LayoutKey, positions: Record<string,Point>): Architecture {
  return { ...doc,layout:{ ...doc.layout,[view]:{ ...doc.layout[view],...positions } } }
}
export function newEdge(source: string, target: string, label: string): Connection {
  return { id:'link-' + crypto.randomUUID(), source, target, label, kind:'Data flow', payload:'', format:'', protocol:'', description:'', validation:'', dependencies:[] }
}


const same = (a: unknown,b: unknown) => JSON.stringify(a) === JSON.stringify(b)
function plain(value: unknown): value is Record<string,unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
// Three-way merge between the legacy seed, a saved document and the new seed.
function mergeDefaults<T>(old: T, current: T, next: T): T {
  if (same(old,current)) return next
  if (!plain(old) || !plain(current) || !plain(next)) return current
  return Object.fromEntries([...new Set([...Object.keys(current),...Object.keys(next)])].map(key=>
    [key,mergeDefaults(old[key],current[key],next[key])])) as T
}
function mergeRecords<T extends { id: string }>(before: T[], saved: T[], defaults: T[]): T[] {
  const old = new Map(before.map(item=>[item.id,item]))
  const next = new Map(defaults.map(item=>[item.id,item]))
  const actual = new Set(saved.map(item=>item.id))
  const kept = saved.flatMap(item=>{
    const original = old.get(item.id), revised = next.get(item.id)
    if (!original) return [item]
    if (!revised) return same(original,item) ? [] : [item]
    return [mergeDefaults(original,item,revised)]
  })
  return [...kept,...defaults.filter(item=>!old.has(item.id) && !actual.has(item.id))]
}

export function upgradePipeline(doc: Architecture): Architecture {
  const groupIds = new Set(doc.groups.map(group=>group.id))
  // Custom documents and already-upgraded exports round-trip without a seed merge.
  if (doc.pipelineRevision || !['sources','ingest','prep','pack'].every(id=>groupIds.has(id))
    || !doc.components.some(item=>['registry','terrain-file','pack-check'].includes(item.id))) return doc
  return mergeArchitecture(baselineArchitecture,doc,pipelineArchitecture,{
    pipelineRevision:1,
    viewSettings:doc.viewSettings.view === 'pipeline' ? { ...doc.viewSettings,pipelineLens:'complete',expanded:[],viewport:undefined } : doc.viewSettings,
  })
}
export function upgradeArchitecture(saved: Architecture): Architecture {
  const doc = upgradePipeline(saved)
  if (doc.modelRevision || !doc.pipelineRevision || !['routing','decision','validate'].every(id=>doc.groups.some(group=>group.id===id))) return doc
  return mergeArchitecture(pipelineArchitecture,doc,initialArchitecture,{
    modelRevision:1,
    viewSettings:doc.viewSettings.view === 'models' ? { ...doc.viewSettings,modelLens:'complete',expanded:[],viewport:undefined } : doc.viewSettings,
  })
}
function mergeArchitecture(base: Architecture,doc: Architecture,next: Architecture,revision: Partial<Architecture>): Architecture {
  const groups = mergeRecords(base.groups,doc.groups,next.groups)
  const validGroups = new Set(groups.map(group=>group.id))
  const components = mergeRecords(base.components,doc.components,next.components).map(item=>{
    if (!item.modelFamily || validGroups.has(item.modelFamily)) return item
    const { modelFamily: _missing,...rest } = item
    return rest
  })
  const validIds = new Set(components.filter(item=>validGroups.has(item.groupId)).map(item=>item.id))
  const links = mergeRecords(base.connections,doc.connections,next.connections)
  const result: Architecture = {
    ...doc,...revision,
    architectureVersion:doc.architectureVersion === base.architectureVersion ? next.architectureVersion : doc.architectureVersion,
    groups,components,connections:links,
  }
  const unavailable = [...new Set([...base.components,...next.components,...components].map(item=>item.id))].filter(id=>!validIds.has(id))
  return architectureSchema.parse(removeItems(result,unavailable,
    links.filter(link=>!validIds.has(link.source) || !validIds.has(link.target)).map(link=>link.id)))
}
