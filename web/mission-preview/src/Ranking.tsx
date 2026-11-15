import { CELL_COUNT, areaLabel, cellHref, cellSorts, conceptLabel, orderedAreas } from './cells'
import type { CellSelection, CellSort, RankingState } from './cells'
import type { Exclusion, Method } from './regions'
import { Segmented, globeHref } from './ui'
import { useState } from 'react'

const format = (n: number) => n.toLocaleString('en-US')
const PAGE_SIZE = 3

export function Ranking({ ranking, selected, objective, termsEdited, excludes, method, sort, select, setSort, retry }: {
  ranking: RankingState
  selected?: CellSelection
  objective: string
  termsEdited: boolean
  excludes: Exclusion[]
  method: Method
  sort: CellSort
  select: (cell: CellSelection) => void
  setSort: (sort: CellSort) => void
  retry: () => void
}) {
  const result = ranking.status === 'ready' ? ranking.result : undefined
  const data = orderedAreas(result?.areas ?? [], sort)
  const selectedIndex = data.findIndex(area => area.best_cell === selected?.id)
  const active = data[selectedIndex]
  const [page, setPage] = useState(() => Math.floor(Math.max(0, selectedIndex) / PAGE_SIZE))
  const lastPage = Math.max(0, Math.ceil(data.length / PAGE_SIZE) - 1)
  const p = Math.min(page, lastPage)
  const from = p * PAGE_SIZE

  return <div className="ranking cell-ranking">
    <div className="ranking-toolbar">
      <div className="ranking-objective">
        <span className="caption">Objective</span><h1>{objective}</h1>
        {result && <>
          <span className="caption">{termsEdited ? 'Targets read as' : 'Read as'}</span>
          {result.parse.concepts.map(item => <span key={item.id} className="chip active">{conceptLabel(item.id)}</span>)}
          {result.parse.negated.map(item => <span key={item.id} className="chip filter muted">Not {conceptLabel(item.id)}</span>)}
          {result.parse.demo.filter(item => !item.included).map(item => <span key={item.id} className="chip filter muted">{conceptLabel(item.id)} · demo only</span>)}
          {result.parse.unsupported.map(item => <span key={item.id} className="chip filter muted">{conceptLabel(item.id)} · unsupported</span>)}
          {!!result.parse.unknown.length && <span className="chip filter muted">Not recognised: “{result.parse.unknown.join(', ')}”</span>}
        </>}
      </div>
    </div>
    {ranking.status === 'loading' && <p role="status" className="muted">Searching the Mars cell grid…</p>}
    {ranking.status === 'error' && <div className="ranking-feedback">
      <p role="alert">{ranking.error}</p><button className="button compact" onClick={retry}>Retry ranking</button>
    </div>}
    {ranking.status === 'idle' && <p role="status" className="muted">Enter a science objective on the globe to search for areas.</p>}
    {result?.abstain && <p role="status" className="caution">Ranking withheld. No supported concepts were recognised.</p>}
    {result && !result.abstain && !data.length && <p role="status" className="caution">No matching areas for the evaluated concepts and filters.</p>}
    {data.length > 0 && <>
      <p className="ranking-scroll-hint muted">Scroll the table to see all record counts and method fit.</p>
      <div className="ranking-scroll" role="region" aria-label="Cell ranking table" tabIndex={0}>
        <table className="ranking-table">
          <colgroup>{['rank', 'name', 'cell', 'tier', 'score', 'concepts', 'ctx', 'hirise', 'dtm', 'crism', 'method'].map(column =>
            <col key={column} className={'col-' + column} />)}</colgroup>
          <thead><tr>
            {['#', 'Area', 'Best cell', 'Match tier', sort === 'Terrain' ? 'Terrain' : 'Match', 'Concepts found', 'CTX', 'HiRISE', 'DTM', 'CRISM', 'Method'].map(label =>
              <th key={label} scope="col">{label}</th>)}
          </tr></thead>
          <tbody>{data.slice(from, from + PAGE_SIZE).map(area => {
            const label = areaLabel(area)
            const current = area.best_cell === selected?.id
            const matches = Object.entries(area.concepts).filter(([, evidence]) =>
              evidence.state === 'Present' || (evidence.broader_support ?? 0) > 0)
            const choose = () => select({ id: area.best_cell, label: area.label ?? undefined })
            return <tr key={area.best_cell} className={current ? 'selected' : ''} onClick={choose}>
              <td className="mono muted">{area.rank}</td>
              <th scope="row"><button type="button" aria-pressed={current} aria-label={area.label ? label + ' · ' + area.best_cell : 'Select ' + area.best_cell}
                onClick={event => { event.stopPropagation(); choose() }}>{area.label ?? 'Unlabelled area'}</button>
                {area.sparse && <span className="sparse-label muted"> · sparse</span>}</th>
              <td className="mono">{area.best_cell}</td>
              <td className={area.tier === 'Direct' ? 'good' : area.tier === 'Partial' ? 'caution' : 'muted'}>{area.tier}</td>
              <td className="mono">{sort === 'Terrain'
                ? area.terrain_screening?.score == null ? '—' : area.terrain_screening.score + '%'
                : format(area.match_best)}</td>
              <td>{matches.map(([id, evidence]) => conceptLabel(id) + ' · ' + evidence.relation).join(', ') || '—'}</td>
              {(['ctx', 'hirise', 'dtm', 'crism'] as const).map(source =>
                <td className={`mono${area.records[source] === 0 ? ' muted' : ''}`} key={source}>{format(area.records[source])}</td>)}
              <td className={area.method === 'compatible' ? '' : 'caution'}>{area.method === 'compatible' ? 'Compatible' : 'Not established'}</td>
            </tr>
          })}</tbody>
        </table>
      </div>
    </>}
    <div className="ranking-notes">
      <section aria-label="Column definitions">
        <h2 className="caption">Columns from the service</h2>
        <dl className="metrics">
          <dt>Tier</dt><dd>Direct, partial or thematic</dd>
          <dt>Records</dt><dd>Product counts in the area</dd>
          <dt>Sparse</dt><dd>Flag when coverage is thin</dd>
        </dl>
      </section>
      <section aria-label="When nothing matches">
        <h2 className="caption">When nothing matches</h2>
        <dl className="metrics">
          <dt>Result</dt><dd className="caution">No areas returned</dd>
          <dt>Shown</dt><dd>Unsupported or unrecognised terms</dd>
        </dl>
      </section>
      <section aria-label="Ranking settings">
        <div className="cell-rank-sort">
          <span className="caption">Sort</span><Segmented items={cellSorts} value={sort}
            onChange={next => { setSort(next); setPage(0) }} label="Sort ranked areas" />
        </div>
        <dl className="metrics">
          <dt>Method</dt><dd>{method}</dd>
          <dt>Excluded</dt><dd>{excludes.join(', ') || 'None'}</dd>
          {sort === 'Terrain' && <><dt>Terrain</dt><dd>Mapped indicators only; local slope unassessed</dd></>}
        </dl>
      </section>
    </div>
    <footer className="ranking-footer mono muted">
      <span aria-live="polite">{data.length ? `${from + 1}–${Math.min(from + PAGE_SIZE, data.length)} of ${data.length} returned areas · ${format(CELL_COUNT)} cells in the grid` : 'HEALPix Nside 128 · east-positive coordinates'}</span>
      <div className="rank-actions">
        {lastPage > 0 && <>
          <button className="button compact" onClick={() => setPage(p - 1)} disabled={p === 0}>Previous</button>
          <button className="button compact" onClick={() => setPage(p + 1)} disabled={p === lastPage}>Next</button>
        </>}
        {active ? <a className="button compact primary" href={cellHref(active.best_cell)} aria-label={`Investigate ${areaLabel(active)}`}>Investigate</a>
          : <a className="button compact" href={globeHref}>Back to globe</a>}
      </div>
    </footer>
  </div>
}
