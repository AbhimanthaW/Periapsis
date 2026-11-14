import { useEffect, useRef, useState } from 'react'
import { ArrowsOut, GridFour, Pause, Play, Swap, X } from '@phosphor-icons/react'
import type { MissionProps } from './mission'
import { Action, Panel, RangeChart, routeIds, RouteMap } from './MissionUI'
import { Matrix } from './Analysis'
import { Readouts, Section, Warn } from './RegionEvidence'
import { Badge, IconButton, Segmented } from './ui'

const feedback = ['Archive','Recorded','Simulated'] as const
const changeTypes = ['Obstruction','Component','Constraint'] as const
const moduleGroups = [['Rover operations','Camera feed','Power','Progress','Components'],['Energy · terrain','Energy history','Terrain profile'],['Environment · console','Weather','Event log']]
const defaultModules = ['Camera feed','Power','Progress','Components','Mission map']
const presetsDefault = {'Rover Mission Control':defaultModules,'Compact playback':['Camera feed','Mission map','Progress'],'Field telemetry':[...defaultModules,'Energy history','Event log']}
const pad = (n:number) => String(n).padStart(2,'0')
const timeCode = (n:number) => pad(Math.floor(n/3600))+':'+pad(Math.floor(n%3600/60))+':'+pad(n%60)

function Camera({ eva, progress, setProgress, playing, setPlaying }: {
  eva?: boolean; progress:number; setProgress:(n:number)=>void; playing:boolean; setPlaying:(b:boolean)=>void
}) {
  const [source,setSource]=useState<(typeof feedback)[number]>('Simulated')
  const [helmet,setHelmet]=useState('EV1')
  const [expanded,setExpanded]=useState(false)
  return <Panel name="Camera feed" className={(eva?'eva-camera ':'rover-camera ')+'striped'+(expanded?' expanded-camera':'')}>
    <header className="section-heading">{eva?<span>Helmet · {helmet} <Badge>SIM</Badge></span>:<Segmented items={feedback} value={source} onChange={setSource} label="Footage source"/>}
      {eva&&<div className="inline-controls"><IconButton aria-label="Switch helmet" onClick={()=>setHelmet(helmet==='EV1'?'EV2':'EV1')}><Swap size={15}/></IconButton><IconButton aria-label={expanded?'Restore camera':'Expand camera'} onClick={()=>setExpanded(!expanded)}><ArrowsOut size={15}/></IconButton></div>}</header>
    <div className="camera-unavailable"><p>{source==='Archive'?'No archive connected':source==='Recorded'?'No recording loaded':'No footage source'}</p>
      <span className="muted">{eva?'Simulated helmet camera or analogue recording':'Connect an archive or load a recording'}</span></div>
    {(!eva||expanded)&&<footer><IconButton aria-label={playing?'Pause playback':'Play playback'} onClick={()=>setPlaying(!playing)}>{playing?<Pause size={16}/>:<Play size={16}/>}</IconButton>
      <span className="mono">T+{timeCode(Math.round(progress*31.2))}</span><input type="range" style={{ background: `linear-gradient(to right, #f3eae0 ${progress}%, #423a32 ${progress}%)` }} min="0" max="100" step=".01" value={progress} aria-label="Playback position" onChange={e=>setProgress(Number(e.target.value))}/>
      <span className="mono muted">00:52:00</span><IconButton aria-label={expanded?'Restore camera':'Expand camera'} onClick={()=>setExpanded(!expanded)}><ArrowsOut size={16}/></IconButton></footer>}
  </Panel>
}

