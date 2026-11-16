import { useCallback, useEffect, useState } from 'react'
import { describeFailure, getRegionEvidence } from './api'
import type { CapabilityAssessment, EvidenceResponse, RegionEvidence } from './api'
import { describeReason, metres, percent } from './format'
import { SiteMap } from './SiteMap'
import { contextFor, pinnedSite } from './site'
import { assessmentFor, assessmentLabel, coordinatesLabel, profileLabels, regions } from '../atlas/data'
import type { Profile, Region } from '../atlas/data'

type EvidenceState =
  | { state: 'loading' }
  | { state: 'unavailable'; reason: string }
  | { state: 'loaded'; data: RegionEvidence }

function useRegionEvidence(regionId: string) {
  const [evidence, setEvidence] = useState<EvidenceState>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setEvidence({ state: 'loading' })
    getRegionEvidence(regionId, controller.signal).then(result => {
      if (result.ok && result.data.region_id === regionId) setEvidence({ state: 'loaded', data: result.data })
      else setEvidence({
        state: 'unavailable',
        reason: result.ok ? 'The service returned evidence for a different region.' : describeFailure(result),
      })
    }, () => {})
    return () => controller.abort()
  }, [regionId, attempt])
  return [evidence, useCallback(() => setAttempt(value => value + 1), [])] as const
}

type Spec = EvidenceResponse['result']['query']['requested']

function Requirement({ spec }: { spec: Spec }) {
  return <>{spec.requirements.map(requirement => (
    <span key={requirement.variable}>
      {requirement.variable}
      {requirement.product_classes?.length ? ` · ${requirement.product_classes.join(', ')}` : ''}
      {requirement.max_native_spacing_m != null ? ` · posting ≤ ${requirement.max_native_spacing_m} m` : ''}
    </span>
  ))}</>
}

function Assessment({ label, spec, assessment }: { label: string; spec: Spec | undefined; assessment: CapabilityAssessment }) {
  const allowed = assessment.eligible
  return (
    <section className="mission-assessment" data-eligible={allowed}>
      <header>
        <p className="mission-kicker">{label}</p>
        <span className={allowed ? 'mission-pass' : 'mission-fail'}>{allowed ? 'Supported' : 'Refused'}</span>
      </header>
      <h3><code>{assessment.id}</code></h3>
      {spec && <p className="mission-muted mission-requirement">Requires <Requirement spec={spec}/></p>}
      {!allowed && assessment.reason && <p className="mission-reason">{describeReason(assessment.reason)} <code>{assessment.reason}</code></p>}
      {assessment.variables.map(variable => (
        <div key={variable.variable} className="mission-variable">
          {!allowed && variable.reason && <p className="mission-muted">{variable.variable}: {describeReason(variable.reason)}</p>}
          <table className="mission-table">
            <thead><tr><th scope="col">Product</th><th scope="col">Posting</th><th scope="col">Support</th><th scope="col">Result</th></tr></thead>
            <tbody>{variable.candidates.map(candidate => (
              <tr key={candidate.product_id}>
                <td><code className="mission-wrap">{candidate.product_id}</code></td>
                <td>{metres(candidate.native_spacing_m)}</td>
                <td title={`Observed ${percent(candidate.observed_fraction)}`}>{percent(candidate.support_fraction)}</td>
                <td>{candidate.reasons.length
                  ? candidate.reasons.map(reason => <span key={reason} className="mission-fail-text">{describeReason(reason)} <code>{reason}</code></span>)
                  : <span className="mission-pass-text">Meets requirements</span>}</td>
              </tr>
            ))}</tbody>
          </table>
          <p className="mission-muted">Qualified coverage {percent(variable.qualified_fraction)}{variable.covered_by_single_product ? ' · single product' : ''}</p>
        </div>
      ))}
    </section>
  )
}

