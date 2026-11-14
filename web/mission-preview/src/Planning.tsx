import { useEffect, useState } from 'react'
import { Cursor, Jeep, MapPin, Ruler, Stack, Users, Crosshair, Polygon, X, ArrowSquareOut } from '@phosphor-icons/react'
import type { MissionProps } from './mission'
import { Badge, IconButton, Tabs, Segmented } from './ui'
import { Readouts, Section, Warn } from './RegionEvidence'
import { Action, Bars, candidates, Panel, RangeChart, routeIds, RouteMap, Scale } from './MissionUI'

const crewTabs = ['Crew','Resources','Movement','Return'] as const
const resultStates = ['No route','Running','No feasible route','Result withheld','Run failed'] as const
const tasks = ['Sample layered rock at the delta front','Image bedding from a standoff viewpoint'] as const
const crewRows = [
  ['Pace on level ground','3.2 km/h','2.8 km/h'], ['Max walking slope','12°','10°'],
  ['Oxygen supply','8:00 h','8:00 h'], ['Oxygen minimum at base','30 %','30 %'],
  ['Water','1.5 L','1.5 L'], ['Food','600 kcal','600 kcal'], ['Max continuous EVA','3:00 h','2:30 h'],
]

function Crew({ initial, violation, limit, changeLimit }: { initial: (typeof crewTabs)[number]; violation?: boolean; limit: string; changeLimit: (value: string) => void }) {
  const [tab,setTab] = useState(initial)
  const [count,setCount] = useState(2)
  const data = tab==='Resources' ? [['Oxygen supply','8:00','h'],['Water','1.5','L'],['Food','600','kcal'],['EVA limit','3:00','h'],['Return reserve','0:30','h']]
    : tab==='Movement' ? [['Walking pace','2.8','km/h'],['Max walking slope',limit,'°']]
    : [['Minimum oxygen','30','%'],['Return reserve','0:30','h']]
  return <Panel name="Crew constraints" className={violation?'crew-review':'crew-controls left-dock'}>
    <Tabs items={crewTabs} value={tab} onChange={setTab} label="Crew settings">
      {tab==='Crew' ? <>
        <table className="mission-table crew-table"><thead><tr><th>Limit, operator-set</th>{Array.from({length:count},(_,i)=><th key={i}>EV{i+1}</th>)}</tr></thead>
          <tbody>{crewRows.map(([name,a,b])=><tr key={name}><th scope="row">{name}</th>{Array.from({length:count},(_,i)=><td className="mono" key={i}>{name==='Max walking slope'&&i===1?limit+'°':i?b:a}</td>)}</tr>)}</tbody></table>
        <div className="section-heading crew-footer"><span className="muted">Plan uses the stricter value in each row</span><span><Badge>SIM</Badge> <Action disabled={count===4} onClick={()=>setCount(count+1)}>Add crew</Action></span></div>
      </> : <div className="crew-inputs">
        {data.map(([name,value,unit])=><label key={name}><span>{name}</span>{name==='Max walking slope'?<input value={limit} onChange={e=>changeLimit(e.target.value)}/>:<input defaultValue={value}/>}<small className="mono muted">{unit}</small></label>)}
        <div className="section-heading muted">Operator scenario <Badge>SIM</Badge></div>
      </div>}
    </Tabs>
  </Panel>
}

function ReturnCard({ blocked, limit, onResolve, onEdit, showSegment, onUse, onReturns, running }: {
  blocked: boolean; limit: string; onResolve: () => void; onEdit: () => void
  showSegment: () => void; onUse: () => void; onReturns: () => void; running?: boolean
}) {
  return <Panel name="Return margin" className={'return-card '+(blocked?'':'right-dock')}>
    <Section title="Return margin" status={<Badge>CALC</Badge>}><div className="section-heading"><strong className="large-mono">+0:35</strong><span className={'mono status-text '+(blocked?'bad':'good')}>{blocked?'1 LIMIT EXCEEDED':'PASS 6/6'}</span></div></Section>
    <Section title=""><Readouts rows={blocked ? [
      ['Max slope on route',<span className="bad mono">11° · EV2 limit {limit}°</span>],['Where','Return leg, 140 m before stop 2'], ['Duration',<span className="mono">1:55 · within 2:30</span>],['Oxygen at base',<>76 % <Badge>EST</Badge></>],['Food','within allocation'],
    ] : [['Distance','3.5 km'],['Duration','1:55'],['Oxygen at return',<>76 % <Badge>EST</Badge></>],['Water at return',<>0.9 L <Badge>EST</Badge></>],['Max slope',<>9° <Badge>SIM</Badge></>]]}/></Section>
    {blocked ? <Section title="Resolve"><div className="vertical-actions"><Action primary onClick={onResolve}>Reroute return under {limit}°</Action><Action onClick={showSegment}>Show segment on map</Action><Action onClick={onEdit}>Edit EV2 limit</Action></div></Section>
      : <div className="mission-actions fill"><Action primary disabled={running} onClick={onUse}>Use plan</Action><Action onClick={onReturns}>Returns · 2</Action></div>}
  </Panel>
}

