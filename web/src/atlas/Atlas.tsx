import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowUpRight, BookOpen, ChevronDown, Compass, Globe2, Layers3, Orbit, Search, SlidersHorizontal } from 'lucide-react'
import { z } from 'zod'
import { loadDocument } from '../document'
import { MarsMap } from './MarsMap'
import type { Camera, MapControls } from './MarsMap'
import { RatingBadge, RegionInspector } from './RegionInspector'
import { assets, assessmentFor, byRegion, featureColor, featureTypes, labels, levels, mapModes, modeDescriptions, modes, normalizeLongitude, profileLabels, profiles, ratingColor, regions, researchProvenance, searchText } from './data'
import type { MapMode, Mode, Profile, RasterAsset, Rating } from './data'
import './atlas.css'

const ResearchViewer=lazy(()=>import('./ResearchViewer').then(module=>({default:module.ResearchViewer})))
const Comparison=lazy(()=>import('./Comparison').then(module=>({default:module.Comparison})))
const storageKey='return-window-atlas/v1'
const panels=['map','research','compare'] as const
const stateSchema=z.object({
  region:z.string().nullable().catch('06'),panel:z.enum(panels).catch('map'),
  compare:z.array(z.string()).catch([]),mode:z.enum(mapModes).catch('documentation'),profile:z.enum(profiles).catch('rover'),
  basemap:z.enum(['viking','mola']).catch('viking'),showMarkers:z.boolean().catch(true),showLabels:z.boolean().catch(true),
  showGrid:z.boolean().catch(false),showDetail:z.boolean().catch(false),
})
type AtlasState=z.infer<typeof stateSchema>
const cameraSchema=z.object({center:z.tuple([z.number(),z.number().min(-90).max(90)]),zoom:z.number().min(0).max(14)})
const defaults=stateSchema.parse({})
const searchIndex=new Map(regions.map(region=>[region.id,searchText(region)]))

