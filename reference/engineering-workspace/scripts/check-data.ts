import { deepStrictEqual, equal, ok, throws } from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import { baselineArchitecture, initialArchitecture, pipelineArchitecture } from '../src/initial'
import { architectureSchema, defaultView, modelLenses, pipelineLenses, views } from '../src/schema'
import { buildDiagram, switchSettings } from '../src/diagram'
import { lenses, pipelineOverview } from '../src/pipeline-layout'
import { modelGuides, modelViews } from '../src/model-layout'
import { renameNode, removeItems, setPositions, upgradePipeline, upgradeArchitecture } from '../src/document'

const doc = architectureSchema.parse(initialArchitecture)
const json = JSON.stringify(doc,null,2) + '\n'
const exportPath = new URL('../public/default-architecture.json',import.meta.url)
if (process.argv.includes('--write')) writeFileSync(exportPath,json)
else equal(readFileSync(exportPath,'utf8'),json,'The machine-readable default export must match the source.')
deepStrictEqual(architectureSchema.parse(JSON.parse(json)),doc)

for (const view of views) {
  const result = buildDiagram(doc,switchSettings(defaultView,view,doc.pipelineRevision,doc.modelRevision))
  ok(result.boxes.length)
  const ids = new Set(result.boxes.map(box => box.id))
  equal(ids.size,result.boxes.length)
  for (const edge of result.links) ok(ids.has(edge.source) && ids.has(edge.target) && edge.links.length)
  if (view === 'decision') {
    equal(result.boxes.filter(box => box.step).length,8)
    equal(result.links.length,7)
  }
}
for (const node of doc.components) {
  if (['Scientific model','Algorithm'].includes(node.category)) {
    ok(node.algorithm?.name && node.algorithm.validation,node.name + ' must have an editable, seeded specification')
  }
}

const renamed = renameNode(doc,'closure','closure-updated')
architectureSchema.parse(renamed)
equal(buildDiagram(renamed,switchSettings(defaultView,'decision')).links.length,7)
const removed = removeItems(renamed,['closure-updated'],[])
architectureSchema.parse(removed)
ok(buildDiagram(removed,switchSettings(defaultView,'decision')).links.length < 7)
throws(() => architectureSchema.parse({ ...doc,connections:[...doc.connections,{ ...doc.connections[0],id:'dangling',target:'missing' }] }))
console.log(`Validated ${doc.components.length} components, ${doc.connections.length} connections and ${views.length} shared views.`)

const pipeline = switchSettings(defaultView,'pipeline',doc.pipelineRevision)
const overview = buildDiagram(doc,pipeline)
equal(overview.boxes.filter(box=>box.kind==='group').length,12)
equal(overview.boxes.filter(box=>box.kind==='component').length,0)
for (const pair of Object.keys(pipelineOverview)) {
  const [source,target] = pair.split('>')
  ok(overview.links.some(link=>link.source==='group:'+source && link.target==='group:'+target),pair+' must be backed by actual connections')
}
for (const lens of pipelineLenses) {
  const settings = {...pipeline,pipelineLens:lens,expanded:lenses[lens].open}
  const guided = buildDiagram(doc,settings)
  const full = buildDiagram(doc,{...settings,pipelineAllLinks:true})
  const ids = new Set(full.boxes.map(box=>box.id))
  ok(guided.boxes.some(box=>box.kind==='group'))
  ok(guided.links.length)
  ok(full.links.length>=guided.links.length)
  ok(full.links.every(link=>ids.has(link.source)&&ids.has(link.target)))
  const groupBoxes = guided.boxes.filter(box=>box.kind==='group')
  for (const [index,a] of groupBoxes.entries()) for (const b of groupBoxes.slice(index+1)) {
    ok(a.x+a.w<=b.x || b.x+b.w<=a.x || a.y+(a.regionHeight??a.h)<=b.y || b.y+(b.regionHeight??b.h)<=a.y, lens+' group overlap')
  }
}
const gates = doc.components.filter(item=>item.gate)
equal(gates.length,10)
ok(gates.every(item=>item.gate!.result==='Not evaluated' && item.owner && item.inputs.length && item.outputs.length))
const docsWithLayouts = setPositions(doc,'pipeline-global',{'group:sources':{x:200,y:200}})
const globalSettings = {...pipeline,pipelineLens:'global' as const}
equal(buildDiagram(docsWithLayouts,globalSettings).boxes.find(box=>box.id==='group:sources')?.x,200)
equal(buildDiagram(docsWithLayouts,pipeline).boxes.find(box=>box.id==='group:sources')?.x,0)
const old = renameNode(baselineArchitecture,'projection','local-projection-edited')
const legacy = {
  ...old,
  architectureVersion:'Team working draft',
  components:old.components.map(item=>item.id==='elevation' ? {...item,name:'Team elevation model'} : item),
  connections:old.connections.map(edge=>edge.id==='registry--retrieve'?{...edge,description:'Team-specific access process.'}:edge),
  layout:{pipeline:{'group:prep':{x:90,y:115}}},
  viewSettings:{...defaultView,view:'pipeline' as const,expanded:['prep'],viewport:{x:200,y:50,zoom:1}},
}
const upgraded = upgradePipeline(architectureSchema.parse(legacy))
equal(upgraded.architectureVersion,'Team working draft')
equal(upgraded.pipelineRevision,1)
ok(upgraded.components.some(item=>item.id==='local-projection-edited'))
ok(!upgraded.components.some(item=>item.id==='projection'))
ok(upgraded.components.some(item=>item.id==='elevation' && item.name==='Team elevation model' && item.groupId==='terrain'))
ok(upgraded.connections.some(edge=>edge.id==='registry--retrieve' && edge.description==='Team-specific access process.'))
deepStrictEqual(upgraded.layout.pipeline,legacy.layout.pipeline)
equal(upgraded.viewSettings.viewport,undefined)
deepStrictEqual(upgradePipeline(upgraded),upgraded)
console.log('Validated seven Data Pipeline views, ten gates, independent layouts and legacy edit migration.')

