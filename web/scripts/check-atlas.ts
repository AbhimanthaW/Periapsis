import { strict as assert } from 'node:assert'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { initialArchitecture } from '../src/initial'
import { assets, assetIds, assessmentFor, atlasModelIds, byRegion, globalExtent, modes, normalizeLongitude, planningContext, ratingColor, regions, researchProvenance } from '../src/atlas/data'

const path = (name:string) => new URL('../public/atlas/'+name,import.meta.url)
const archive = readFileSync(path('MARS_REGIONAL_RESEARCH.md'))
const sha = createHash('sha256').update(archive).digest('hex')
assert.equal(sha,researchProvenance.sha256)
const lines = archive.toString().split(/\r?\n/)
assert.equal(byRegion.size,56)
assert.deepEqual(regions.map(region=>region.id),Array.from({length:56},(_,i)=>String(i+1).padStart(2,'0')))
for (const [index,region] of regions.entries()) {
  assert.ok(lines[region.startLine-1].includes(region.sourceName))
  assert.ok(region.endLine>region.startLine)
  if (regions[index+1]) assert.equal(region.endLine+1,regions[index+1].startLine)
  assert.match(region.geography.gazetteerUrl,/^https:\/\/planetarynames\.wr\.usgs\.gov\/Feature\/\d+/)
  assert.ok(region.geography.center.every(Number.isFinite))
  assert.ok(region.overview.length>0)
  assert.ok(region.related.every(relation=>byRegion.has(relation.id)))
  assert.equal(assessmentFor(region,'traversal','human').rating,null)
  assert.equal(assessmentFor(region,'traversal','terrain').rating,null)
  assert.equal(planningContext(region,'rover')?.sitePackId,null)
  assert.equal(planningContext(region,'human')?.start,null)
  for (const mode of modes) if (region.assessments[mode].rating !== null) assert.ok(region.assessments[mode].original)
}
assert.equal(regions.filter(region=>region.geography.status==='Representative anchor').length,2)
assert.equal(regions.filter(region=>region.geography.shape).length,0)
assert.match(lines[byRegion.get('47')!.startLine-1],/Mawrth Vallis/)
assert.ok(byRegion.get('01')!.geography.center[1]>80 && byRegion.get('22')!.geography.center[1]<-80)
assert.ok(byRegion.get('06')!.geography.center[0]<-130)
assert.equal(byRegion.get('06')!.assessments.traversal.rating,null)
assert.equal(byRegion.get('33')!.assessments.traversal.rating,null)
assert.equal(normalizeLongitude(226.1975),-133.8025)
assert.equal(normalizeLongitude(540),-180)
assert.equal(ratingColor('documentation',1),ratingColor('traversal',5))
assert.notEqual(ratingColor('science',5),ratingColor('documentation',5))
assert.notEqual(ratingColor('traversal',null),ratingColor('traversal',3))

const components=new Set(initialArchitecture.components.map(item=>item.id))
for (const id of [...Object.values(atlasModelIds).flat(),'rover-travel','rover-energy','traverse','human-profile']) assert.ok(components.has(id),id)
assert.deepEqual(globalExtent,[-180,-90,180,90])
for (const id of assetIds) {
  const layer=assets[id]
  assert.equal((layer.extent[2]-layer.extent[0])/layer.sampleDegrees,layer.width)
  assert.equal((layer.extent[3]-layer.extent[1])/layer.sampleDegrees,layer.height)
  assert.match(layer.service,/^https:\/\/trek\.nasa\.gov/)
  if (id==='jezero') {
    assert.ok(existsSync(path('jezero.webp')))
    const [lon,lat]=byRegion.get('43')!.geography.center
    assert.ok(lon>layer.extent[0]&&lon<layer.extent[2]&&lat>layer.extent[1]&&lat<layer.extent[3])
  } else {
    assert.deepEqual(layer.extent,globalExtent)
    for (let zoom=0;zoom<=2;zoom++) for (let x=0;x<2**(zoom+1);x++) for(let y=0;y<2**zoom;y++) assert.ok(existsSync(path(`${id}/${zoom}/${x}/${y}.webp`)))
  }
}
console.log('Atlas validated: 56 regions, exact survey archive and section spans, Gazetteer bounds, research scales, all local raster tiles and canonical model links.')
