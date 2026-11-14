import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { MissionProps } from './mission'
import { Action, candidates, Panel, RangeChart, RouteMap } from './MissionUI'
import { Readouts, Section, Warn } from './RegionEvidence'
import { Badge, Segmented } from './ui'

const pages = [['Overview','overview'],['Terrain','terrain'],['Energy and power','energy'],['Radiation','radiation'],['Environment','environment'],['Route ranking',''],['Models','models'],['Evidence','evidence'],['Report','report']] as const
const recordPages = [pages[0],pages[5],pages[6],pages[4],['Mission record','record'] as const,pages[8]]
const modelRows = [
  ['Region match','ML · text match','—','OBS','—','Not in this run'],['Terrain cost','Deterministic','0.1','SIM','0.9 s','Done'],
  ['Pathfinding','Deterministic · Dijkstra','0.1','CALC','1.4 s','Done'],['Energy','Deterministic','0.1','CALC','1.1 s','Done'],
  ['Power','Deterministic','0.1','CALC','0.6 s','Done'],['Radiation','Deterministic','0.1','SIM','0.3 s','Done · dummy input'],
  ['Weather','ML · forecast','—','SIM','0.4 s','Done · dummy input'],['Component effects','Deterministic','—','N/A','—','Skipped · wind, dust unmodelled'],
  ['Route ranker','Rule · Pareto, then priority','0.1','CALC','0.2 s','Done'],
]
const trace = [
  '14:28:01 terrain cost 0.1 · SIM grid 288 × 180 · 0.9 s','14:28:02 pathfinding 0.1 · Dijkstra · 3 candidates · 1.4 s',
  '14:28:04 energy 0.1 · A 410 · B 455 · C 520 Wh · 1.1 s','14:28:05 power 0.1 · peak A 310 · B 335 · C 360 W · 0.6 s',
  '14:28:05 radiation 0.1 · EST · 0.3 s     weather SIM · 0.4 s','14:28:06 ranker 0.1 · A › B › C at criterion 1 · 0.2 s',
]
export const outcomes = ['Continue','Reroute','Alternate task','Defer','Direct return','No admissible route','Insufficient evidence','Search incomplete']

export function Matrix({ headers, rows, className='', onPick, selected }: {
  headers?: ReactNode[]; rows: ReactNode[][]; className?: string; onPick?: (index:number)=>void; selected?:number
}) {
  return <div className="table-scroll"><table className={'mission-table '+className}>
    {headers&&<thead><tr>{headers.map((key,i)=><th scope="col" key={i}>{key}</th>)}</tr></thead>}
    <tbody>{rows.map(([first,...rest],i)=><tr className={selected===i?'matrix-selected':undefined} key={i} onClick={onPick?()=>onPick(i):undefined}>
      <th scope="row">{onPick?<button onClick={event=>{event.stopPropagation();onPick(i)}} aria-pressed={selected===i}>{first}</button>:first}</th>{rest.map((v,j)=><td key={j}>{v}</td>)}
    </tr>)}</tbody>
  </table></div>
}
const Mono = ({ children }: { children: ReactNode }) => <span className="mono">{children}</span>