export function EvidencePanel({ data }: { data: EvidenceResponse }) {
  const { result } = data
  const fallbackSpecs = new Map(result.query.fallbacks.map(spec => [spec.id, spec]))
  return (
    <div className="mission-evidence">
      <div className="mission-provenance" role="note">
        <span className="mission-badge mission-badge-warn">{data.classification}</span>
        <span>Reviewed package and exact query</span>
      </div>
      <Assessment label="Requested calculation" spec={result.query.requested} assessment={result.requested}/>
      {result.fallbacks.map(fallback => (
        <Assessment key={fallback.id} label={result.supported_fallback_ids.includes(fallback.id) ? 'Supported fallback' : 'Fallback'}
          spec={fallbackSpecs.get(fallback.id)} assessment={fallback}/>
      ))}
      {result.provenance.map(({ dataset, product }) => (
        <section key={product.id} className="mission-product">
          <p className="mission-kicker">Product</p>
          <h3>{[dataset.mission, dataset.instrument].filter(Boolean).join(' · ') || dataset.id}</h3>
          <dl className="mission-facts">
            <dt>Product</dt><dd><code className="mission-wrap">{product.id}</code></dd>
            <dt>Native posting</dt><dd>{metres(product.native_spacing_m)}</dd>
            <dt>Effective scale</dt><dd>{metres(product.effective_scale_m)}</dd>
            <dt>Processing</dt><dd>{product.processing_level ?? '—'} · {product.readiness}</dd>
            <dt>Support extent</dt><dd>{product.support_extent_complete ? 'Complete' : 'Incomplete'}</dd>
            <dt>Observation extent</dt><dd>{product.observation_extent_complete ? 'Complete' : 'Incomplete'}</dd>
            <dt>Catalogue</dt><dd>{dataset.catalogue_status ?? '—'}</dd>
          </dl>
          {product.limitations?.length ? <ul className="mission-list">{product.limitations.map(item => <li key={item}>{item}</li>)}</ul> : null}
          {dataset.archive_url && <a href={dataset.archive_url} target="_blank" rel="noreferrer">Source archive</a>}
        </section>
      ))}
      <section className="mission-product">
        <p className="mission-kicker">Limits</p>
        <ul className="mission-list">{result.limitations.map(item => <li key={item}>{item}</li>)}</ul>
        <p className="mission-muted mission-small"><code>{result.package_id}@{result.package_version}</code> · {result.method_version}</p>
      </section>
    </div>
  )
}

export function RegionalContext({ data }: { data: Pick<RegionEvidence, 'anchor_cell_id' | 'cell_context'> }) {
  const context = data.cell_context
  return <section className="mission-card">
    <h2>Regional evidence</h2>
    <p><code>{data.anchor_cell_id}</code> · HEALPix Nside 128 cell for regional context. Local calculations use the exact reviewed query footprint.</p>
    {context ? <>
      <dl className="mission-facts mission-region-facts">
        <dt>Terrain documentation</dt><dd>{context.terrain.tier} · bounds {context.terrain.bounds.lower.toFixed(1)}–{context.terrain.bounds.upper.toFixed(1)}</dd>
        <dt>Science and environment documentation</dt><dd>{context.science_environment.tier} · bounds {context.science_environment.bounds.lower.toFixed(1)}–{context.science_environment.bounds.upper.toFixed(1)}</dd>
        <dt>MOLA gridded elevation at cell centroid</dt><dd>{metres(context.mola_elevation_m)}
          {context.mola_elevation_m !== null && context.mola_observation_count === 0 &&
            <span className="mission-post-note">Interpolated estimate with zero native observations</span>}
        </dd>
        <dt>MOLA observation count at native post</dt><dd>{context.mola_observation_count ?? 'Unknown'}</dd>
        <dt>Stereo coverage in the cell</dt><dd>{context.stereo_topography.status === 'unknown'
          ? 'Unknown' : `${percent(context.stereo_topography.observed_fraction)} catalogued · ${percent(context.stereo_topography.usable_fraction)} verified usable`}</dd>
      </dl>
      <p className="mission-muted">MOLA supplies regional topographic context. Documentation bounds reflect the released inventory and its gaps. Pack <code title={context.pack.sha256}>{context.pack.version}</code>.</p>
    </> : <p>Cell evidence unavailable. The sourced ranking pack is missing or has no record for this cell.</p>}
  </section>
}