function ResultStates({ go, run }: {go: MissionProps['go']; run: () => void}) {
  const [start,setStart] = useState(false)
  const [target,setTarget] = useState(false)
  const [running,setRunning] = useState(true)
  return <div className="result-gallery">
    {resultStates.map((state,i)=><Panel key={state} name={state} className="result-example">
      <div className="section-heading"><span className={'caption '+([2,4].includes(i)?'bad':i===3?'caution':'')}>{state}</span>
        <span className="mono">{['','R-014 · 2.1 s','R-015','N/A','R-016'][i]}</span></div>
      {i!==1 && <h2>{['Place a start and a target','','3 candidates, all fail','Target is outside mapped data','Power model stopped'][i]}</h2>}
      {i===0 && <><div className="mission-actions fill"><Action onClick={()=>setStart(!start)}>{start?'Start set':'S'}</Action><Action onClick={()=>setTarget(!target)}>{target?'Target set':'T'}</Action></div><Section title=""><Readouts rows={[[ 'Profile','LR-1' ],['Region','Jezero Crater']]}/></Section><Action disabled={!start||!target} onClick={run}>Run</Action></>}
      {i===1 && <><progress max={100} value={running?50:0} aria-label="Run progress"/><Readouts rows={['Terrain cost','Pathfinding','Energy','Power','Radiation','Route ranker'].map((name,index)=>[name,<span className={'mono '+(index<3?'good':index===3?'accent':'muted')}>{running?['done','done','done','running','queued','waiting'][index]:'cancelled'}</span>])}/><Action onClick={()=>setRunning(!running)}>{running?'Cancel':'Restart'}</Action></>}
      {i===2 && <><Readouts rows={['energy −40 Wh','energy −95 Wh','slope 17° · limit 15°'].map((text,index)=>[routeIds[index],<span className="bad mono">{text}</span>])}/><Section title="Change one"><div className="vertical-actions"><Action onClick={()=>go('route','move-target')}>Move target</Action><Action onClick={()=>go('route','profiles')}>Reserve policy 40 %</Action><Action onClick={()=>go('route','profiles')}>Rover profile</Action></div></Section></>}
      {i===3 && <><Readouts rows={[[ 'CTX optical',<Warn>not covered</Warn> ],['Elevation',<Warn>not available</Warn>],['Models run','0 of 6']]}/><div className="vertical-actions"><Action onClick={()=>go('route','coverage')}>Show coverage layer</Action><Action onClick={()=>go('route','move-target')}>Move target</Action></div></>}
      {i===4 && <><p className="mono muted"><b>power</b> missing input: peak limit<br/><b>ranker</b> not started</p><Section title=""><Readouts rows={[[ 'Kept','Terrain, paths, energy' ],['Last good run','R-012']]}/></Section><div className="vertical-actions"><Action primary onClick={()=>go('route','profiles')}>Set peak limit</Action><Action onClick={()=>go('analysis','models')}>Open models</Action></div></>}
    </Panel>)}
  </div>
}

