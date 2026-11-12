import { useMemo, useState } from 'react'
import { ArrowUpRight, BookOpen, Crosshair, Search, X } from 'lucide-react'
import { assessmentFor, byRegion, coordinatesLabel, featureTypes, labels, modes, readiness, regions, searchText } from './data'
import type { Mode, Profile, Region } from './data'
import { RatingBadge } from './RegionInspector'

type Sort = 'id'|'name'|Mode
export function Comparison({profile,ids,toggle,openMap,openResearch}:{profile:Profile;ids:string[];toggle:(id:string)=>void;openMap:(id:string)=>void;openResearch:(id:string)=>void}) {
  const [query,setQuery]=useState('')
  const [category,setCategory]=useState('')
  const [sort,setSort]=useState<Sort>('id')
  const [desc,setDesc]=useState(false)
  const [only,setOnly]=useState(false)
  const selected=ids.map(id=>byRegion.get(id)).filter((r):r is Region=>Boolean(r))
  const results=useMemo(()=>regions.filter(r=>(!only||ids.includes(r.id))&&(!category||r.featureType===category)&&(!query.trim()||searchText(r).includes(query.trim().toLowerCase()))).sort((a,b)=>{
    if (sort==='id'||sort==='name') return (desc?-1:1)*a[sort].localeCompare(b[sort])
    const x=assessmentFor(a,sort,profile).rating,y=assessmentFor(b,sort,profile).rating
    if (x===null || y===null) return Number(x===null)-Number(y===null)||a.id.localeCompare(b.id)
    return (desc?-1:1)*(x-y)||a.id.localeCompare(b.id)
  }),[query,category,ids,only,sort,desc,profile])
  function changeSort(value:Sort) {if(value===sort)setDesc(!desc);else {setSort(value);setDesc(value!=='id'&&value!=='name')}}
  const cells:[string,(r:Region)=>string][]=[
    ['Coordinates',r=>coordinatesLabel(r.geography.center,3)],['Scientific opportunity',r=>r.opportunity],
    ['Terrain and operations',r=>r.concern],['Data and observations',r=>r.documentationNote],
    ['Research uncertainty',r=>r.uncertainty],['Routing readiness',()=>readiness],
  ]
  return <main className="atlas-comparison">
    <div className="atlas-kicker">RESEARCH WORKBENCH / REGIONAL COMPARISON</div>
    <h1>Compare Mars regions</h1>
    <p className="atlas-note">Compare the survey’s traversal and science assessments. Equal levels are ties. Mixed assessments keep their original wording.</p>
    {selected.length>0&&<section className="atlas-selected-compare">
      <div className="atlas-panel-heading"><h2>Side by side</h2><span>{selected.length} selected</span></div>
      <div className="atlas-table-wrap"><table className="atlas-table side-table"><thead><tr><th scope="col">Evidence dimension</th>
        {selected.map(r=><th scope="col" key={r.id}><button className="quiet" onClick={()=>openMap(r.id)}>{r.name}<ArrowUpRight size={13}/></button><button className="icon-button" aria-label={`Remove ${r.name}`} onClick={()=>toggle(r.id)}><X size={14}/></button></th>)}
      </tr></thead><tbody>
        {modes.map(mode=><tr key={mode}><th scope="row">{labels[mode]}</th>{selected.map(r=><td key={r.id}><RatingBadge region={r} mode={mode} profile={profile}/><p>{assessmentFor(r,mode,profile).original||assessmentFor(r,mode,profile).note||'Unknown'}</p></td>)}</tr>)}
        {cells.map(([label,get])=><tr key={label}><th scope="row">{label}</th>{selected.map(r=><td key={r.id}>{get(r)||'Not specified in extracted fields'}</td>)}</tr>)}
      </tbody></table></div>
    </section>}
    <section>
      <div className="atlas-panel-heading"><h2>Research registry</h2><span>{results.length} entries</span></div>
      <div className="atlas-compare-controls">
        <label className="atlas-search"><Search size={15}/><input aria-label="Search comparisons" placeholder="Search comparisons…" value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <label>Feature type <select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All types</option>{featureTypes.map(c=><option key={c}>{c}</option>)}</select></label>
        <label><input type="checkbox" checked={only} onChange={e=>setOnly(e.target.checked)}/> Selected only</label>
      </div>
      <div className="atlas-table-wrap"><table className="atlas-table registry-table">
        <thead><tr><th scope="col">Compare</th>{(['id','name'] as const).map(key=><th scope="col" aria-sort={sort===key?(desc?'descending':'ascending'):undefined} key={key}><button onClick={()=>changeSort(key)}>{key==='id'?'ID':'Region'} {sort===key?(desc?'↓':'↑'):''}</button></th>)}
          <th scope="col">Category</th>{modes.map(mode=><th scope="col" aria-sort={sort===mode?(desc?'descending':'ascending'):undefined} key={mode}><button onClick={()=>changeSort(mode)}>{labels[mode]} {sort===mode?(desc?'↓':'↑'):''}</button></th>)}
          <th scope="col">Terrain challenge</th><th scope="col">Science opportunity</th><th scope="col">Available evidence</th><th scope="col">Limitations</th><th scope="col">Open</th></tr></thead>
        <tbody>{results.map(r=><tr key={r.id}><td><input type="checkbox" aria-label={`Compare ${r.name}`} checked={ids.includes(r.id)} onChange={()=>toggle(r.id)}/></td>
          <td>{r.id}</td><th scope="row">{r.name}</th><td>{r.featureType}</td>{modes.map(mode=><td key={mode}><RatingBadge region={r} mode={mode} profile={profile}/><p>{assessmentFor(r,mode,profile).original||assessmentFor(r,mode,profile).note||'Unknown'}</p></td>)}
          <td>{r.concern||'Not specified'}</td><td>{r.opportunity||'Not specified'}</td><td>{r.documentationNote||'Not specified'}</td><td>{r.uncertainty||'See full survey'}</td>
          <td><button className="icon-button" aria-label={`Map ${r.name}`} onClick={()=>openMap(r.id)}><Crosshair size={14}/></button><button className="icon-button" aria-label={`Research ${r.name}`} onClick={()=>openResearch(r.id)}><BookOpen size={14}/></button></td>
        </tr>)}</tbody></table></div>
    </section>
  </main>
}
