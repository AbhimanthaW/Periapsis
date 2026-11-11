import { useEffect, useState } from 'react'
import { ArrowUpRight, BookOpen, Crosshair, Layers3, Plus, X } from 'lucide-react'
import { atlasModelIds, assessmentFor, assessmentLabel, byRegion, coordinatesLabel, detailKeys, labels, modes, planningContext, profileLabels, ratingColor, readiness } from './data'
import type { Mode, Profile, Region, ResearchTable } from './data'
import type { Component } from '../schema'

const tabs = ['Overview','Terrain','Science','Data','Operations','Sources'] as const
type Tab = typeof tabs[number]
export function RatingBadge({region,mode,profile}: {region:Region;mode:Mode;profile:Profile}) {
  const {rating,original,note}=assessmentFor(region,mode,profile)
  const name=rating ? assessmentLabel(rating) : original ? 'Unclassified' : 'Unknown'
  return <span className="atlas-rating" title={original||note} style={{color:ratingColor(mode,rating)}}><i className={rating?'':'unknown'}/>{name}</span>
}
export function ResearchTableView({table}:{table:ResearchTable}) {
  return <div className="atlas-table-wrap"><table className="atlas-table">
    <thead><tr>{table.head.map((head,i)=><th scope="col" key={i}>{head}</th>)}</tr></thead>
    <tbody>{table.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell}</td>)}</tr>)}</tbody>
  </table></div>
}
export function SourceList({region}:{region:Region}) {
  const [copy,setCopy]=useState('')
  const core=region.sources.filter(source=>source.kind!=='Media proxy')
  const proxies=region.sources.filter(source=>source.kind==='Media proxy')
  return <div className="atlas-sources">
    <p className="atlas-note">The location is matched to the Gazetteer. Survey links retain their publisher and original attribution, with individual claims awaiting verification.</p>
    <div className="atlas-source"><a href={region.geography.gazetteerUrl} target="_blank" rel="noreferrer">IAU / USGS · {region.geography.gazetteerName} <ArrowUpRight size={13}/></a><small>Matched named-feature record</small></div>
    {core.map(source=><div className="atlas-source" key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}<ArrowUpRight size={13}/></a><small>{source.kind} · {new URL(source.url).hostname}</small></div>)}
    {!core.length&&<p className="atlas-note">No direct research links were extracted. See the archived source section for its original attribution text.</p>}
    {proxies.length>0&&<details><summary>Indirect image references ({proxies.length})</summary>
      <p className="atlas-note">Media proxy links are preserved as references. Image rights and underlying sources were not verified.</p>
      {proxies.map(source=><div className="atlas-source" key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}<ArrowUpRight size={13}/></a></div>)}
    </details>}
    <button className="button" onClick={()=>{void navigator.clipboard.writeText([region.geography.gazetteerUrl,...core.map(s=>s.url)].join('\n')).then(()=>setCopy('References copied.')).catch(()=>setCopy('Clipboard unavailable. The links remain selectable.'))}}>Copy citations</button>
    {copy&&<p className="atlas-note" role="status">{copy}</p>}
  </div>
}
function ModelLinks({components,profile}:{components:Map<string,Component>;profile:Profile}) {
  const ids=[...atlasModelIds.terrain,...atlasModelIds.science,...atlasModelIds.readiness,...atlasModelIds.pipeline,...(profile==='rover'?['rover-travel','rover-energy']:profile==='human'?['traverse','human-profile']:[])]
  return <details className="atlas-disclosure">
    <summary>Architecture and model references</summary>
    <p className="atlas-note">Relevant specifications. Regional inputs and model applicability remain unevaluated.</p>
    {ids.filter(id=>components.has(id)).map(id=><div key={id} className="atlas-source"><a href={`/architecture?component=${id}`}>{components.get(id)?.name}<ArrowUpRight size={13}/></a><small>Relevant · applicability not evaluated</small></div>)}
  </details>
}
export function RegionInspector({region,profile,components,compare,compared,locate,close,research,select,detail}: {
  region:Region;profile:Profile;components:Map<string,Component>;compared:boolean;compare:()=>void;
  locate:()=>void;close:()=>void;research:()=>void;select:(id:string)=>void;detail:()=>void;
}) {
  const [tab,setTab]=useState<Tab>('Overview')
  useEffect(()=>setTab('Overview'),[region.id])
  const section=detailKeys.find(key=>key===tab.toLowerCase())
  const context=planningContext(region,profile)
  const terrain=region.fields['dominant terrain'] || region.fields['surface category'] || region.fields['terrain type']
  return <aside className="atlas-inspector" aria-label="Region inspector">
    <header>
      <div className="atlas-kicker">REGION {region.id} <span>·</span> {region.featureType.toUpperCase()}</div>
      <button className="icon-button atlas-inspector-close" aria-label="Close region" onClick={close}><X size={16}/></button>
      <h2>{region.name}</h2>
      <p className="atlas-coordinate">{coordinatesLabel(region.geography.center,3)} · {region.geography.status}</p>
      <div className="atlas-inline">
        <button className="button" onClick={locate}><Crosshair size={14}/> Locate</button>
        <button className="button" aria-pressed={compared} onClick={compare}><Plus size={14}/>{compared?'Added to compare':'Compare'}</button>
        <button className="button" onClick={research}><BookOpen size={14}/> Full research</button>
      </div>
    </header>
    <nav aria-label="Region sections" className="atlas-region-tabs">
      {tabs.map(name=><button key={name} aria-pressed={tab===name} onClick={()=>setTab(name)}>{name}</button>)}
    </nav>
    <div className="atlas-inspector-body" key={tab}>
      {tab==='Overview'&&<>
        <div className="atlas-assessments">{modes.map(mode=>{
          const value=assessmentFor(region,mode,profile)
          return <div key={mode}><div><span>{labels[mode]}</span><RatingBadge region={region} mode={mode} profile={profile}/></div>
            <p>{value.original||value.note||'No explicit survey assessment extracted.'}</p></div>
        })}</div>
        <section><h3>Scientific overview</h3>{region.overview.map(paragraph=><p key={paragraph}>{paragraph}</p>)}</section>
        {region.opportunity&&<section><h3>Research opportunity</h3><p>{region.opportunity}</p></section>}
        <section><h3>Planning readiness</h3><div className="atlas-readiness"><i/>{readiness}</div>
          <p>Global display is available. A validated regional site pack and an operational solver are required for planning.</p>
          {context&&<details className="atlas-disclosure"><summary>Mission handoff context</summary>
            <dl className="atlas-keyvalues"><dt>Region ID</dt><dd>{context.regionId}</dd><dt>Mission profile</dt><dd>{profileLabels[profile]}</dd><dt>Site pack</dt><dd>None linked</dd><dt>Start and objectives</dt><dd>Not configured</dd></dl>
          </details>}
        </section>
        <section><h3>Scientific uncertainty</h3><p>{region.uncertainty || 'No dedicated uncertainty field was extracted. Consult the survey and verify local terrain support, resolution, and applicability before planning.'}</p></section>
        {region.related.length>0&&<section><h3>Related features</h3>{region.related.map(relation=><button key={relation.id} className="atlas-related" onClick={()=>select(relation.id)}>
          <span>{byRegion.get(relation.id)?.name}</span><small>{relation.relation}</small><ArrowUpRight size={13}/></button>)}</section>}
        <ModelLinks components={components} profile={profile}/>
      </>}
      {section&&<section>
        {section==='terrain'&&<><h3>Geographic context</h3><p>{region.location || region.featureType}</p>{terrain&&<p>{terrain}</p>}
          <p>{region.geography.note}</p>{!region.sections.terrain.length&&region.overview.slice(0,2).map(paragraph=><p key={paragraph}>{paragraph}</p>)}</>}
        {section==='science'&&region.opportunity&&<><h3>Primary opportunity</h3><p>{region.opportunity}</p></>}
        {section==='data'&&<>
          <h3>Available documentation</h3><p>{region.documentationNote || region.assessments.documentation.original || 'See survey references and the full research section.'}</p>
          {region.id==='43'&&<button className="button" onClick={detail}><Layers3 size={14}/> Show Jezero CTX imagery</button>}
        </>}
        {section==='operations'&&<><h3>Survey conditions</h3><p>Rover notes are provisional and location dependent. The active profile is {profileLabels[profile]}.</p><p>{region.concern || 'No primary operational concern was extracted.'}</p><p>{region.uncertainty}</p></>}
        {region.sections[section].map(paragraph=><p key={paragraph}>{paragraph}</p>)}
        {region.tables[section].map((table,index)=><details className="atlas-disclosure" key={index} open={index===0||undefined}>
          <summary>{table.title}</summary><ResearchTableView table={table}/>
        </details>)}
        <button className="quiet" onClick={research}><BookOpen size={14}/> Read full survey section</button>
      </section>}
      {tab==='Sources'&&<SourceList key={region.id} region={region}/>}
    </div>
  </aside>
}