const modelSettings = switchSettings(defaultView,'models',doc.pipelineRevision,doc.modelRevision)
equal(buildDiagram(doc,modelSettings).boxes.filter(box=>box.kind==='group').length,14)
for (const lens of modelLenses) {
  const settings = {...modelSettings,modelLens:lens,expanded:modelViews[lens].open}
  const view = buildDiagram(doc,settings)
  const all = buildDiagram(doc,{...settings,modelAllLinks:true})
  const ids = new Set(all.boxes.map(box=>box.id))
  equal(ids.size,all.boxes.length,lens+' has unique nodes')
  ok(all.links.every(link=>ids.has(link.source) && ids.has(link.target) && link.links.length))
  ok(all.links.length>=view.links.length)
  const groups = view.boxes.filter(box=>box.kind==='group')
  for (const [i,a] of groups.entries()) for (const b of groups.slice(i+1)) {
    ok(a.x+a.w<=b.x || b.x+b.w<=a.x || a.y+(a.regionHeight??a.h)<=b.y || b.y+(b.regionHeight??b.h)<=a.y,lens+' group overlap')
  }
  for (const pair of Object.keys(modelGuides[lens])) {
    const [a,b] = pair.split('>')
    const parent = new Map(view.boxes.map(box=>[box.id,box.group?.id]))
    ok(view.links.some(link=>parent.get(link.source)===a && parent.get(link.target)===b),lens+' guide has no backed link: '+pair)
  }
}
const physicsView = buildDiagram(doc,{...modelSettings,modelLens:'terrain',expanded:['geometry']})
ok(physicsView.boxes.some(box=>box.id==='elevation'&&box.group?.id==='geometry'))
equal(doc.components.filter(item=>item.id==='elevation').length,1)
ok(doc.components.every(item=>item.review?.validationStatus!=='Validated'))
ok(doc.connections.some(edge=>edge.source==='hard-filter'&&edge.target==='pareto-front'))
ok(!doc.connections.some(edge=>edge.source==='rank-regions'&&['graph','grade','traverse','rover-travel'].includes(edge.target)))
const oldModels = removeItems(renameNode(pipelineArchitecture,'traverse','team-walking-model'),['sensitivity'],[])
const modelUpgrade = upgradeArchitecture(architectureSchema.parse({...oldModels,
  components:oldModels.components.map(item=>item.id==='rank'?{...item,name:'Team selection'}:item),
  layout:{models:{'group:decision':{x:90,y:115}},'pipeline-global':{'group:atlas':{x:25,y:30}}},
}))
equal(modelUpgrade.modelRevision,1)
ok(modelUpgrade.components.some(item=>item.id==='team-walking-model'))
ok(!modelUpgrade.components.some(item=>item.id==='sensitivity'||item.id==='traverse'))
ok(modelUpgrade.components.some(item=>item.id==='rank'&&item.name==='Team selection'))
deepStrictEqual(modelUpgrade.layout['pipeline-global'],{'group:atlas':{x:25,y:30}})
deepStrictEqual(upgradeArchitecture(modelUpgrade),modelUpgrade)
console.log('Validated ten scientific views, backed guide links, canonical models, feasibility ordering and v2 edit migration.')