function Profiles({ mission, update, go }: MissionProps) {
  const [profiles,setProfiles] = useState(['LR-1','Perseverance','Curiosity'])
  const [selected,setSelected] = useState(mission.rover)
  const [reference,setReference] = useState('Perseverance')
  const [settings,setSettings] = useState<Record<string,string>>(mission.roverSettings??{})
  const cols = [[['Mass','420','kg'],['Wheels','6 × 0.40','m'],['Max slope','15','°'],['Drive speed','0.60','m/s'],['Payload','Sample cache','']], [['Capacity','1000','Wh'],['Reserve policy','40','%'],['Generation','0','W'],['Peak limit','400','W']]]
  return <Panel name="Rover profiles" className="profiles-panel">
    <aside><span className="caption">Profiles</span>{profiles.map((item,i)=><button key={item} aria-pressed={selected===item} onClick={()=>{setSelected(item);setSettings({})}}>
      <span>{item}<small>{['Hypothetical · logistics','Reference · Mars 2020','Reference · MSL'][i]||'Operator-defined'}</small></span><Badge>{i===1||i===2?'OBS':'SIM'}</Badge>
    </button>)}<button className="muted" onClick={()=>{const custom='Custom '+(profiles.length-2);setProfiles([...profiles,custom]);setSelected(custom);setSettings({})}}>New custom profile <span>+</span></button>
      <div className="striped missing-rover">No image for {selected}</div></aside>
    <section><div className="section-heading"><h1>{selected}</h1><span className="muted">Editable · operator-defined <Badge>SIM</Badge></span></div>
      <div className="profile-inputs">{cols.map((column,i)=><div key={i}><span className="caption">{i?'Energy and power':'Vehicle'}</span>
        {i===1&&<label>Battery type <select value={settings.battery||'Li-ion'} onChange={e=>setSettings({...settings,battery:e.target.value})}><option>Li-ion</option><option>MMRTG + Li-ion</option></select></label>}
        {column.map(([name,value,unit])=><label key={name}>{name}<input aria-label={name} value={settings[name]??value} onChange={e=>setSettings({...settings,[name]:e.target.value})}/><small className="mono muted">{unit}</small></label>)}
      </div>)}</div>
      <Section title="Loads on route A" status={<Badge>CALC</Badge>}><Bars data={[[ 'Drive',80,'330 Wh' ],['Instruments',11,'44 Wh'],['Heating',9,'36 Wh']]}/><Readouts rows={[[ 'Total', 'usable 600 Wh after 40 % reserve · 410 Wh' ]]}/></Section>
    </section>
    <section className="profile-compare"><div className="section-heading"><span className="caption">Compare on route A</span><select aria-label="Comparison rover" value={reference} onChange={e=>setReference(e.target.value)}>{profiles.filter(r=>r!=='LR-1').map(r=><option key={r}>{r}</option>)}</select></div>
      <table className="mission-table"><thead><tr><th/><th>{selected}</th><th>{reference}</th></tr></thead><tbody>
        {[['Mass',(settings.Mass??'420')+' kg', reference==='Curiosity'?'899 kg':'1,025 kg'],['Wheels','6 × 0.40 m','6 × 0.53 m'],['Power source',settings.battery||'Li-ion','MMRTG + Li-ion'],['Top speed','0.60 m/s','152 m/h'],['Duration, 1.85 km','52 min','12:10 h'],['Energy','410 Wh','N/A · no drive-power model'],['Result','PASS 5/5','Not assessed']].map(row=><tr key={row[0]}>{row.map((value,i)=><td className={i?'mono':'muted'} key={i}>{value}</td>)}</tr>)}
      </tbody></table>
      <footer><p className="caution">R-012 becomes stale on apply</p><div className="mission-actions fill"><Action primary onClick={()=>{update({rover:selected,plan:'R-014',roverSettings:settings});go('route','running')}}>Apply and rerun</Action><Action onClick={()=>go('route')}>Cancel</Action></div></footer>
    </section>
  </Panel>
}