function Console({ view, go, onInspect }: { view:string; go: MissionProps['go']; onInspect:(i:number)=>void }) {
  const [input,setInput] = useState('')
  const [extra,setExtra] = useState('')
  return <div className="analysis-console glass mono"><div className="console-log muted">
    {view==='models'?<><p>› inspect pathfinding</p><p><b>pathfinding</b> 0.1 · graph 288 × 180 cells · 3 candidates · 1.4 s</p><p>› models --failed</p><p><b>component effects</b> skipped: wind and dust have no model, heating is computed in energy 0.1</p><p>› inputs --class SIM</p></>:<>
      <p>› run R-012</p><p><b>terrain</b> ok 0.9 s　 <b>energy</b> ok 1.1 s　 <b>power</b> ok 0.6 s　 <b>radiation</b> ok, SIM input　 <b>weather</b> ok, SIM input　 <b>ranker</b> ok 0.2 s</p>
      <p>› open analysis ranking</p><p><b>ranking</b> 3 routes · 5 hard constraints · Pareto front: A · priority rule not needed</p></>}
    {extra&&<p role="status">{extra}</p>}
  </div><form onSubmit={e=>{e.preventDefault();const command=input.trim().toLowerCase();if(command.startsWith('compare'))go('route','compare');else if(command.startsWith('inspect ')){const i=modelRows.findIndex(row=>row[0].toLowerCase()===command.slice(8));if(i>=0){onInspect(i);go('analysis','models')}else setExtra('Model unavailable in this local run')}else if(command==='record')go('analysis','record');else setExtra('Try compare A B, inspect energy, or record.');setInput('')}}><span className="accent">›</span><input aria-label="Analysis command" value={input} onChange={e=>setInput(e.target.value)} placeholder={view==='models'?'inspect energy':'compare A B'}/><Badge>/</Badge></form></div>
}

function RankingAnalysis({ props }: { props: MissionProps }) {
  const { region,go,mission }=props
  const constraints = [
    ['Energy','≤ 600 Wh',...candidates.map(c=>c.energy+' · pass')],['Peak power','≤ 400 W','310 · pass','335 · pass','360 · pass'],
    [<>Max slope <Badge>SIM</Badge></>,'≤ 15°',...candidates.map(c=>c.slope+' · pass')],['Restricted areas','none crossed','pass','pass','pass'],['Path connected','start to target','pass','pass','pass'],
  ]
  const objectiveRows = [['Energy margin','higher','+190 Wh','+145 Wh',<Warn>+80 Wh</Warn>],['Duration','lower','52 min','61 min','66 min'],[<>Path above 12° <Badge>SIM</Badge></>,'lower','0 m','140 m','60 m']]
  return <div className="analysis-columns ranking-analysis">
    <div><div className="section-heading"><h1>A dominates B and C</h1><strong className="large-mono accent">front: A</strong></div>
      <p className="mono muted intro-line">Rule: hard constraints, then Pareto comparison. Mission priority is used only if more than one route stays on the front.</p>
      <Matrix className="analysis-mono" headers={['Hard constraint','Limit','A','B','C']} rows={constraints}/>
      <Matrix className="analysis-mono spacing-table" headers={['Objective','Better','A','B','C','A against B, C']} rows={objectiveRows.map(row=>[...row,<span className="accent">Better than both</span>])}/>
    </div><aside>
      <div className="analysis-map glass"><RouteMap overview regionId={region.id} route={mission.route}/></div>
      <div className="section-heading side-caption"><span className="caption">Does the result hold</span><Badge>CALC</Badge></div>
      <Matrix className="analysis-side-table" rows={[[ 'Rolling resistance +20 %',<span className="good mono">A stays first</span> ],['Drive speed −20 %',<span className="good mono">A stays first</span>],['Slope error ±2°',<span className="caution mono">B fails slope limit</span>],['Real elevation model',<span className="caution mono">Not testable · terrain is SIM</span>]]}/>
      <div className="section-heading side-caption"><span className="caption">Inputs</span><Action onClick={()=>go('analysis','radiation')}>Provenance</Action></div>
      <Matrix className="analysis-side-table" rows={[[ 'CTX orthomosaic','6 m',<Badge>OBS</Badge> ],['Terrain grid','synthetic',<Badge>SIM</Badge>],['Rover profile '+mission.rover,'hypothetical',<Badge>SIM</Badge>],['Energy model','v0.1',<Badge>CALC</Badge>]]}/>
    </aside>
  </div>
}

