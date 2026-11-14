import type { ReactNode } from 'react'
import { Badge } from './ui'

export const candidates = [
  { id: 'A', distance: '1.85', duration: 52, energy: 410, power: 310, slope: 11, dose: '0.02' },
  { id: 'B', distance: '2.20', duration: 61, energy: 455, power: 335, slope: 14, dose: '0.03' },
  { id: 'C', distance: '2.10', duration: 66, energy: 520, power: 350, slope: 13, dose: '0.03' },
]
export const routeIds = ['A','B','C'] as const

export function Panel({ name, children, className = '' }: { name: string; children: ReactNode; className?: string }) {
  return <section aria-label={name} className={'glass mission-panel '+className}>{children}</section>
}
export function Action({ children, onClick, primary, disabled }: { children: ReactNode; onClick: () => void; primary?: boolean; disabled?: boolean }) {
  return <button type="button" className={'button'+(primary?' primary':'')} onClick={onClick} disabled={disabled}>{children}</button>
}
export function Bars({ data }: { data: [string, number, string][] }) {
  return <div className="mission-bars">{data.map(([name,amount,value]) => <div key={name}>
    <span className="muted">{name}</span><progress max={100} value={amount} aria-label={name}/><span className="mono">{value}</span>
  </div>)}</div>
}

