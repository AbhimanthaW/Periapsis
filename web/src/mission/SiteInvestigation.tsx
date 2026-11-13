import { useCallback, useEffect, useState } from 'react'
import { describeFailure, getEvidence } from './api'
import type { CapabilityAssessment, EvidenceResponse } from './api'
import { describeReason, metres, percent } from './format'
import { SiteMap } from './SiteMap'
import { configuredSite } from './site'
import type { SiteDescriptor } from './site'

type EvidenceState =
  | { state: 'loading' }
  | { state: 'not_configured'; message: string }
  | { state: 'unavailable'; reason: string }
  | { state: 'loaded'; data: EvidenceResponse }

function useEvidence() {
  const [evidence, setEvidence] = useState<EvidenceState>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setEvidence({ state: 'loading' })
    getEvidence(controller.signal).then(result => {
      if (result.ok) setEvidence({ state: 'loaded', data: result.data })
      else if (result.kind === 'http' && result.status === 503 && result.error?.error === 'EVIDENCE_NOT_CONFIGURED') {
        setEvidence({ state: 'not_configured', message: result.error.message })
      } else setEvidence({ state: 'unavailable', reason: describeFailure(result) })
    }, () => {})
    return () => controller.abort()
  }, [attempt])
  return [evidence, useCallback(() => setAttempt(value => value + 1), [])] as const
}

const provenanceLabel: Record<string, string> = {
  provenance_unverified: 'Provenance unverified',
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

function EvidencePanel({ data }: { data: EvidenceResponse }) {
  const { result } = data
  const fallbackSpecs = new Map(result.query.fallbacks.map(spec => [spec.id, spec]))
  return (
    <div className="mission-evidence">
      <div className="mission-provenance" role="note">
        <span className="mission-badge mission-badge-warn">{data.classification}</span>
        <span>{provenanceLabel[data.classification] ?? data.classification} · {data.context.replaceAll('_', ' ')}</span>
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

function EvidenceBody({ site, evidence, retry }: { site: SiteDescriptor; evidence: EvidenceState; retry: () => void }) {
  if (evidence.state === 'loading') return <p role="status" className="mission-muted">Loading evidence…</p>
  if (evidence.state === 'not_configured') return (
    <div className="mission-callout" role="status">
      <h3>Evidence not configured</h3>
      <p className="mission-muted">Start the planning service with this site's evidence package and query. Expected package <code>{site.evidence.package_id}@{site.evidence.package_version}</code>.</p>
    </div>
  )
  if (evidence.state === 'unavailable') return (
    <div className="mission-callout mission-callout-fail" role="alert">
      <h3>Evidence unavailable</h3>
      <p className="mission-muted">{evidence.reason}</p>
      <button className="mission-button" onClick={retry}>Retry</button>
    </div>
  )
  const { package_id, package_version } = evidence.data.result
  if (package_id !== site.evidence.package_id || package_version !== site.evidence.package_version) return (
    <div className="mission-callout mission-callout-fail" role="alert">
      <h3>Evidence identity mismatch</h3>
      <p className="mission-muted">The service returned <code>{package_id}@{package_version}</code>. {site.label} expects <code>{site.evidence.package_id}@{site.evidence.package_version}</code>. The evidence is not shown.</p>
    </div>
  )
  return <EvidencePanel data={evidence.data}/>
}

function SimulationEntry({ onEnter }: { onEnter: () => void }) {
  return (
    <section className="mission-card mission-sim-entry">
      <p className="mission-kicker">Next</p>
      <p className="mission-muted">The Marswalk replay uses a synthetic fixture grid with its own coordinates. It is not drawn on this site.</p>
      <button className="mission-button mission-button-primary" onClick={onEnter}>Enter simulated Marswalk</button>
    </section>
  )
}

export function SiteInvestigation({ onEnterSimulation }: { onEnterSimulation: () => void }) {
  const [evidence, retry] = useEvidence()
  const selection = configuredSite

  if (selection.state !== 'configured') {
    const invalid = selection.state === 'invalid'
    return (
      <div className="mission-site mission-site-empty">
        <section className={`mission-card${invalid ? ' mission-warn' : ''}`}>
          <p className="mission-kicker">Site · {invalid ? 'invalid' : 'unset'}</p>
          <h1>{invalid ? `Unknown site “${selection.value}”` : 'No site selected'}</h1>
          <p className="mission-muted">{invalid
            ? 'VITE_RW_SITE does not match a registered site. No evidence or map context is shown.'
            : 'Primary site awaiting qualification and approval. Map context and evidence appear once a site is configured.'}</p>
          {evidence.state === 'loaded' && (
            <p className="mission-muted mission-small">The planning service has evidence <code>{evidence.data.result.package_id}@{evidence.data.result.package_version}</code> configured. It is not shown without a matching site.</p>
          )}
          {evidence.state === 'unavailable' && <p className="mission-muted mission-small">Evidence service: {evidence.reason}</p>}
        </section>
        <SimulationEntry onEnter={onEnterSimulation}/>
      </div>
    )
  }

  const { site } = selection
  const matched = evidence.state === 'loaded'
    && evidence.data.result.package_id === site.evidence.package_id
    && evidence.data.result.package_version === site.evidence.package_version
  const control = site.role === 'engineering_control'
  return (
    <div className="mission-site">
      <div className="mission-site-main">
        <header className="mission-site-header">
          <p className="mission-kicker">Site investigation{control && <span className="mission-badge mission-badge-warn">Engineering control</span>}</p>
          <h1>{site.label}</h1>
          {control && <p className="mission-muted">Engineering control only. Not the primary demo site.</p>}
        </header>
        {site.context
          ? <SiteMap asset={site.context}
            support={matched ? evidence.data.result.provenance.flatMap(item => item.footprints.flatMap(footprint => footprint.geometry ? [footprint.geometry] : [])) : []}
            query={matched ? evidence.data.result.query.geometry : undefined}/>
          : <p className="mission-callout mission-muted">No local map context is packaged for this site.</p>}
      </div>
      <aside className="mission-site-side" aria-label="Evidence">
        <section className="mission-card">
          <p className="mission-kicker">Evidence</p>
          <EvidenceBody site={site} evidence={evidence} retry={retry}/>
        </section>
        <SimulationEntry onEnter={onEnterSimulation}/>
      </aside>
    </div>
  )
}