function loadState() {
  try {
    const raw=JSON.parse(localStorage.getItem(storageKey) ?? '{}')
    const { data:camera }=cameraSchema.safeParse(raw.camera)
    return {state:stateSchema.parse(raw.state ?? {}),camera}
  } catch {return {state:defaults,camera:undefined}}
}
function readUrl(saved:AtlasState,initial=false):AtlasState {
  const params=new URLSearchParams(location.search)
  if (initial&&!location.search) return saved
  const id=params.get('region')
  const region=id==='none'?null:id&&byRegion.has(id)?id:defaults.region
  return stateSchema.parse({...saved,region,panel:params.get('panel') ?? 'map',mode:params.get('mode') ?? saved.mode,
    profile:params.get('profile') ?? saved.profile,compare:params.has('compare')?(params.get('compare') ?? '').split(',').filter(id=>byRegion.has(id)):saved.compare})
}
function syncUrl(state:AtlasState,replace:boolean) {
  const params=new URLSearchParams()
  params.set('region',state.region ?? 'none')
  if(state.panel!=='map')params.set('panel',state.panel)
  params.set('mode',state.mode)
  params.set('profile',state.profile)
  params.set('compare',state.compare.join(','))
  const url=`/atlas?${params}`
  if (location.pathname+location.search===url) return
  if (replace) history.replaceState(null,'',url)
  else history.pushState(null,'',url)
}
function LayerInfo({asset}:{asset:RasterAsset}) {
  return <div className="atlas-layer-info"><p>{asset.era}</p>
    <p>{asset.nativeMeters} m native · {(asset.sampleDegrees*3396190*Math.PI/180).toLocaleString(undefined,{maximumFractionDigits:0})} m/pixel at equator in this display · {asset.id==='jezero'?'bounded Jezero subset':'global'}</p>
    <p>Packaged display imagery · NASA Mars Trek · {asset.credit}</p>
    <p>{asset.limits}</p><a href={asset.source} target="_blank" rel="noreferrer">Source catalog <ArrowUpRight size={12}/></a></div>
}
function FeatureLegend() {
  return <details className="atlas-legend" open>
    <summary><span>Geographic feature type</span><ChevronDown size={14}/></summary>
    <div className="atlas-feature-legend">{featureTypes.map(type=><span key={type}><i style={{background:featureColor(type)}}/>{type}</span>)}</div>
    <p>Categories from the research registry.</p>
  </details>
}
function ScaleLegend({mode,profile}:{mode:Mode;profile:Profile}) {
  return <details className="atlas-legend" open>
    <summary><span>{labels[mode]}</span><ChevronDown size={14}/></summary>
    <div className="atlas-legend-steps">{levels.map((level,i)=><span key={level}><i style={{background:ratingColor(mode,(i+1) as Rating)}}/>{level}</span>)}</div>
    <p>{mode==='traversal'&&profile!=='rover'?'This profile has no classified traversal assessments.':modeDescriptions[mode]}</p>
    <p className="atlas-legend-unknown"><i/> Mixed, unknown or unclassified</p>
  </details>
}
export default function Atlas() {
  const [loaded]=useState(loadState)
  const [state,setState]=useState(()=>readUrl(loaded.state,true))
  const current=useRef(state)
  current.current=state
  const deepLinkRegion = new URLSearchParams(location.search).get('region')
  const deepLinkTarget = deepLinkRegion && deepLinkRegion !== loaded.state.region ? byRegion.get(deepLinkRegion) : undefined
  const camera=useRef<Camera|undefined>(deepLinkTarget ? {center:deepLinkTarget.geography.center,zoom:4} : loaded.camera)
  const map=useRef<MapControls>(null)
  const requestedFocus=useRef<string|null>(null)
  const [architecture]=useState(()=>new Map(loadDocument().doc.components.map(component=>[component.id,component])))
  const [query,setQuery]=useState('')
  const [type,setType]=useState('')
  const [level,setLevel]=useState('')
  const [showLayers,setShowLayers]=useState(false)
  const [showFilters,setShowFilters]=useState(false)
  const [mobile,setMobile]=useState<'map'|'index'|'region'>('map')
  const selected=state.region ? byRegion.get(state.region) : undefined
  const compare=state.compare.filter(id=>byRegion.has(id))
  const persist=(snapshot:AtlasState)=>{try{localStorage.setItem(storageKey,JSON.stringify({state:snapshot,camera:camera.current}))}catch{/* Browser storage is optional. */}}
  function change(patch:Partial<AtlasState>,replace=false) {
    const next={...current.current,...patch}
    current.current=next
    setState(next)
    syncUrl(next,replace)
    persist(next)
  }
  function returnToMap() {
    change({panel:'map'})
    setMobile('map')
  }
  useEffect(()=>{
    // Give the initial entry a stable history address before pushing selections.
    syncUrl(current.current,true)
    const pop=()=>{const next=readUrl(current.current);current.current=next;setState(next);persist(next)}
    window.addEventListener('popstate',pop)
    return ()=>window.removeEventListener('popstate',pop)
  },[])
  useEffect(()=>{
    if (state.panel!=='map'||!requestedFocus.current) return
    const target=byRegion.get(requestedFocus.current)
    requestedFocus.current=null
    if (target) {
      const frame=requestAnimationFrame(()=>map.current?.locate(target))
      return ()=>cancelAnimationFrame(frame)
    }
  },[state.panel,state.region])
  const needle=query.trim().toLowerCase()
  const visible=useMemo(()=>regions.filter(region=>
    (!needle||searchIndex.get(region.id)?.includes(needle))&&(!type||region.featureType===type)&&
    (!level||state.mode==='feature'||String(assessmentFor(region,state.mode,state.profile).rating)===level)
  ).sort((a,b)=>needle?Number(!a.name.toLowerCase().includes(needle))-Number(!b.name.toLowerCase().includes(needle))||a.id.localeCompare(b.id):0),
  [needle,type,level,state.mode,state.profile])
  function select(id:string,locate=false) {
    const region=byRegion.get(id)
    if (!region) return
    change({region:id,panel:'map'})
    setMobile('region')
    if (locate&&state.panel==='map') map.current?.locate(region)
    else if (locate) requestedFocus.current=id
  }
  function openResearch(id=state.region ?? '06') {change({region:id,panel:'research'})}
  function toggleCompare(id:string) {
    const ids=current.current.compare
    change({compare:ids.includes(id)?ids.filter(value=>value!==id):[...ids,id]},true)
  }
  function detail() {change({showDetail:true,basemap:'viking'},true);map.current?.detail();setMobile('map')}
  const moveCamera=(next:Camera)=>{camera.current={...next,center:[normalizeLongitude(next.center[0]),next.center[1]]};persist(current.current)}
  return <div className="atlas-app">
    <header className="masthead atlas-masthead">
      <div className="brand"><div className="brand-icon"><Orbit size={23} strokeWidth={1.3}/></div><div><h1>Return Window</h1><p>PLANETARY RESEARCH <span>·</span> PERIAPSIS</p></div></div>
      <nav aria-label="Return Window modules" className="atlas-modules">
        <button className="button atlas-current" aria-current="page" onClick={returnToMap}><Globe2 size={15}/> Atlas</button>
        <a className="button" href="/architecture">Architecture</a>
        <a className="button atlas-model-nav" href="/architecture?view=models">Scientific models</a>
      </nav>
      <nav aria-label="Atlas tools" className="atlas-toolnav">
        <button className="button" aria-pressed={state.panel==='research'} onClick={()=>openResearch()}><BookOpen size={15}/> Research</button>
        <button className="button" aria-pressed={state.panel==='compare'} onClick={()=>change({panel:'compare'})}>Compare <span className="atlas-count">{compare.length}</span></button>
      </nav>
    </header>
    {state.panel==='map'?<>
      <div className="atlas-mobile-tabs" aria-label="Map panels">
        <button className="button" aria-pressed={mobile==='index'} onClick={()=>setMobile('index')}>Regions</button>
        <button className="button" aria-pressed={mobile==='map'} onClick={()=>setMobile('map')}>Map</button>
        <button className="button" aria-pressed={mobile==='region'} onClick={()=>setMobile('region')}>Inspector</button>
      </div>
      <main className="atlas-workspace" data-mobile={mobile}>
        <aside className="atlas-sidebar" aria-label="Region index and map settings">
          <div className="atlas-side-top">
            <div className="atlas-kicker">MARS / RESEARCH INDEX</div>
            <h2>Explore regions</h2>
            <label className="atlas-search"><Search size={16}/><input aria-label="Find region" placeholder="Find a region…" value={query} onChange={e=>setQuery(e.target.value)}
              onKeyDown={e=>{if(e.key==='Enter'&&visible[0])select(visible[0].id,true)}}/></label>
            <label className="atlas-field">Map classification<select value={state.mode} onChange={e=>{setLevel('');change({mode:e.target.value as MapMode},true)}}>
              {modes.map(mode=><option key={mode} value={mode}>{labels[mode]}</option>)}
              <option value="feature">Geographic feature type</option>
            </select></label>
            <label className="atlas-field">Mission profile<select value={state.profile} onChange={e=>{setLevel('');change({profile:e.target.value as Profile},true)}}>
              {profiles.map(profile=><option key={profile} value={profile}>{profileLabels[profile]}</option>)}
            </select></label>
            <div className="atlas-side-tools">
              <button className="button" aria-expanded={showFilters} onClick={()=>setShowFilters(!showFilters)}><SlidersHorizontal size={14}/> Filters{type||level?' •':''}</button>
              <button className="button" aria-expanded={showLayers} onClick={()=>setShowLayers(!showLayers)}><Layers3 size={14}/> Layers</button>
            </div>
          </div>
          {showFilters&&<div className="atlas-side-drawer">
            <label className="atlas-field">Feature type<select value={type} onChange={e=>setType(e.target.value)}><option value="">All types</option>{featureTypes.map(t=><option key={t}>{t}</option>)}</select></label>
            {state.mode!=='feature'&&<label className="atlas-field">Assessment level<select value={level} onChange={e=>setLevel(e.target.value)}><option value="">All levels</option>{levels.map((v,i)=><option key={v} value={i+1}>{v}</option>)}<option value="null">Unclassified / unknown</option></select></label>}
            <button className="quiet" onClick={()=>{setType('');setLevel('');setQuery('')}}>Clear filters</button>
          </div>}
          {showLayers&&<div className="atlas-side-drawer" aria-label="Map layers">
            <label className="atlas-field">Global raster<select value={state.basemap} onChange={e=>change({basemap:e.target.value as AtlasState['basemap']},true)}><option value="viking">Viking color mosaic</option><option value="mola">MOLA shaded relief</option></select></label>
            <details><summary>Global raster metadata</summary><LayerInfo asset={assets[state.basemap]}/></details>
            {([['showMarkers','Research markers'],['showLabels','Feature names'],['showGrid','Coordinate grid'],['showDetail','Jezero CTX imagery']] as const).map(([key,label])=>
              <label className="atlas-check" key={key}><input type="checkbox" checked={state[key]} onChange={e=>change({[key]:e.target.checked},true)}/>{label}</label>)}
            <details><summary>Jezero detail metadata</summary><LayerInfo asset={assets.jezero}/><button className="quiet" onClick={detail}>Zoom to imagery</button></details>
            <p className="atlas-note">Operational overlays await validated assets. <a href="/architecture?component=rank-regions">Overall priority not evaluated</a>.</p>
          </div>}
          <div className="atlas-region-list">
            <div className="atlas-panel-heading"><h3>Research locations</h3><span>{visible.length} / 56</span></div>
            <div className="atlas-index-list">
              {visible.map(region=><button key={region.id} aria-current={region.id===state.region?'true':undefined} onClick={()=>select(region.id,true)}>
                <span>{region.id}</span><strong>{region.name}</strong>{state.mode==='feature'?
                  <span className="atlas-rating" style={{color:featureColor(region.featureType)}}><i/>{region.featureType}</span>:
                  <RatingBadge region={region} mode={state.mode} profile={state.profile}/>}
              </button>)}
              {!visible.length&&<p className="atlas-note">No matching research locations.</p>}
            </div>
          </div>
        </aside>
        <section className="atlas-map-panel" aria-label="Mars atlas">
          <div className="atlas-map-heading">
            <div><div className="atlas-kicker"><Compass size={13}/> GLOBAL SURVEY <span>·</span> MARS</div><h2>Mars Research Atlas</h2></div>
            <span className="atlas-map-tag"><i/> LOCAL DATA</span>
          </div>
          <div className="atlas-map-frame">
            <MarsMap ref={map} camera={camera.current} saveCamera={moveCamera} regions={visible} selected={state.region} select={id=>select(id)}
              mode={state.mode} profile={state.profile} basemap={state.basemap} showMarkers={state.showMarkers}
              showLabels={state.showLabels} showGrid={state.showGrid} showDetail={state.showDetail}/>
            {state.mode==='feature'?<FeatureLegend/>:<ScaleLegend mode={state.mode} profile={state.profile}/>}
          </div>
          <footer className="atlas-map-footer"><a href="https://planetarynames.wr.usgs.gov/Page/MARS/system" target="_blank" rel="noreferrer">Mars planetocentric · east-positive</a>
            <a href={researchProvenance.source} target="_blank" rel="noreferrer">IAU / USGS feature centers</a></footer>
        </section>
        {selected?<RegionInspector region={selected} profile={state.profile} components={architecture} compared={compare.includes(selected.id)}
          compare={()=>toggleCompare(selected.id)} locate={()=>{map.current?.locate(selected);setMobile('map')}}
          close={()=>{change({region:null});setMobile('map')}} research={()=>openResearch(selected.id)}
          select={id=>select(id,true)} detail={detail}/>:
          <aside className="atlas-inspector atlas-empty-inspector" aria-label="Region inspector"><div className="atlas-kicker">REGIONAL RESEARCH</div><h2>Select a feature</h2>
            <p>Choose a map marker or a region from the index to inspect its evidence, assessments and planning readiness.</p>
            {['06','03','43'].map(id=><button className="atlas-related" key={id} onClick={()=>select(id,true)}>{byRegion.get(id)?.name}<ArrowUpRight size={13}/></button>)}
          </aside>}
      </main>
    </>:<Suspense fallback={<p className="atlas-loading" role="status">Opening research…</p>}>
      {state.panel==='research'?<ResearchViewer region={selected ?? byRegion.get('06')!}
        select={id=>change({region:id})} back={returnToMap}/>:
        <div className="atlas-compare-shell"><div className="atlas-compare-top"><button className="button" onClick={returnToMap}><ArrowLeft size={14}/> Back to map</button>
          <label>Mission profile <select value={state.profile} onChange={e=>change({profile:e.target.value as Profile},true)}>{profiles.map(profile=><option key={profile} value={profile}>{profileLabels[profile]}</option>)}</select></label></div>
          <Comparison profile={state.profile} ids={compare} toggle={toggleCompare} openMap={id=>select(id,true)} openResearch={openResearch}/></div>}
    </Suspense>}
  </div>
}
