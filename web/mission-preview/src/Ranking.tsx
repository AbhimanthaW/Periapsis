import { isExcluded, matchStrength, sorts } from './regions'
import type { Exclusion, Method, Profile, Region, Sort } from './regions'
import { Badge, regionHref, Segmented } from './ui'

interface RankingProps {
  ranked: Region[]
  selected: Region
  objective: string
  terms: string[]
  method: Method
  excludes: Exclusion[]
  sort: Sort
  profile: Profile
  select: (id: string) => void
  setSort: (sort: Sort) => void
}

function Level({ value, difficulty = false }: { value: string | number; difficulty?: boolean }) {
  if (typeof value === 'string') return <span className="muted">{value}</span>
  if (value === 0) return <span className="muted">No level</span>
  const label = value === 5 ? 'Very high' : value === 4 ? 'High' : 'Moderate'
  return <span className="level">
    <span className="level-bars" aria-hidden="true">{[1, 2, 3, 4, 5].map(step =>
      <span key={step} data-filled={step <= value} />)}</span>
    {label}{difficulty && ' difficulty'}
  </span>
}

export function Ranking({ ranked, selected, objective, terms, method, excludes, sort, profile, select, setSort }: RankingProps) {
  let position = 0
  return <div className="ranking">
    <div className="ranking-toolbar">
      <div className="ranking-objective">
        <span className="caption">Objective</span>
        <h1>{objective}</h1>
        <span className="chip active">{method}</span>
        {excludes.map(item => <span key={item} className="chip filter active">Exclude {item.toLowerCase()}</span>)}
      </div>
      <div className="sort-control">
        <span className="caption">Sort</span><Segmented items={sorts} value={sort} onChange={setSort} label="Sort regions" />
      </div>
    </div>
    <p className="ranking-scroll-hint muted">Scroll the table for all criteria and investigation links.</p>
    <div className="ranking-scroll" role="region" aria-label="Region ranking table" tabIndex={0}>
      <table className="ranking-table">
        <colgroup>
          {['rank', 'name', 'match', 'science', 'records', 'traversal', 'imagery', 'action'].map(column =>
            <col key={column} className={'col-' + column} />)}
        </colgroup>
        <thead><tr>
          <th scope="col">#</th><th scope="col">Region</th>
          <th scope="col">Matched text <Badge>EST</Badge></th>
          <th scope="col">Scientific interest</th><th scope="col">Documentation</th>
          <th scope="col">Traversal · {profile}</th><th scope="col">Local imagery</th>
          <th scope="col"><span className="sr-only">Open region</span></th>
        </tr></thead>
        <tbody>{ranked.map(region => {
          const excluded = isExcluded(region, excludes)
          const active = region.id === selected.id
          const rank = excluded ? '—' : ++position
          return <tr key={region.id} className={active ? 'selected' : ''} data-excluded={excluded}
            onClick={() => { if (!excluded) select(region.id) }}>
            <td className="mono muted">{rank}</td>
            <th scope="row">{excluded ? region.name : <button type="button" aria-pressed={active}
              onClick={event => { event.stopPropagation(); select(region.id) }}>{region.name}</button>}</th>
            <td>{excluded ? <span className="caution">Excluded · {region.exclusion?.toLowerCase()}</span>
              : <span className={`mono ${matchStrength(region, terms) > 0 ? 'accent' : 'muted'}`}>“{region.phrase}”</span>}</td>
            <td><Level value={region.science} /></td>
            <td><Level value={typeof region.records === 'string' ? (region.records === 'No level' ? region.records : region.records + ' · no level') : region.records} /></td>
            <td><Level value={region.traversal[profile]} difficulty /></td>
            <td className={`mono ${region.id === '43' ? '' : 'muted'}`}>{region.id === '43' ? 'CTX 6 m' : '—'}</td>
            <td>{!excluded && <a href={regionHref(region.id)} className="button mono"
              aria-label={`Investigate ${region.name}`}>Investigate</a>}</td>
          </tr>
        })}</tbody>
      </table>
    </div>
    <footer className="ranking-footer mono muted">
      <span title="Local sample rows from the 56-entry reference registry">{ranked.length} of 56 · registry 2026-11-08 · survey levels are provisional</span>
      <span>Criteria are shown separately and never summed</span>
    </footer>
  </div>
}
