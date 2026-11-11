import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Download, Search } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { atlasAsset, regions, searchText } from './data'
import type { Region } from './data'

let archiveRequest:Promise<string[]>|undefined
function loadArchive() {
  archiveRequest ??= fetch(atlasAsset('MARS_REGIONAL_RESEARCH.md')).then(response=>{
    if (!response.ok) throw new Error('The local research archive could not be opened.')
    return response.text()
  }).then(text=>text.split(/\r?\n/)).catch(error=>{archiveRequest=undefined;throw error})
  return archiveRequest
}
export function ResearchViewer({region,select,back}:{region:Region;select:(id:string)=>void;back:()=>void}) {
  const [lines,setLines]=useState<string[]>()
  const [error,setError]=useState('')
  const [query,setQuery]=useState('')
  const article=useRef<HTMLElement>(null)
  useEffect(()=>{
    let mounted=true
    void loadArchive().then(result=>{if(mounted)setLines(result)}).catch(error=>{if(mounted)setError(error.message)})
    return ()=>{mounted=false}
  },[])
  useEffect(()=>{
    article.current?.scrollTo({top:0})
  },[region.id])
  const current=regions.indexOf(region)
  const needle=query.trim().toLowerCase()
  const visible=regions.filter(r=>!needle || searchText(r).includes(needle) || lines?.slice(r.startLine-1,r.endLine).some(line=>line.toLowerCase().includes(needle)))
  const content=lines?.slice(region.startLine-1,region.endLine).join('\n')
  return <div className="atlas-research">
    <aside className="atlas-research-index" aria-label="Research contents">
      <div className="atlas-panel-heading"><h2>Research index</h2><span>{visible.length} / 56</span></div>
      <label className="atlas-search"><Search size={15}/><input aria-label="Search research" placeholder="Find in research…" value={query} onChange={e=>setQuery(e.target.value)}/></label>
      <div className="atlas-index-list">{visible.map(r=><button key={r.id} aria-current={r.id===region.id?'true':undefined} onClick={()=>select(r.id)}><span>{r.id}</span>{r.name}</button>)}</div>
    </aside>
    <article className="atlas-paper" ref={article} aria-label="Full regional research">
      <div className="atlas-paper-toolbar"><button className="button" onClick={back}><ArrowLeft size={14}/> Back to map</button>
        <a className="button" href={atlasAsset('MARS_REGIONAL_RESEARCH.md')} download><Download size={14}/> Original Markdown</a></div>
      <div className="atlas-kicker">SURVEY ARCHIVE / REGION {region.id} · LINES {region.startLine}–{region.endLine}</div>
      <h1>{region.name}</h1>
      <p className="atlas-note">Original survey section. Linked media and cited assessments retain their original context.</p>
      {error?<p role="alert">{error}</p>:content?
        <div className="atlas-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{
          a:({href,children})=><a href={href} target={href?.startsWith('#')?undefined:'_blank'} rel="noreferrer">{children}</a>,
          img:({src,alt})=><a href={src} target="_blank" rel="noreferrer">{alt || 'Linked image'}</a>,
          h2:({children})=><h2 id={String(children).toLowerCase().replace(/[^a-z0-9]+/g,'-')}>{children}</h2>,
        }}>{content}</Markdown></div>:<p role="status">Opening the local survey archive…</p>}
      <div className="atlas-paper-toolbar">
        <button className="button" disabled={!current} onClick={()=>select(regions[current-1].id)}><ArrowLeft size={14}/> Previous entry</button>
        <button className="button" disabled={current===regions.length-1} onClick={()=>select(regions[current+1].id)}>Next entry <ArrowRight size={14}/></button>
      </div>
    </article>
  </div>
}