function Compare({ primary, onChange, onClose }: {primary: string; onChange: (route:string)=>void; onClose: ()=>void}) {
  const [secondary,setSecondary] = useState('B')
  const a=candidates.find(c=>c.id===primary)??candidates[0]
  const b=candidates.find(c=>c.id===secondary)??candidates[1]
  const values = (c: typeof a) => [c.id,c.distance+' km',c.duration+' min',c.energy+' Wh',c.power+' W',c.slope+'°','≈ '+c.dose+' mSv','5/5',c.id==='A'?'On Pareto front':'Dominated by A']
  const delta = (n:number) => n>0?'+'+n:n.toString()
  return <Panel name="Route comparison" className="compare-dock"><div className="section-heading">
    <div className="inline-controls"><span className="caption">Compare</span><Segmented items={routeIds} value={a.id as typeof routeIds[number]} onChange={onChange} label="First route"/>
      <span className="muted">with</span><Segmented items={routeIds} value={secondary as typeof routeIds[number]} onChange={setSecondary} label="Second route"/></div>
    <div className="inline-controls"><span className="muted">Units kept separate · no combined score</span><Action onClick={onClose}>Close</Action></div>
  </div><div className="table-scroll"><table className="mission-table compare-table"><thead><tr>{['','Distance','Duration','Energy','Peak power','Max slope','Dose','Constraints','Ranked on'].map((label,i)=><th key={i}>{label}</th>)}</tr></thead>
    <tbody>{[values(a),values(b),[b.id+' − '+a.id,delta(Number((Number(b.distance)-Number(a.distance)).toFixed(2))),delta(b.duration-a.duration),delta(b.energy-a.energy),delta(b.power-a.power),delta(b.slope-a.slope),'not resolvable','equal',a.id===b.id?'Same route':'Criteria shown separately']].map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j} className={i===2&&j<6?'caution':j===7&&i<2?'good':''}>{v}</td>)}</tr>)}
    <tr>{['','CALC','CALC','CALC','CALC','SIM','EST','',''].map((v,i)=><td key={i}>{v&&<Badge>{v}</Badge>}</td>)}</tr></tbody>
  </table></div></Panel>
}

function Tasks({ objective, terms, mission, update, go, profile }: MissionProps) {
  const [extra,setExtra] = useState(false)
  return <Panel name="Science tasks" className="task-dock left-dock">
    <header><span className="caption">Objective</span><h1>{objective.charAt(0).toUpperCase()+objective.slice(1)}</h1>
      <div className="chips">{terms.map(term=><span className="chip active" key={term}>{term}</span>)}<Badge>EST</Badge></div></header>
    {tasks.map((task,i)=><section key={task}><button className="task-item" aria-pressed={mission.task===task||(i===0&&mission.task==='Delta front')} onClick={()=>update({task})}>
      <strong className="mono">{i+1}</strong><b>{task}</b><span className="good mono">ELIGIBLE</span>
    </button><Readouts rows={i===0?[[ 'Target',<>Delta front scarp base <Badge>SIM</Badge></> ],['Method',profile==='Rover'?'Contact sampling · needs arm and cache':'Contact sampling · crew station'],['Vehicle has',<span className="good">Sample cache</span>],['Dwell','25 min'],['Delivers','1 cached sample, context images'],['Station evidence',<Warn>Not reviewed · G6</Warn>]]
      :[['Target','Same scarp, remote view'],['Method','Remote imaging · needs line of sight'],['Dwell','8 min'],['Delivers','Oriented image set, no sample'],['Used when','Task 1 becomes infeasible']]}/></section>)}
    <section className="muted">— Investigate ice <span className="bad mono">NOT ELIGIBLE · no ice target in region</span></section>
    <footer className="section-heading"><span className="muted">{extra?'Order 1 then 2 then 3 · total dwell 38 min':'Order 1 then 2 · total dwell 33 min'}</span><div className="inline-controls"><Action onClick={()=>setExtra(!extra)}>{extra?'Remove stop':'Add stop'}</Action><Action primary onClick={()=>{if(mission.task==='Delta front')update({task:tasks[0]});go('route')}}>Run with tasks</Action></div></footer>
  </Panel>
}