function RegionSummary({ region, profile }: { region: Region; profile: Profile }) {
  const terrain = assessmentFor(region, 'traversal', profile)
  const science = assessmentFor(region, 'science', profile)
  return <section className="mission-card">
    <h2>Atlas research context</h2>
    <p>{coordinatesLabel(region.geography.center, 3)} · {region.geography.status} · {profileLabels[profile]}</p>
    <dl className="mission-facts">
      <dt>Survey terrain assessment</dt><dd>{terrain.rating ? assessmentLabel(terrain.rating) : 'Unclassified'}</dd>
      <dt>Survey scientific interest</dt><dd>{science.rating ? assessmentLabel(science.rating) : 'Unclassified'}</dd>
    </dl>
    {region.opportunity && <p>{region.opportunity}</p>}
    {region.uncertainty && <p className="mission-muted">{region.uncertainty}</p>}
    <p className="mission-muted">Qualitative survey and research leads. Local support and applicability require a separate evidence check.</p>
    <a href={region.geography.gazetteerUrl} target="_blank" rel="noreferrer">IAU / USGS feature record</a>
  </section>
}

export function SiteInvestigation({ region, profile, onChange, onEnterSimulation }: {
  region: Region
  profile: Profile
  onChange: (regionId: string) => void
  onEnterSimulation: () => void
}) {
  const [evidence, retry] = useRegionEvidence(region.id)
  const site = pinnedSite(region.id)
  const asset = contextFor(site)
  const data = evidence.state === 'loaded' ? evidence.data : null
  const local = data?.local_evidence
  const matched = local && site && local.query_sha256 === site.query_sha256
    && local.package_sha256 === site.package_sha256
    && local.result.package_id === site.package_id && local.result.package_version === site.package_version

  return <div className="mission-site">
    <div className="mission-site-main">
      <header className="mission-site-header">
        <p className="mission-kicker">Site investigation{site && <span className="mission-badge mission-badge-warn">
          {site.role === 'engineering_control' ? 'Engineering control' : 'Primary evidence demo'}
        </span>}</p>
        <h1>{region.name}</h1>
        <label>Atlas region <select value={region.id} onChange={event => onChange(event.target.value)}>
          {regions.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
      </header>
      {asset && <SiteMap asset={asset}
        support={matched ? local.result.provenance.flatMap(item => item.footprints.flatMap(footprint => footprint.geometry ? [footprint.geometry] : [])) : []}
        query={matched ? local.result.query.geometry : undefined}/>}
      <RegionSummary region={region} profile={profile}/>
      {data && <RegionalContext data={data}/>}
      <section className="mission-card">
        <h2>Model applicability</h2>
        <p><strong>Tactical routing withheld.</strong> No qualified local routing pack for {region.name}.</p>
        <p><strong>Live hazard assessment unavailable.</strong> No qualified feed is bound to this region. Keep local slope, trafficability, resource cost, and hazard exposure unevaluated.</p>
      </section>
    </div>
    <aside className="mission-site-side" aria-label="Evidence">
      <section className="mission-card">
        <h2>Local calculation evidence</h2>
        {evidence.state === 'loading' && <p role="status">Loading regional evidence…</p>}
        {evidence.state === 'unavailable' && <><p role="alert">{evidence.reason}</p><button className="mission-button" onClick={retry}>Retry</button></>}
        {data && (matched ? <EvidencePanel data={local}/>
          : site || local ? <p role="alert">Evidence identity mismatch. Expected the pinned package and exact query for {region.name}.</p>
          : <p>No reviewed local query is packaged for this region. Use regional context to choose an area for a stereo coverage search. Local elevation and tactical calculations are withheld.</p>)}
      </section>
      <section className="mission-card mission-sim-entry">
        <h2>Simulated Marswalk</h2>
        <p className="mission-muted">Rehearse the return-window decision on an independent synthetic grid with a fixed crew profile.</p>
        <button className="mission-button mission-button-primary" onClick={onEnterSimulation}>Enter simulated Marswalk</button>
        {import.meta.env.VITE_PACKAGED_RELEASE === '1' && <p><a href={'/?' + new URLSearchParams({ region: region.id, profile }) + '#monitor/rover/43/hazards'}>Open separate simulated hazard drill</a></p>}
      </section>
    </aside>
  </div>
}