function Models({ index, select, running }: { index:number; select:(i:number)=>void; running:boolean }) {
  const [name,kind,version,input,time,status]=modelRows[index]
  return <div className="analysis-columns models-columns">
    <Matrix selected={index} onPick={select} headers={['Model','Kind','Version','Input class','Time','Status']} rows={modelRows.map(([name,kind,version,input,time,status])=>[
      name,<span className="muted">{kind}</span>,<Mono>{version}</Mono>,<Badge>{input}</Badge>,<Mono>{time}</Mono>,<span className={running?'accent':status==='Done'?'good':status.startsWith('Done')?'caution':status.startsWith('Skipped')?'bad':'muted'}>{running?'Running':status}</span>,
    ])}/>
    <aside><div className="section-heading"><h1>{name}</h1><span className="mono good">{running?'RUNNING':status.toUpperCase()+' '+time}</span></div>
      <p className="mono muted intro-line">{index===2?'Dijkstra · directed graph · 8 neighbours · no corner cuts':kind+' · version '+version}</p>
      <span className="caption">Inputs</span><Matrix className="analysis-side-table" rows={index===2?[[ 'Edge cost','from Terrain cost 0.1',<Badge>SIM</Badge> ],['Start, target','map position',<Badge>OBS</Badge>],['Exclusions','slope > 15°, restricted',<Badge>SIM</Badge>]]:[[ 'Input class',<Badge>{input}</Badge> ],['Context','Local sample run']]}/>
      <div className="analysis-detail"><Section title="Parameters"><Readouts rows={index===2?[[ 'Cost weight',<Mono>time</Mono> ],['Alternatives',<Mono>3 · loopless</Mono>],['Grid cell',<Mono>5 m</Mono>]]:[['Execution',kind],['Version',version]]}/></Section>
      <Section title="Outputs"><Readouts rows={index===2?[[ 'Candidates',<Mono>A 1.85 km · B 2.20 km · C 2.10 km</Mono> ],['Passed to','Energy, Power, Route ranker'],['Warnings',<Warn>Terrain grid is synthetic</Warn>]]:[['State',status],['Run time',time]]}/></Section></div>
    </aside>
  </div>
}

function Environment({ props }: { props: MissionProps }) {
  const [provenance,setProvenance]=useState(true)
  return <div className="analysis-columns environment-columns"><div>
    <div className="section-heading"><h1>Radiation along route</h1><Badge>EST</Badge></div>
    <p className="mono muted intro-line">dose = surface rate × time on route · rate 0.67 mSv per day</p>
    <p className="caution environment-warning">Illustrative only. Rate measured at Gale, not validated for Jezero. Differences between routes are below what this method can resolve.</p>
    <Matrix className="analysis-mono" headers={['Route','Time exposed','Dose','Limit','Status']} rows={candidates.map(c=>[c.id,c.duration+' min','≈ '+c.dose+' mSv',<span className="muted">none configured</span>,<span className="muted">Not a constraint</span>])}/>
    <div className="section-heading weather-heading"><h1>Weather scenario</h1><Badge>SIM</Badge></div>
    <div className="weather-grid">{[['Wind','6 m/s'],['Dust opacity','τ 0.6'],['Air temperature','−48 °C'],['Forecast model','Dummy input']].map(([label,value],i)=><div key={label}><span className="caption">{label}</span><p className={i===3?'caution':'large-mono'}>{value}</p></div>)}</div>
    <div className="section-heading side-caption"><span className="caption">Effect on rover components</span><Badge>SIM</Badge></div>
    <Matrix headers={['Component','Driver','Modelled effect','Applied to run']} rows={[[ 'Heaters','Air temperature','+36 Wh on route A',<span className="good">Yes · by Energy 0.1, not Component effects</span> ],['Solar array','Dust opacity','None · LR-1 has no generation','—'],['Mobility','Wind',<Warn>No model</Warn>,'Not applied'],['Optics','Dust deposition',<Warn>No model</Warn>,'Not applied']]}/>
  </div><aside>{provenance?<Panel name="Provenance" className="provenance-panel">
    <div className="section-heading"><span className="caption">Provenance</span><button className="icon-button" aria-label="Close provenance" onClick={()=>setProvenance(false)}>×</button></div>
    <h2>Surface dose rate</h2>
    <Readouts rows={[[ 'Origin','MSL Curiosity · RAD instrument' ],['Class',<><Badge>OBS</Badge> rate · <Badge>EST</Badge> here</>],['Dataset',<Mono>PDS · MSL RAD</Mono>],['Measured at','Gale Crater'],['Applied at',<Warn>{props.region.name}</Warn>],['Resolution','Single site, no map'],['Time','Mission average'],['Method','Constant rate × exposure time'],['Model',<Mono>radiation 0.1</Mono>]]}/>
    <Section title="Known limits"><Readouts rows={[[ 'Site transfer',<Warn>Not validated for Jezero</Warn> ],['Solar events','Not included'],['Shielding, terrain','Not included'],['Uncertainty','Not quantified']]}/></Section>
  </Panel>:<Action onClick={()=>setProvenance(true)}>Provenance</Action>}</aside></div>
}