type Point = [number,number]
export function RouteMap({ astronaut = false, compare = false, tasks = false, monitor = false, inset = false, overview = false,
  visible = true, regionId = '43', route = 'A', progress, onPick, marker, coverage }: {
  astronaut?: boolean; compare?: boolean; tasks?: boolean; monitor?: boolean; inset?: boolean; overview?: boolean
  visible?: boolean; regionId?: string; route?: string; progress?: number; onPick?: (id: string) => void
  marker?: string; coverage?: boolean
}) {
  const roverCurves: Point[][][] = [
      [[[705,505],[818,518],[949,587],[1060,600]]],
      [[[705,505],[743,420],[781,405],[852,409]],[[852,409],[940,409],[1034,488],[1060,600]]],
      [[[705,505],[714,556],[739,586],[800,610]],[[800,610],[900,658],[997,654],[1060,600]]],
      [[[705,505],[725,635],[870,708],[939,656]],[[939,656],[977,632],[1020,613],[1060,600]]],
    ]
  const roverRoutes = roverCurves.map(curves => 'M'+curves[0][0].join(' ') +
    curves.map(([,a,b,end])=>' C'+[a,b,end].flat().join(' ')).join(''))
  const crewRoutes = ['M720 520 C823 521 907 579 1060 600','M720 520 C758 596 865 657 1003 624 C1037 618 1048 612 1060 600']
  const compact = ['M136 312 C318 342 540 446 704 464','M136 312 C210 160 272 148 390 161 C556 173 660 285 704 464','M136 312 C159 426 229 459 315 492 C476 562 603 535 704 464']
  const docked = inset || overview
  const selectedIndex = route==='D'?3:Math.max(0, routeIds.findIndex(candidate => candidate===route))
  const trace = (t: number): Point => {
    const curves = roverCurves[selectedIndex]
    const at = t * curves.length
    const index = Math.min(curves.length-1,Math.floor(at))
    const local = at-index
    const [a,b,c,d] = curves[index]
    const inv = 1-local
    const mix = (axis: number) => a[axis]*inv**3 + 3*b[axis]*local*inv**2 + 3*c[axis]*local**2*inv + d[axis]*local**3
    return [mix(0),mix(1)]
  }
  const draw = (mobile: boolean) => {
    const crew = astronaut && !mobile
    const lines = mobile ? compact : crew ? crewRoutes : roverRoutes
    const nodes: { pos: Point; label: string; id: string; selected?: boolean }[] = mobile
      ? [{pos:[136,312],label:'T',id:'T'}, {pos:[704,464],label:'S',id:'S'}]
      : [{pos:crew?[720,520]:[705,505],label:tasks||crew?'1':'T',id:'T',selected:crew||tasks},
         {pos:[1060,600],label:crew?'H':'S',id:'S'},
         ...(crew ? [{pos:[900,640] as Point,label:'2',id:'B'}] : [
           {pos:[872,550] as Point,label:tasks?'2':compare?'A':'1',id:'A',selected:route==='A'&&!tasks},
           ...(!tasks ? [{pos:[860,410] as Point,label:compare?'B':'2',id:'B',selected:route==='B'},
           ...(!compare ? [{pos:[800,610] as Point,label:'3',id:'C',selected:route==='C'}] : [])] : []),
         ])]
    const [x,y] = progress === undefined ? [0,0] : crew ? [720,520] : trace(1-progress/100)
    const ahead = progress === undefined ? '' : Array.from({length:21},(_,i)=>trace((1-progress/100)*i/20).join(' ')).join(' L')
    const behind = progress === undefined ? '' : Array.from({length:21},(_,i)=>trace(1-progress/100+progress/100*i/20).join(' ')).join(' L')
    return <svg className={'route-overlay '+(mobile?'route-mobile':'route-desktop')} viewBox={mobile?'0 0 768 1024':inset?'670 383 420 332':overview?'560 342 650 398':'0 0 1440 900'}
      preserveAspectRatio={docked?'none':'xMidYMid slice'} aria-label="Simulated route map">
      <g transform={compare?'translate(0 -80)':undefined}>
        {lines.map((path,i) => {
          if ((i===3 && route!=='D') || (tasks && i>0) || (inset && progress!==undefined && i===selectedIndex)) return null
          const selected = selectedIndex === i
          const hot = crew ? monitor ? i===1 : i===0 : selected && !monitor
          const subdued = (compare && i === 2) || (inset && !selected)
          return <g key={path} opacity={subdued?.45:1}>
            {!subdued && (!mobile || hot) && !overview && <path d={path} stroke="#1e1712" strokeWidth={mobile?10:7} fill="none" />}
            <path d={path} fill="none" stroke={hot?'#ee945d':'#f4ede4'} strokeWidth={mobile?4:3}
              strokeLinecap="round" strokeDasharray={i===2?(mobile?'1 13':inset?'2 8':'1 6'):i===1?(mobile||inset?'16 13':crew&&monitor?'2 7':'10 7'):undefined}/>
          </g>
        })}
        {tasks && <><path d="M692 470 L872 550" fill="none" stroke="#f1e5d6" strokeDasharray="3 5"/><text x="759" y="491" fill="#fff" stroke="#201610" paintOrder="stroke" strokeWidth="3" fontSize="11">line of sight</text></>}
        {coverage && <rect x="570" y="300" width="590" height="400" fill="#89cfc51c" stroke="#89cfc5" strokeDasharray="12 8"/>}
          {inset && progress !== undefined && <><path d={'M'+ahead+' M'+behind} fill="none" stroke="#201610" strokeWidth="14"/><path d={'M'+behind} fill="none" stroke="#f4eade" strokeWidth="6"/><path d={'M'+ahead} fill="none" stroke="#e98d56" strokeWidth="6" strokeDasharray="3 19" strokeLinecap="round"/></>}
        {nodes.filter(node => !(inset||overview||crew&&monitor) || node.id==='S'||(node.id==='T'&&!(crew&&monitor))).map(({pos:[cx,cy],id,label,selected}) => <g key={id}
          role={onPick?'button':undefined} aria-label={onPick?(id==='S'?'Set start':id==='T'?'Set target':'Select route '+id):undefined}
          tabIndex={onPick?0:undefined} className={onPick?'route-node':''} aria-pressed={onPick && (selected||marker===id)}
          onClick={onPick?()=>onPick(id):undefined} onKeyDown={onPick?event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onPick(id)}}:undefined}>
          <circle cx={cx} cy={cy} r={mobile?18:inset?10:overview?9:id==='S'||id==='T'?13:11} fill={selected||marker===id?'#e4874f':'#0b0908'}
            stroke={selected?'#e4874f':'#f7efe6'} strokeWidth={mobile?3:2}/>
          <text x={cx} y={cy} dy=".34em" textAnchor="middle" fill={selected||marker===id?'#261710':'#fff'} fontSize={mobile?16:12} fontWeight="700">{overview?'':label}</text>
        </g>)}
        {progress !== undefined && !mobile && <g>
          <circle cx={x} cy={y} r="16" fill="#e4874f33" stroke="#e4874f" strokeWidth="1.7"/><circle cx={x} cy={y} r="5.5" fill="#e4874f"/>
        </g>}
        {crew && <g fill="#fff" stroke="#201610" paintOrder="stroke" strokeWidth="3" fontSize="12" fontWeight="600">
          <text x="879" y="530">{monitor?'':'out 0:34'}</text><text x="850" y="668">{monitor?'return 0:36 · 1.8 km':'return 0:36'}</text>
          {monitor && <><text x="746" y="514">EV1 · EV2</text><text x="746" y="530">Stop 1</text></>}
        </g>}
      </g>
    </svg>
  }
  return <div className={'mission-map'+(docked?' docked-map':'')}>
    <img src={regionId !== '43'?'./maps/mars-viking.webp':overview?'./maps/jezero-overview.webp':inset?'./maps/jezero-monitor.webp':'./maps/jezero-mission.webp'} alt={regionId==='43'?'Jezero CTX optical context':'Mars planetary context'}/>
    {visible && <>{draw(false)}{!docked && draw(true)}</>}
    {inset && <div className="map-ident glass">Position <Badge>SIM</Badge></div>}
  </div>
}
export function RangeChart({ variant = 'energy' }: { variant?: 'energy' | 'slope' | 'dose' }) {
  const top = variant === 'energy' ? '600' : variant === 'slope' ? '15°' : '0.03'
  return <svg className="range-chart" viewBox="0 0 410 142" role="img" aria-label={variant + ' along route'}>
    {[18,68,118].map((y,i) => <g key={y}><path d={`M38 ${y}H398`} stroke={i===0?'#bfa64e':'#c7b29d44'} strokeDasharray={i===0?'4 4':undefined}/><text x="30" y={y+3} textAnchor="end">{[top,variant==='energy'?'300':'','0'][i]}</text></g>)}
    <path d={variant==='slope'?'M38 96 L70 85 105 89 142 52 180 60 225 48 275 71 327 52 396 73':'M38 118 C140 97 244 60 393 40'} stroke="#e98c53" strokeWidth="2" fill="none"/>
    {variant==='energy' && <><path d="M38 118 L399 42 M38 118 L399 30" stroke="#e5d7c5" strokeDasharray="4 4" fill="none"/><text x="344" y="30" fill="#e7c95b">usable Wh</text></>}
    <text x="38" y="136">0</text><text x="195" y="136">1</text><text x="350" y="136">2 km</text>
  </svg>
}
export const Scale = () => <div className="mission-scale mono"><span/>500 m</div>