export function Planning(props: MissionProps) {
  const {mission,region,profile,view,go,update} = props
  const astronaut = profile==='Astronaut'
  const [limit,setLimit] = useState('10')
  const [chart,setChart] = useState(true)
  const [marker,setMarker] = useState('')
  const [layer,setLayer] = useState(false)
  const [crewOpen,setCrewOpen] = useState(true)
  const [showSegment,setShowSegment] = useState(false)
  const chosen = candidates.find(c=>c.id===mission.route)??candidates[0]
  const run = () => {
    if (astronaut && Number(limit)<9) { go('route','constraints');return }
    const rawPeak=mission.roverSettings?.['Peak limit']
    if(!astronaut && rawPeak!==undefined && (!rawPeak.trim() || !Number.isFinite(Number(rawPeak)))) {go('route','states');return}
    if(!astronaut && rawPeak!==undefined && Number(rawPeak)<chosen.power) {go('route','states');return}
    go('route','running')
  }
  useEffect(()=>{
    if(view!=='running') return
    const timer=window.setTimeout(()=>{go('route')},1100)
    return ()=>window.clearTimeout(timer)
  },[view])
  function pick(id:string) {
    setMarker(id)
    if(routeIds.some(route=>route===id)) update({route:id})
  }
  function usePlan() {
    update({plan:astronaut?'EVA-A':mission.plan})
    go('monitor')
  }
  const violation = view==='constraints'
  if(view==='states') return <ResultStates go={go} run={run}/>
  if(violation) return <div className="constraint-gallery">
    <Crew initial="Crew" violation limit={limit} changeLimit={setLimit}/>
    <ReturnCard blocked limit={limit} onResolve={()=>{setShowSegment(false);go('route')}} onEdit={()=>{setLimit('12');go('route')}}
      showSegment={()=>{setShowSegment(true);go('route')}} onUse={usePlan} onReturns={()=>go('route')}/>
  </div>
  return <div className={'planner mission-canvas view-'+(view||'default')+(astronaut?' astronaut-planner':' rover-planner')}>
    <RouteMap regionId={region.id} astronaut={astronaut} compare={view==='compare'} tasks={view==='tasks'} route={mission.route} visible={view!=='profiles'} marker={marker} onPick={pick} coverage={layer||showSegment||view==='coverage'}/>
    {view==='profiles' ? <Profiles {...props}/> : view==='compare' ? <Compare primary={mission.route} onChange={route=>update({route})} onClose={()=>go('route')}/> : view==='tasks' ? <Tasks {...props}/> : <>
      <div className="planning-tools left-dock">
        <div className="glass toolstrip">
          <button className="desktop-tool" onClick={()=>astronaut?setCrewOpen(!crewOpen):go('route','profiles')}>{astronaut?<Users size={16}/>:<Jeep size={16}/>} {astronaut?'Crew 2':mission.rover} {!astronaut&&<Badge>SIM</Badge>}</button>
          {!astronaut&&<IconButton className={'icon-button desktop-tool '+(!marker?'chosen-tool':'')} title="Pointer" aria-label="Pointer" onClick={()=>setMarker('')}><Cursor size={16}/></IconButton>}
          <IconButton title={astronaut?'Habitat':'Start'} aria-label="Set start" onClick={()=>pick('S')}>{astronaut?'H':'S'}</IconButton>
          <IconButton title="Target" aria-label="Choose science tasks" onClick={()=>go('route','tasks')}>{astronaut?<Crosshair size={16}/>:'T'}</IconButton>
          <IconButton className="icon-button desktop-tool" title={astronaut?'Crew constraints':'Measure route'} aria-label={astronaut?'Crew constraints':'Measure route'} onClick={()=>astronaut?go('route','constraints'):setChart(!chart)}>{astronaut?<Polygon size={16}/>:<Ruler size={16}/>}</IconButton>
          <IconButton title="Coverage layer" aria-label="Coverage layer" aria-pressed={layer} onClick={()=>setLayer(!layer)}><Stack size={17}/></IconButton>
          <Action primary onClick={run}>Run</Action>
        </div>
        {!astronaut&&<div className="glass model-status"><span className="mono">{mission.plan}</span>{['Terrain','Energy','Power','Radiation','Weather','Ranker'].map((label,i)=><button key={label} onClick={()=>go('analysis','models')}><i className={i===3||i===4?'muted':'good'}>{i===3||i===4?'◌':'●'}</i> {label}</button>)}<button className="mono muted" onClick={()=>go('route','states')}>4.2 s</button></div>}
      </div>
      <div className="compact-model glass"><button onClick={()=>go('route','states')}><span className="good">●</span> 6 models <Badge>SIM 2</Badge></button></div>
      {astronaut ? <>
        {crewOpen&&<Crew initial="Resources" limit={limit} changeLimit={setLimit}/>}
        <ReturnCard blocked={false} limit={limit} onResolve={()=>go('route')} showSegment={()=>setShowSegment(true)} onEdit={()=>go('route','constraints')} running={view==='running'} onUse={usePlan} onReturns={()=>go('route','constraints')}/>
        <div className="eva-timeline glass">{[['Transit','0:34'],['Stop 1 · science','0:45'],['Return','0:36'],['Margin','0:35'],['Reserve','0:30']].map(([label,time])=><div key={label}>{label} <span className="mono muted">{time}</span><i/></div>)}<footer className="mono muted">0:00 <span>1:55 base</span><span>2:30 window closes</span><span>3:00 limit</span></footer></div>
      </> : <>
        <Panel name="Route results" className="route-results right-dock">
          <div className="route-selected"><div className="section-heading route-lead"><strong className="large-mono accent">{routeIds.indexOf(chosen.id as typeof routeIds[number])+1}</strong><div><h2>Route {chosen.id}</h2><span className="mono muted">{chosen.distance} km · {chosen.duration} min</span></div><span className="good mono status-text">PASS 5/5<span className="wide-only"> · SIM TERRAIN</span></span><span className="wide-only"><Badge>CALC</Badge></span></div>
            <Bars data={[[ 'Energy',chosen.energy/6,chosen.energy+' / 600 Wh' ],['Peak power',chosen.power/4,chosen.power+' / 400 W'],['Max slope',chosen.slope/15*100,chosen.slope+' / 15°']]}/>
            <div className="wide-only"><Section title="Better than B and C on"><Readouts rows={[[ ' ',<span className="mono accent">A　　 B　　 C</span> ],['Energy margin, Wh',<span className="mono">+190　+145　 +80</span>],['Duration, min',<span className="mono">52　　 61　　66</span>],['Path above 12°, m',<span className="mono">0　　 140　　60</span>]]}/></Section>
              <Section title=""><Readouts rows={[[ 'Planned completion','Sol 214 · 15:40' ],['Calculated',<>Sol 214 · 15:22 <Badge>CALC</Badge></>],['Path method','Dijkstra · 3 candidates']]}/></Section></div>
            <div className="mission-actions fill"><Action primary disabled={view==='running'} onClick={usePlan}>Use route</Action><span className="wide-only"><Action onClick={()=>go('route','compare')}>Compare</Action></span><span className="wide-only"><Action onClick={()=>go('analysis')}>Analysis</Action></span><span className="compact-only"><Action onClick={()=>go('route','compare')}>Why rank 1</Action></span></div>
          </div>
          {candidates.filter(c=>c!==chosen).map(c=><button className="other-route" key={c.id} onClick={()=>update({route:c.id})}><strong className="muted">{routeIds.indexOf(c.id as typeof routeIds[number])+1}</strong> Route {c.id} <span className="mono muted wide-only">{c.distance} km · {c.duration} min</span> <span className={c.id==='C'?'mono caution':'mono'}>+{600-c.energy} Wh</span></button>)}
        </Panel>
        {chart&&<Panel name="Energy along route" className="energy-dock"><div className="section-heading"><b>Energy along route <Badge>CALC</Badge></b><div><IconButton aria-label="Open analysis" onClick={()=>go('analysis')}><ArrowSquareOut size={14}/></IconButton><IconButton aria-label="Hide chart" onClick={()=>setChart(false)}><X size={14}/></IconButton></div></div><RangeChart/></Panel>}
        <button className="glass map-ident plan-ident" onClick={()=>setLayer(!layer)}>CTX optical <span className="mono muted">6 m native</span> <Badge>OBS</Badge>　│　 Terrain <Badge>SIM</Badge></button>
      </>}
      <Scale/>
      {view==='running'&&<Panel name="Running route models" className="run-progress"><span role="status">Running terrain, energy and power models…</span><progress/><Action onClick={()=>go('route')}>Cancel</Action></Panel>}
      {(view==='coverage'||view==='move-target'||showSegment)&&<div className="glass planner-message" role="status">{showSegment?'Return segment · 140 m before stop 2':view==='coverage'?'CTX coverage shown · optical context only':'Select the target marker to place the target'}</div>}
    </>}
  </div>
}
