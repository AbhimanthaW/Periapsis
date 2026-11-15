import { readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { arcadiaScenario } from '../src/objective-methods/arcadia.ts'
import { methodCatalog } from '../src/objective-methods/catalog.ts'
import { confirmGoals, interpretObjective } from '../src/objective-methods/interpret.ts'
import { recommendMethods } from '../src/objective-methods/recommend.ts'

const { objective, regionId, profile, footprint } = arcadiaScenario
const site = { regionId, profile, footprint }
const propose = (text = objective, context = site) => recommendMethods(interpretObjective(text), context)
const statuses = proposal => proposal.methods.map(({ method, status, requested }) => [method.id, status, requested])

test('the frozen objective uses only the pinned elevation evidence and scale', () => {
  const proposal = propose()
  assert.deepEqual(proposal.intent.goalIds, ['regional-elevation', 'local-elevation'])
  assert.deepEqual(proposal.clarification, [])
  assert.deepEqual(statuses(proposal), [
    ['review-mola-context', 'suggested', false],
    ['analyze-stereo-dtm', 'pending', false],
  ])
  assert.equal(proposal.evidence.packageId, 'arcadia-mola-context')
  assert.equal(proposal.evidence.packageVersion, '0.1.0')
  assert.equal(proposal.evidence.classification, 'provenance_unverified')
  assert.deepEqual(proposal.evidence.footprint, footprint)
  assert.deepEqual(proposal.methods[0].supportingProductIds, ['mola-meg004-topography'])
  assert.match(proposal.methods[1].reason, /no qualifying stereo DTM for this polygon/)
  assert.deepEqual(proposal.uncoveredObservations.map(({ id }) => id), ['local-elevation-grid'])
})

test('a hard exclusion leaves both observations uncovered', () => {
  const proposal = propose(objective + ' Without MOLA.')
  assert.deepEqual(statuses(proposal), [
    ['review-mola-context', 'excluded', false],
    ['analyze-stereo-dtm', 'pending', false],
  ])
  assert.deepEqual(proposal.uncoveredObservations.map(({ id }) => id), [
    'regional-elevation-context', 'local-elevation-grid',
  ])
})

test('requested stereo remains pending. Context changes preserve intent and recheck support', () => {
  const intent = confirmGoals(interpretObjective(objective + ' Without MOLA. With a stereo DTM.'), [
    'regional-elevation', 'local-elevation',
  ])
  const rover = recommendMethods(intent, { ...site, profile: 'Rover' })
  assert.deepEqual(statuses(rover), statuses(recommendMethods(intent, site)))
  assert.equal(propose(objective, { ...site, profile: 'Rover' }).methods[0].status, 'suggested')
  for (const context of [
    { ...site, regionId: '43' },
    { regionId, profile },
    { ...site, footprint: { ...footprint, geometry: { type: 'Polygon', coordinates: [] } } },
  ]) {
    const proposal = recommendMethods(intent, context)
    assert.equal(proposal.intent, intent)
    assert.equal(proposal.evidence, undefined)
    assert.deepEqual(statuses(proposal), [
      ['review-mola-context', 'excluded', false],
      ['analyze-stereo-dtm', 'pending', true],
    ])
    assert.match(proposal.methods[1].reason, /No reviewed evidence/)
    assert.ok(propose(objective, context).methods.every(result => result.status === 'pending'))
  }
})

test('a conflict or unresolved instruction pauses selection', () => {
  const conflict = propose(objective + ' Without MOLA and with MOLA.')
  assert.match(conflict.clarification[0], /both requested and excluded/)
  assert.deepEqual(statuses(conflict), [['review-mola-context', 'excluded', true]])
  for (const exclusion of ['without unknown instrument', 'without MOLA-aligned products']) {
    const unresolved = propose(objective + ' ' + exclusion)
    assert.match(unresolved.clarification[0], /Clarify which method to exclude/)
    assert.deepEqual(unresolved.methods, [])
  }
})

test('coordinated exclusions work for methods and their required operations', () => {
  assert.deepEqual(statuses(propose(objective + ' No MOLA or stereo DTM.')), [
    ['review-mola-context', 'excluded', false],
    ['analyze-stereo-dtm', 'excluded', false],
  ])
  const testCoringMethod = {
    ...methodCatalog[1], id: 'test-coring', label: 'Collect a core',
    aliases: ['coring'], operations: ['drilling', 'sampling'],
  }
  const catalog = [...methodCatalog, testCoringMethod]
  const intent = interpretObjective(objective + ' No drilling or sampling.', catalog)
  assert.deepEqual(intent.excludedOperationIds, ['drilling', 'sampling'])
  const coring = recommendMethods(intent, site, catalog).methods.find(({ method }) => method.id === testCoringMethod.id)
  assert.equal(coring.status, 'excluded')
  assert.match(coring.reason, /drilling/)
  const conflict = interpretObjective(objective + ' No drilling. With coring.', catalog)
  assert.match(conflict.constraintIssues[0], /both requested and excluded/)
})

test('clarify unsupported or partial goals, allow correction and start fresh on resubmission', () => {
  const unsupported = interpretObjective('Look for ice with a stereo DTM.')
  assert.match(unsupported.goalIssue, /Choose broad elevation/)
  assert.deepEqual(statuses(recommendMethods(unsupported, site)), [['analyze-stereo-dtm', 'pending', true]])
  const partial = interpretObjective('Map ancient regional elevation and detect ice. Without MOLA.')
  assert.deepEqual(partial.modifierIds, ['age-ancient'])
  assert.match(partial.goalIssue, /Confirm the interpreted goals/)
  const confirmed = confirmGoals(partial, ['regional-elevation'])
  assert.equal(confirmed.source, 'confirmed')
  assert.deepEqual(statuses(recommendMethods(confirmed, site)), [['review-mola-context', 'excluded', false]])
  assert.deepEqual(propose().intent.excludedMethodIds, [])
  assert.equal(propose().intent.source, 'lexicon')
})

const fields = {
  deltas: 'mapped_fraction',
  alluvial_fans: 'mapped_fraction',
  valley_networks: 'length_km',
  glacial_landforms: 'mapped_fraction',
  crustal_magnetism: 'magnitude_nt',
  olivine: 'candidate_fraction_of_cell',
}

// Fixture evidence enters a test-only boundary. The production evidence resolver has no fixture input.
function readSyntheticCell(fixture, cellId) {
  assert.equal(fixture.data_status, 'synthetic')
  const cell = fixture.cells.find(item => item.cell_id === cellId)
  if (cell) {
    assert.equal(cell.data_status, fixture.data_status)
    assert.equal(cell.recipe_id, fixture.recipe_id)
    assert.deepEqual(cell.methods, fixture.methods)
  }
  return Object.entries(fields).map(([field, metric]) => {
    const value = cell?.fields[field] === null || !cell ? null : cell.fields[field][metric]
    assert.ok(value === null || (Number.isFinite(value) && value >= 0))
    const explanation = value === null ? 'Missing synthetic coverage.'
      : value === 0 ? 'Evaluated in the fixture with a zero result.' : 'Positive value in the synthetic fixture.'
    return { cellId, field, dataStatus: fixture.data_status, recipeId: fixture.recipe_id, value, explanation }
  })
}

const fixturePath = process.env.RW_SYNTHETIC_FIXTURE
test('the external context fixture preserves all six metrics and separates missing from zero', {
  skip: !fixturePath && 'Set RW_SYNTHETIC_FIXTURE to include the external fixture check.',
}, async () => {
  const fixture = JSON.parse(await readFile(fixturePath, 'utf8'))
  assert.equal(fixture.cells.length, 28)
  assert.equal(new Set(fixture.cells.map(cell => cell.cell_id)).size, 28)
  const records = fixture.cells.flatMap(cell => readSyntheticCell(fixture, cell.cell_id))
  for (const field of Object.keys(fields)) {
    assert.ok(records.some(record => record.field === field && record.value > 0), field)
  }
  assert.ok(records.every(record => record.dataStatus === 'synthetic'
    && record.recipeId === 'synthetic-science-v1' && /^HPX128:\d+$/.test(record.cellId)))
  const zero = records.find(record => record.field === 'deltas' && record.value === 0)
  assert.ok(zero)
  assert.match(zero.explanation, /zero result/)
  const outside = readSyntheticCell(fixture, 'HPX128:0')
  assert.ok(outside.every(record => record.value === null && /Missing/.test(record.explanation)))
  assert.equal(propose(objective, { ...site, footprint: undefined }).evidence, undefined)
})
