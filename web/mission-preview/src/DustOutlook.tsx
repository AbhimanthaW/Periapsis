import { useState } from 'react'
import { dustOutlook } from './dust'
import type { DustLoad, DustOutlook as Outlook } from './dust'
import { Badge, Metrics } from './ui'

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? null : value > 0 && value < 0.01 ? '<1%' : Math.round(value * 100) + '%'

function peakBin(values: (number | null)[]) {
  let best = -1
  values.forEach((value, i) => { if (value !== null && (best < 0 || value > (values[best] ?? -1))) best = i })
  return best
}

function Strip({ outlook, values, selected, onSelect }: {
  outlook: Outlook; values: (number | null)[]; selected: number; onSelect: (index: number) => void
}) {
  const top = Math.max(0.05, ...values.map(value => value ?? 0))
  return <div className="dust-strip" role="group" aria-label="Seasonal storm chance by solar longitude">
    {outlook.lsBins.map((ls, i) => {
      const value = values[i]
      return <button key={ls} type="button" aria-pressed={i === selected} disabled={value === null}
        aria-label={`Ls ${ls - 15} to ${ls + 15} degrees: ${value === null ? 'insufficient coverage' : percent(value)}`}
        onClick={() => onSelect(i)}>
        <span className="dust-bar" data-empty={value === null} style={{ height: value === null ? undefined : Math.max(2, (value / top) * 100) + '%' }} />
      </button>
    })}
  </div>
}

export function DustOutlookSection({ regionId, load = dustOutlook }: { regionId: string; load?: DustLoad }) {
  const region = load.kind === 'ready' ? load.outlook.regions[regionId] : undefined
  const [selected, setSelected] = useState(() => region ? peakBin(region.climatology) : -1)

  if (load.kind !== 'ready' || !region) {
    const message = load.kind === 'missing' ? 'Awaiting MDAD extraction'
      : load.kind === 'withheld' ? 'Withheld · archive grid review pending'
      : load.kind === 'invalid' ? 'Artifact rejected · ' + load.reason : 'Region not in artifact'
    return <section className="summary-section dust-summary" aria-label="Dust outlook">
      <div className="section-heading"><span className="caption">Dust outlook</span><Badge>N/A</Badge></div>
      <Metrics><dt>Status</dt><dd className="caution">{message}</dd></Metrics>
    </section>
  }

  const outlook = load.outlook
  const skilful = outlook.status === 'model_skilful'
  const index = selected >= 0 ? selected : 0
  const ls = outlook.lsBins[index]
  const baseline = percent(region.climatology[index])
  const years = outlook.marsYears.length ? `MY${outlook.marsYears[0]}–${outlook.marsYears[outlook.marsYears.length - 1]}` : ''

  return <section className="summary-section dust-summary" aria-label="Dust outlook">
    <div className="section-heading">
      <span className="caption">Dust outlook · next {outlook.horizonSols} sols</span>
      <Badge>EST</Badge>
    </div>
    {selected < 0 ? <Metrics><dt>Status</dt><dd className="caution">Insufficient historical coverage</dd></Metrics> : <>
      <Strip outlook={outlook} values={region.climatology} selected={index} onSelect={setSelected} />
      <div className="dust-axis mono muted"><span aria-hidden="true">Ls 0°</span>
        <span className="accent">Ls {ls - 15}–{ls + 15}°</span><span aria-hidden="true">360°</span></div>
      <Metrics>
        <dt title={outlook.definition}>Baseline</dt>
        <dd><span className="mono">{baseline}</span> <span className="muted">historical rate</span></dd>
        {skilful ? <>
          <dt title={outlook.scenarios.nearby}>Storm nearby</dt>
          <dd><span className="mono accent">{percent(region.nearby?.[index]) ?? '—'}</span> <span className="muted">model</span></dd>
          <dt title={outlook.scenarios.quiet}>Quiet week</dt>
          <dd><span className="mono">{percent(region.quiet?.[index]) ?? '—'}</span> <span className="muted">model</span></dd>
          <dt>Skill</dt>
          <dd className="mono" title="Brier skill score over the seasonal baseline on held-out Mars years">
            BSS {outlook.pooledBss.toFixed(2)} · {outlook.foldsPositive}/{outlook.folds} years</dd>
        </> : <>
          <dt>Model</dt><dd className="caution">Withheld · no skill over baseline</dd>
        </>}
      </Metrics>
      <p className="dust-source muted">MDAD v1.1 storm maps · {years} · not a live forecast</p>
    </>}
  </section>
}