function ModuleLibrary({ modules, toggle, reset }: { modules:string[]; toggle:(name:string)=>void; reset:()=>void }) {
  const [search,setSearch]=useState('')
  return <Panel name="Module library" className="module-library">
    <input type="search" placeholder="Search modules" aria-label="Search modules" value={search} onChange={e=>setSearch(e.target.value)}/>
    {moduleGroups.map(([group,...items])=>{
      const filtered=items.filter(name=>name.toLowerCase().includes(search.toLowerCase()))
      return filtered.length>0&&<Section title={group} key={group}>{filtered.map(name=><div className="section-heading module-row" key={name}>
        <span>{name} {['Weather','Terrain profile'].includes(name)&&<Badge>SIM</Badge>}</span>
        <button className={modules.includes(name)?'good mono':'button compact'} aria-label={(modules.includes(name)?'Remove ':'Add ')+name}
          onClick={()=>toggle(name)}>{modules.includes(name)?'ON':'Add'}</button>
      </div>)}</Section>
    })}
    <div className="section-heading library-footer"><span className="muted">Preset · Rover Mission Control</span><Action onClick={reset}>Reset</Action></div>
  </Panel>
}
function LayoutEditor({ modules, setModules, go, presets, savePreset, preset, setPreset }: {
  modules:string[]; setModules:(value:string[])=>void; go:MissionProps['go']; presets:Record<string,string[]>; savePreset:(name:string)=>void; preset:string; setPreset:(name:string)=>void
}) {
  const [moving,setMoving]=useState('Energy history')
  const [collapsed,setCollapsed]=useState<string[]>([])
  const [showEvent,setShowEvent]=useState(true)
  const [extraSlot,setExtraSlot]=useState('')
  const [name,setName]=useState('')
  const dialog=useRef<HTMLDialogElement>(null)
  function drop() {
    if(!moving)return
    setExtraSlot(moving)
    if(!modules.includes(moving))setModules([...modules,moving])
    setMoving('')
  }
  function module(name:string, area:string, size:string, pinned=false) {
    const minimized=collapsed.includes(name)
    return <section className={'glass layout-module '+area+(pinned?' pinned':'')+(minimized?' collapsed':'')} draggable={!pinned} onDragStart={()=>setMoving(name)}>
      <header><b>{name}</b><div className="inline-controls">{pinned&&<span className="mono accent">PINNED</span>}
        {['Camera feed','Mission map'].includes(name)&&<button aria-label={(minimized?'Expand ':'Collapse ')+name} onClick={()=>setCollapsed(minimized?collapsed.filter(x=>x!==name):[...collapsed,name])}>{minimized?'+':'−'}</button>}
        {!pinned&&<button aria-label={'Remove '+name} onClick={()=>{if(name==='Event log')setShowEvent(false);else if(name===extraSlot)setExtraSlot('');setModules(modules.filter(x=>x!==(name==='Battery'?'Power':name)))}}><X size={13}/></button>}
      </div></header><footer className="mono muted">{size}</footer>
    </section>
  }
  return <div className="layout-screen">
    <div className="layout-tools inline-controls"><label className="caption">Preset <select aria-label="Layout preset" value={preset} onChange={e=>{setPreset(e.target.value);setModules([...presets[e.target.value]]);setExtraSlot('');setMoving('')}}>{Object.keys(presets).map(value=><option key={value}>{value}</option>)}</select></label>
      <Action onClick={()=>dialog.current?.showModal()}>Save as</Action><Action onClick={()=>{setModules([...defaultModules]);setExtraSlot('');setMoving('');setShowEvent(true);setPreset('Rover Mission Control')}}>Reset</Action><Action primary onClick={()=>go('monitor','playback')}>Done</Action></div>
    <div className="layout-top">
      {module('Camera feed','camera-layout','8 × 6 cells · cannot be removed in this preset',true)}
      {modules.includes('Mission map')?module('Mission map','map-layout','5 × 6 cells'):<button className="glass layout-module map-layout" onClick={()=>setModules([...modules,'Mission map'])}>Add mission map</button>}
      <div className="layout-slot">
        {extraSlot?module(extraSlot,'drop-layout','3 × 3 cells'): <button className="glass layout-module drop-layout" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();drop()}} onClick={drop}>Drop here <span className="mono muted">3 × 3 cells free</span></button>}
        {showEvent?module('Event log','event-layout','3 × 3 cells'):<button className="glass layout-module" onClick={()=>setShowEvent(true)}>Add event log</button>}
      </div>
    </div>
    <div className="layout-bottom">
      {([['Power','Battery'],['Progress','Progress'],['Components','Components']] as const).map(([key,label])=>modules.includes(key)?<div key={key}>{module(label,'','4 × 4 cells')}</div>:<button key={key} className="glass layout-module" onClick={()=>setModules([...modules,key])}>Add {label.toLowerCase()}</button>)}
      {module('Route and warnings','','4 × 4 cells · warnings always shown',true)}
    </div>
    {moving&&<button className="glass moving-module" draggable onDragStart={()=>setMoving(moving)} aria-label={'Place '+moving} onClick={drop}><span className="section-heading"><b>{moving}</b><span className="mono accent">MOVING</span></span><span className="mono muted">from library · 3 × 3 cells</span></button>}
    <dialog className="dialog" ref={dialog} aria-labelledby="preset-title"><form onSubmit={e=>{e.preventDefault();if(name.trim()){savePreset(name.trim());setName('');dialog.current?.close()}}}><h2 id="preset-title">Save layout preset</h2>
      <label>Preset name <input required value={name} onChange={e=>setName(e.target.value)}/></label><div className="dialog-actions"><Action onClick={()=>dialog.current?.close()}>Cancel</Action><button className="button primary">Save preset</button></div></form></dialog>
  </div>
}