const reportContent = ['Mission and route summary','Constraint and ranking tables','Assumptions and limits','Calculation trace','Per-segment costs','Dataset provenance records']
function Report({ props }: {props:MissionProps}) {
  const { objective, mission, region, profile } = props
  const [checked,setChecked]=useState([true,true,true,true,false,false])
  const write = mission.writeTrace ? 'On' : 'Off'
  const reportTrace = mission.writeTrace ? trace : []
  const chosen=candidates.find(c=>c.id===mission.route)??candidates[0]
  const data = {
    summary:{objective, task:mission.task, region:region.name, profile, route:mission.route, run:mission.plan, revision:mission.revision, decision:mission.decision},
    criteria:candidates, limits:['Synthetic terrain grid','Dummy weather scenario','Illustrative dose','Local sample'], trace:reportTrace,
    segments:[{section:'approach',fraction:0.6},{section:'delta',fraction:0.4}], provenance:['Jezero CTX optical','Synthetic terrain','Operator profile'],
  }
  const keys = ['summary','criteria','limits','trace','segments','provenance'] as const
  function save(kind: 'JSON'|'Trace CSV') {
    const payload = kind==='JSON'?JSON.stringify(Object.fromEntries(keys.filter((_,i)=>checked[i]).map(key=>[key,data[key]])),null,2)
      :'step,message\n'+(checked[3]?reportTrace:[]).map((row,i)=>i+1+',"'+row.replaceAll('"','""')+'"').join('\n')
    const url=URL.createObjectURL(new Blob([payload],{type:kind==='JSON'?'application/json':'text/csv'}))
    const link=document.createElement('a');link.href=url;link.download='return-window-'+mission.plan+(kind==='JSON'?'.json':'.csv');link.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <div className="analysis-columns report-columns">
    <div className="report-panel">
      <p className="mono muted">Run {mission.plan} · generated Sol 214 14:28 · report 1 of 1</p>
      <h1>{profile==='Rover'?'Rover traverse':'Astronaut traverse'} to {region.id==='43'?'the Jezero delta front':region.name}</h1>
      <div className="report-sections">
        {checked[0]&&<><Section title="Mission"><Readouts rows={[[ 'Objective',objective.charAt(0).toUpperCase()+objective.slice(1) ],['Method','Sample rock'],['Region',region.name+' · '+region.coords],['Vehicle',<>{profile==='Rover'?mission.rover:'Crew 2'} <Badge>SIM</Badge></>]]}/></Section>
        <Section title="Selected route"><Readouts rows={[[ 'Route',mission.route+' · rank '+(candidates.indexOf(chosen)+1)+' of 3' ],['Distance, duration',<Mono>{profile==='Rover'?chosen.distance+' km · '+chosen.duration+' min':'3.5 km · 1:55'}</Mono>],['Energy',<Mono>{chosen.energy} of 600 Wh · +{600-chosen.energy}</Mono>],['Completion',<Mono>Sol 214 15:22 · plan 15:40</Mono>]]}/></Section></>}
        {checked[1]&&<Section title="Constraints"><Readouts rows={[[ 'Hard constraints',<span className="good mono">5 of 5 pass</span> ],['Ranked on','Energy margin, +45 Wh over B'],['Alternatives stored','B, C']]}/></Section>}
        {checked[2]&&<Section title="Assumptions and limits"><Readouts rows={[[ 'Terrain',<Warn>Synthetic grid · no elevation model</Warn> ],['Weather',<Warn>Dummy scenario</Warn>],['Radiation','Gale rate applied at Jezero'],['Not modelled','Wind on mobility, dust on optics']]}/></Section>}
      </div>
      {checked[3]&&<Section title="Calculation trace"><div className="trace-lines mono muted">{reportTrace.length ? reportTrace.map(row=><p key={row}>{row}</p>) : <p>Trace recording is off.</p>}</div></Section>}
      {checked[4]&&<Section title="Per-segment costs"><Readouts rows={[[ 'Approach', chosen.energy*.6+' Wh' ],['Delta',chosen.energy*.4+' Wh']]}/></Section>}
      {checked[5]&&<Section title="Dataset provenance records"><p>Jezero CTX optical · synthetic terrain · operator profile</p></Section>}
    </div>
    <aside><div className="export-actions inline-controls"><span className="caption">Export</span><Action onClick={()=>window.print()}>PDF</Action><Action onClick={()=>save('JSON')}>JSON</Action><Action onClick={()=>save('Trace CSV')}>Trace CSV</Action></div>
      <Section title="Contents"><div className="report-options">{reportContent.map((label,i)=><label key={label}><input type="checkbox" checked={checked[i]} onChange={e=>setChecked(checked.map((value,j)=>i===j?e.target.checked:value))}/>{label}</label>)}</div></Section>
      <Section title=""><div className="section-heading">Write trace while running <Segmented items={['On','Off'] as const} value={write} onChange={value=>props.update({writeTrace:value==='On'})} label="Write trace while running"/></div><Readouts rows={[[ 'Earlier runs',<span className="mono muted">R-009 · R-011</span> ]]}/></Section>
    </aside>
  </div>
}

function RecordView({ props }: {props:MissionProps}) {
  const {mission, profile, region, objective, go}=props
  const populated=Boolean(mission.decision)
  const [revision,setRevision]=useState(0)
  const [outcome,setOutcome]=useState(mission.decision||'Reroute')
  const route=populated?mission.route:'D'
  const confirmed = mission.history.length ? mission.history : [{
    number:4,run:'R-013',change:'Obstruction on route A · simulated',decision:'Reroute',route:'D',task:'Delta front',
  }]
  const rows = [
    ...confirmed.map((entry,i)=>[String(entry.number),entry.run,entry.change,entry.decision,entry.route,i===0?<span className="good">Current</span>:'Superseded']),
    ['3','R-012',profile==='Rover'?'Rover profile set to '+mission.rover:'Crew plan approved','Continue','A','Superseded'],
    ['2','R-011','Target moved 120 m east','Continue','A','Superseded'],['1','R-009','Mission created','No feasible route','—','Superseded'],
  ]
  return <div className="analysis-columns record-columns record-screen"><div>
    <Matrix headers={['Rev','Run','What changed','Outcome','Chosen','State']} rows={rows} selected={revision} onPick={setRevision}/>
    <div className="section-heading side-caption"><span className="caption">Revision {rows[revision][0]} against revision {rows[revision+1]?.[0]??rows[revision][0]}</span><Badge>CALC</Badge></div>
    {profile==='Rover'?<Matrix className="analysis-mono" headers={['','Rev 3 · A','Rev 4 · '+route,'Change']} rows={[
      ['Remaining distance','0.73 km','0.92 km',<Warn>+0.19</Warn>],['Energy margin at target','+190 Wh','+128 Wh',<Warn>−62</Warn>],
      ['Completion','Sol 214 15:22','Sol 214 15:31',<Warn>+0:09</Warn>],['Science tasks kept','1, 2','1, 2','none lost'],['Completed work','1.12 km','1.12 km','preserved'],
    ]}/>:<Matrix headers={['','Baseline','Current decision','Status']} rows={[
      ['Science task',mission.task,confirmed[revision]?.task??mission.task,confirmed[revision]?.decision==='Direct return'?'Deferred':'Preserved'],
      ['Return margin','+0:35',mission.decision==='Direct return'?'+0:14':'+0:09','SIM'],
      ['Decision','Continue',confirmed[revision]?.decision??rows[revision][3],'Recorded'],
    ]}/>}
    </div><aside>
      <Section title={'Snapshot · revision '+rows[revision][0]}><Readouts rows={[[ 'Region, pack',<>{region.name.replace(' Crater','')} · none <Badge>SIM</Badge></> ],['Profile',profile==='Rover'?'Rover '+mission.rover+' · rev 2':'Astronaut · Crew 2'],['Objective',objective.charAt(0).toUpperCase()+objective.slice(1)],['Position',<><Mono>map estimate</Mono> <Badge>SIM</Badge></>],['Limits',<Mono>{profile==='Rover'?'600 Wh · 400 W · 15°':'3:00 h · 0:30 reserve'}</Mono>],['Exclusions',revision===0?'1 blocked area · 15 m clearance':'No newly reported closures'],['Candidates searched',<Mono>4 · bounded</Mono>]]}/></Section>
      <Section title="Possible outcomes"><div className="chips">{outcomes.map(value=><button className="chip" key={value} aria-pressed={outcome===value} onClick={()=>setOutcome(value)}>{value}</button>)}</div></Section>
      <Section title=""><p className="muted">Results from revisions 1 to {Number(rows[0][0])-1} cannot be applied</p><div className="mission-actions fill"><Action onClick={()=>go('monitor','contingency')}>Open replan</Action><Action onClick={()=>go('analysis','report')}>Report</Action></div></Section>
    </aside>
  </div>
}

export function Analysis(props:MissionProps) {
  const {view,go,mission,update}=props
  const [model,setModel]=useState(2)
  const [running,setRunning]=useState(false)
  useEffect(()=>{if(!running)return;const timer=setTimeout(()=>{setRunning(false);update({plan:'R-014'})},1100);return()=>clearTimeout(timer)},[running])
  const consoleOpen = view===''||view==='models'
  return <div className={'paper-screen analysis-screen analysis-'+(view||'ranking')+(consoleOpen?' with-console':'')}>
    <nav className="analysis-nav" aria-label="Analysis sections">{(view==='record'||mission.decision?recordPages:pages).map(([name,key])=><button key={name} aria-current={view===key?'page':undefined} onClick={()=>go('analysis',key)}>{name} {name==='Radiation'||name==='Environment'?<Badge>{view==='radiation'&&name==='Radiation'?'EST':'SIM'}</Badge>:null}</button>)}
    {view==='overview'&&!mission.decision&&<button onClick={()=>go('analysis','record')}>Mission record</button>}</nav>
    <div className="analysis-main">
      {view==='models'?<><div className="export-actions"><Action primary disabled={running} onClick={()=>setRunning(true)}>{running?'Running…':'Rerun all'}</Action></div><Models index={model} select={setModel} running={running}/></>
      :view==='radiation'||view==='environment'?<Environment props={props}/>
      :view==='report'?<Report props={props}/>
      :view==='record'?<RecordView props={props}/>
      :view==='energy'||view==='terrain'?<div className="analysis-chart"><h1>{view==='energy'?'Energy and power':'Terrain along route'}</h1><RangeChart variant={view==='energy'?'energy':'slope'}/></div>
      :view==='evidence'?<><h1>Evidence</h1><p className="muted intro-line">CTX optical context · simulated terrain grid</p><a className="button" href={'#pack/'+props.region.id}>Site pack readiness</a></>
      :<RankingAnalysis props={props}/>}
    </div>
    {consoleOpen&&<Console view={view} go={go} onInspect={setModel}/>}
  </div>
}