function BlockedMap({ elevator, block }: { elevator:number; block:boolean }) {
  return <svg className="route-overlay contingency-lines" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-label="Obstruction and replan candidates">
    <path d="M755 522 Q995 610 1152 630" fill="none" stroke="#f4eade" strokeWidth="4" strokeLinecap="round"/>
    <path d="M512 459 C535 278 731 329 755 522 M512 459 C536 628 727 663 755 522" fill="none" stroke="#241a15" strokeWidth="9"/>
    <path d="M512 459 C535 278 731 329 755 522" fill="none" stroke="#f4eade" strokeWidth="3" strokeDasharray="18 13" strokeLinecap="round"/>
    <path d="M512 459 C536 628 727 663 755 522" fill="none" stroke="#e4874f" strokeWidth="4"/>
    <path d="M512 459 Q628 479 755 522" fill="none" stroke="#e9e1d99e" strokeWidth="3" strokeDasharray="3 13" strokeLinecap="round"/>
    {block&&<g transform={`translate(${elevator} 0)`}><path d="M615 450 L683 441 L706 516 L648 550 L584 514 Z" fill="#f1666238" stroke="#f67f76" strokeWidth="3" strokeDasharray="11 6"/><text x="604" y="426" fill="#f47773">BLOCKED</text></g>}
    <circle cx="513" cy="459" r="13" fill="#0b0908" stroke="#f5ede4" strokeWidth="3"/>
    <circle cx="755" cy="522" r="17" fill="#e4874f41" stroke="#e4874f" strokeWidth="2"/><circle cx="755" cy="522" r="6" fill="#e4874f"/>
    <g fill="#f5ede4"><text x="632" y="321">B</text><text x="543" y="450">A · invalid</text><text x="633" y="637" fill="#e4874f">D</text></g>
  </svg>
}

function RoverContingency({ props, decide }: { props:MissionProps; decide:(decision:string,route?:string)=>void }) {
  const [changed,setChanged]=useState<(typeof changeTypes)[number]>('Obstruction')
  const [clearance,setClearance]=useState('15')
  const [source,setSource]=useState('Simulated by operator')
  const [redraw,setRedraw]=useState(false)
  const [offset,setOffset]=useState(0)
  const [checked,setChecked]=useState(true)
  const [candidate,setCandidate]=useState('D')
  return <div className="mission-canvas contingency-view">
    <RouteMap regionId={props.region.id} visible={false}/>
    <BlockedMap elevator={offset} block={changed==='Obstruction'}/>
    {redraw&&<button className="obstruction-tool" aria-label="Place blocked area" onClick={()=>{setOffset(offset===0?35:0);setRedraw(false);setChecked(false)}}>Place blocked area</button>}
    <Panel name="What changed" className="change-dock left-dock">
      <span className="caption">What changed</span><Segmented items={changeTypes} value={changed} onChange={value=>{setChanged(value);setChecked(false)}} label="Change type"/>
      {changed==='Obstruction'?<div className="change-form"><Readouts rows={[[ 'Area',<span className="mono">drawn · 0.04 km²</span> ]]}/>
        <label>Source class <select value={source} onChange={e=>{setSource(e.target.value);setChecked(false)}}><option>Simulated by operator</option><option>Observed in analogue</option></select></label>
        <label>Clearance <span><input type="number" min="0" value={clearance} onChange={e=>{setClearance(e.target.value);setChecked(false)}}/> <small>m</small></span></label>
        <Readouts rows={[[ 'Position used',<><span className="mono">map estimate</span> <Badge>SIM</Badge></> ]]}/>
      </div>:<div className="change-form"><label>{changed==='Component'?'Component':'New limit'} <select onChange={()=>setChecked(false)}>{(changed==='Component'?['Drive wheel','Navigation','Power']:['Energy reserve','Clearance','Slope']).map(x=><option key={x}>{x}</option>)}</select></label>
        {changed==='Component'&&<Action onClick={()=>props.go('monitor','salvage')}>Search salvage targets</Action>}</div>}
      <div className="mission-actions fill"><Action onClick={()=>{setRedraw(!redraw);setChecked(false)}}>{redraw?'Cancel redraw':'Redraw'}</Action><Action primary onClick={()=>{setChecked(true);setRedraw(false)}}>Recheck</Action></div>
      <div className="recheck-log mono muted" role="status">{checked?<><b>mask</b> 34 cells excluded<br/><b>stored</b> A, B, C rechecked from position<br/><b>path</b> 1 new candidate<br/><b>rank</b> D · B</>:'Change entered · recheck required'}</div>
    </Panel>
    <Panel name="Replan results" className="contingency-dock right-dock">
      <div className="route-selected"><div className="section-heading"><div><b className="accent mono replan-rank">1</b> <strong>Route {candidate} · {candidate==='D'?'new':'stored'}</strong><p className="mono muted">{candidate==='D'?'0.92 km · 27 min':'1.30 km · 38 min'} from here</p></div><span className="good mono">{checked?'PASS 5/5':'STALE'}</span></div>
      <Readouts rows={[[ 'Energy margin at target',<><span className="mono">{candidate==='D'?'+128':'+95'} Wh</span> <Badge>CALC</Badge></> ],['Was, on route '+props.mission.route,'+190 Wh'],['Completion','Sol 214 · 15:31'],['Planned','Sol 214 · 15:40'],['Assumes',changed==='Obstruction'?'Blocked area as drawn, '+clearance+' m clearance':changed+' change as entered']]}/>
      <div className="mission-actions fill"><Action primary disabled={!checked} onClick={()=>decide('Reroute',candidate)}>Switch to {candidate}</Action><Action onClick={()=>decide('Defer')}>Keep holding</Action></div></div>
      <button className="other-route" onClick={()=>setCandidate(candidate==='D'?'B':'D')}>2 Route {candidate==='D'?'B':'D'} · stored <span className="mono muted">1.30 km · 38 min</span> +95 Wh</button>
      <div className="other-route muted">— Route {props.mission.route} <span className="bad mono">FAIL · crosses blocked area</span></div><div className="other-route muted">— Route C · stored <span className="bad mono">FAIL · energy −20 Wh</span></div>
    </Panel>
  </div>
}

function Salvage({ props, decide }: { props:MissionProps; decide:(decision:string)=>void }) {
  const [marker,setMarker]=useState(false)
  return <div className="mission-canvas salvage-view">
    <div className="salvage-globe"><img src="./maps/mars-salvage.webp" alt="Viking Mars globe"/><button aria-label="Rover position" aria-pressed={marker} onClick={()=>setMarker(!marker)}><i/>Rover · {props.region.name.replace(' Crater','')}</button>{marker&&<p className="glass">Simulated rover position</p>}</div>
    <Panel name="Salvage targets" className="salvage-panel right-dock">
      <header><div className="section-heading"><span className="caption">Component fault</span><Badge>SIM</Badge></div><h1>No salvage target in range</h1><p className="mono muted">Range left 1.6 km · nearest past rover 3,751 km</p></header>
      <Matrix headers={['Past rover','Site','Distance','State','Reachable']} rows={[
        ['Curiosity','Gale Crater','3,751 km','Operating',<span className="bad">No · not a target</span>],
        ['Opportunity','Meridiani Planum','4,972 km','Ended 2018',<span className="bad">No · out of range</span>],
        ['Spirit','Gusev Crater','6,033 km','Ended 2010',<span className="bad">No · out of range</span>],
        ['Sojourner','Ares Vallis','6,051 km','Ended 1997',<span className="bad">No · out of range</span>],
      ]}/>
      <Section title="Limits of this check" status={<span className="muted"><Badge>OBS</Badge> positions <Badge>CALC</Badge> distance</span>}><Readouts rows={[[ 'Distance','Great-circle, not a drivable route' ],['Part condition',<Warn>Unknown · no evidence a part is usable</Warn>],['Part compatibility',<Warn>Not modelled</Warn>],['Routing between regions',<Warn>Not supported · one region per pack</Warn>]]}/></Section>
      <div className="mission-actions fill"><Action primary onClick={()=>props.go('monitor','contingency')}>Back to replan</Action><Action onClick={()=>decide('Defer')}>Hold position</Action></div>
    </Panel>
  </div>
}

const tradeoffs = [
  ['Return now, planned path','0:36','31 % · 1 above limit','76 %','max 9°','Partial samples','Measured section','All limits hold, with the smallest oxygen margin of the three. No allowance for a slower pace.'],
  ['Return now, short path','0:29','33 %','77 %','max 14° · limit 12°','Partial samples','Measured section','Seven minutes faster and more oxygen on arrival. Crosses 120 m steeper than the configured walking limit.'],
  ['Finish sampling, then return','0:48','27 % · limit 30 %','74 %','max 9°','Full sample set, measured section','None','Completes the objective. EV2 arrives below the configured oxygen limit.'],
]
function EvaTradeoff({ props, decide }: { props:MissionProps; decide:(outcome:string,route:string)=>void }) {
  const [choice,setChoice]=useState<(typeof routeIds)[number]>('A')
  return <div className="mission-canvas"><RouteMap regionId={props.region.id} visible={false}/>
    <Panel name="EVA trade-off" className="eva-tradeoff">
      <header><div><span className="caption">Scenario</span><h1>{props.mission.closure||'EV2 oxygen regulator fault at stop 1'}</h1><p className="mono muted">Reported 01:31 · 1.8 km from base · stop 1 sampling 70 % complete</p></div>
        <Matrix headers={['Crew','Oxygen','Limit','Max slope','']} rows={[[ 'EV1','81 %','≥ 30 %','12°',<Badge>SIM</Badge> ],['EV2',<Warn>38 %</Warn>,'≥ 30 %','12°',<Badge>SIM</Badge>]]}/></header>
      <div className="tradeoff-grid">{tradeoffs.map(([label,duration,oxygen,ev1,terrain,kept,lost,tradeoff],i)=><article key={label} data-selected={choice===routeIds[i]}>
        <button className="section-heading" aria-pressed={choice===routeIds[i]} onClick={()=>setChoice(routeIds[i])}><strong>{routeIds[i]} · {label}</strong><span className={'mono status-text '+(i?'bad':'good')}>{i?'1 LIMIT EXCEEDED':'WITHIN LIMITS'}</span></button>
        <Readouts rows={[[ 'Time to base',<span className="mono">{duration}</span> ],['EV2 oxygen at base',<span className={'mono '+(i===0?'caution':i===2?'bad':'')}>{oxygen}</span>],['EV1 oxygen at base',<span className="mono">{ev1}</span>],['Terrain',<span className={'mono '+(i===1?'bad':'')}>{terrain}</span>],['Science kept',kept],['Science lost',lost]]}/>
        <Section title="Trade-off"><p>{tradeoff}</p></Section>
      </article>)}</div>
      <footer><span className="caption">Model assessment <Badge>CALC</Badge></span><p>Only A satisfies every configured limit. The system does not choose. Simulated values and rules set by the operator. For scenario review only.</p>
        <span className="caption">Operator decision</span><Segmented items={routeIds} value={choice} onChange={setChoice} label="Operator decision"/>
        <Action primary disabled={choice!=='A'} onClick={()=>decide('Direct return',choice)}>Confirm {choice}</Action><Action onClick={()=>props.go('monitor')}>Close</Action></footer>
    </Panel>
  </div>
}

export function Monitoring(props:MissionProps) {
  const { mission,view,profile,update,go,region }=props
  const eva=profile==='Astronaut'
  const [progress,setProgress]=useState(60.896)
  const [playing,setPlaying]=useState(false)
  const [library,setLibrary]=useState(view==='')
  const [modules,setModules]=useState([...defaultModules])
  const [presets,setPresets]=useState<Record<string,string[]>>(presetsDefault)
  const [preset,setPreset]=useState('Rover Mission Control')
  const [closure,setClosure]=useState('')
  const dialog=useRef<HTMLDialogElement>(null)
  useEffect(()=>{if(!playing)return;const timer=setInterval(()=>setProgress(p=>Math.min(100,p+.31)),120);return()=>clearInterval(timer)},[playing])
  useEffect(()=>{if(progress>=100)setPlaying(false)},[progress])
  useEffect(()=>{if(view==='playback')setLibrary(false)},[view])
  function decide(decision:string,route=mission.route) {
    const revision = mission.revision + 1
    const plan = eva ? 'EVA-A' : 'R-' + String(9 + revision).padStart(3,'0')
    const change = mission.closure || (eva ? 'EV2 oxygen regulator fault at stop 1' : 'Obstruction on route ' + mission.route + ' · simulated')
    const entry = {number:revision,run:plan,change,decision,route,task:mission.task}
    update({decision,route,revision,plan,closure:change,history:[entry,...mission.history]})
    go('analysis','record')
  }
  function report() {
    setClosure(eva?'Return corridor closure at stop 1':'Obstruction on route '+mission.route+' · simulated')
    dialog.current?.showModal()
  }
  const cameraProps={progress,setProgress,playing,setPlaying}
  if(view==='layout')return <LayoutEditor {...{modules,setModules,go,presets,preset,setPreset}} savePreset={name=>{setPresets({...presets,[name]:[...modules]});setPreset(name)}}/>
  if(view==='salvage')return <Salvage props={props} decide={decide}/>
  if(view==='tradeoff'||eva&&view==='contingency')return <EvaTradeoff props={props} decide={decide}/>
  if(view==='contingency')return <RoverContingency props={props} decide={decide}/>
  const camera=<Camera {...cameraProps} eva={eva}/>
  const elapsed=timeCode(5530+Math.round((progress-60.9)*12))
  return <>
    {eva?<div className="mission-canvas eva-monitor">
      <RouteMap astronaut monitor regionId={region.id} progress={progress}/>
      <div className="eva-clock"><span className="caption">EVA elapsed</span><h1 className="mono">{elapsed}</h1><p className="mono"><span className="caution">back by 2:08 · margin 0:22</span>　·　 window closes 2:30　·　 limit 3:00</p></div>
      <Panel name="Crew resources" className="resource-bars right-dock">{[['Oxygen',Math.round(100-progress*.312)+' %','min 30 %',81],['Water','1.0 L','min 0.3 L',69],['Return','+0:22','plan +0:35',37]].map(([label,value,limit,amount],i)=><div key={label} className={i===2?'caution':''}><span className="caption">{label}</span><div className="v-bar"><i style={{height:amount+'%'}}/></div><strong className="large-mono">{value}</strong><small className="mono muted">{limit}</small><Badge>{i===2?'CALC':'EST'}</Badge></div>)}</Panel>
      {camera}
      <div className="glass eva-return"><span className="caption">To base</span><span className="mono">1.8 km · 0:36</span><Action onClick={report}>Contingency</Action></div>
    </div>:<div className="rover-monitor">
      <Panel name="Mission map" className="monitor-map">{modules.includes('Mission map')?<RouteMap monitor inset regionId={region.id} route={mission.route} progress={progress}/>:<Action onClick={()=>setModules([...modules,'Mission map'])}>Restore mission map</Action>}</Panel>
      {modules.includes('Camera feed')?camera:<Panel name="Camera module hidden" className="rover-camera striped"><Action onClick={()=>setModules([...modules,'Camera feed'])}>Restore camera</Action></Panel>}
      <div className="glass monitor-telemetry">
        {modules.includes('Power')&&<div><div className="section-heading"><span className="caption">Battery</span><Badge>SIM</Badge></div><strong className="large-mono">{Math.round(100-progress*.476)} %</strong> <span className="mono muted">280 W · +160 Wh</span></div>}
        {modules.includes('Progress')&&<div><div className="section-heading"><span className="caption">Progress</span><Badge>SIM</Badge></div><strong className="large-mono">{(Math.floor(progress*1.85)/100).toFixed(2)} km</strong> <span className="mono muted">of 1.85 · ETA 0:21</span></div>}
        {modules.includes('Components')&&<div><div className="section-heading"><span className="caption">Components</span><Badge>SIM</Badge></div><strong className="telemetry-label">Nominal</strong> <span className="muted">Drive · Nav · Comms</span></div>}
        <div><div className="section-heading"><span className="caption">Route</span><span className="muted">B, C stored</span></div><div className="section-heading"><strong className="telemetry-label">{mission.route}</strong><Action onClick={report}>Report change</Action></div></div>
      </div>
      <button className="library-toggle icon-button" title="Module library" aria-label="Module library" aria-expanded={library} onClick={()=>setLibrary(!library)}><GridFour size={16} weight="bold"/></button>
      {library&&<ModuleLibrary modules={modules} toggle={name=>setModules(modules.includes(name)?modules.filter(item=>item!==name):[...modules,name])} reset={()=>setModules([...defaultModules])}/>}
      {modules.some(name=>['Energy history','Weather','Terrain profile','Event log'].includes(name))&&<div className="extra-telemetry">
        {modules.filter(name=>['Energy history','Weather','Terrain profile','Event log'].includes(name)).map(name=><Panel name={name} key={name}><Section title={name}>{name==='Energy history'||name==='Terrain profile'?<RangeChart variant={name==='Energy history'?'energy':'slope'}/>:<p>{name==='Weather'?'6 m/s · τ 0.6 · −48 °C · SIM':mission.closure||'Playback started · no reported changes'}</p>}</Section></Panel>)}
      </div>}
    </div>}
    <dialog className="dialog" ref={dialog} aria-labelledby="closure-title"><form onSubmit={e=>{e.preventDefault();if(!closure.trim())return;update({closure:closure.trim(),decision:''});setPlaying(false);dialog.current?.close();go('monitor',eva?'tradeoff':'contingency')}}>
      <h2 id="closure-title">{eva?'Report a closure':'Report change'}</h2><label htmlFor="closure">What changed?</label><textarea id="closure" rows={3} required value={closure} onChange={e=>setClosure(e.target.value)}/>
      <div className="dialog-actions"><Action onClick={()=>dialog.current?.close()}>Cancel</Action><button className="button primary">{eva?'Report closure':'Review replan'}</button></div>
    </form></dialog>
  </>
}
