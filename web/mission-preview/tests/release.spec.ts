import { expect, test } from '@playwright/test'
import registry from '../../src/atlas/regions.json' with { type: 'json' }

test.beforeEach(async ({ page, baseURL }) => {
  await page.route('**/*', route => new URL(route.request().url()).origin === baseURL ? route.continue() : route.abort())
})

test('offline Atlas selection preserves the region and profile through mission and model references', async ({ page }) => {
  await page.goto('/atlas?region=25&profile=human')
  const inspector = page.getByRole('complementary', { name: 'Region inspector' })
  await expect(inspector.getByRole('heading', { name: 'Solis Planum' })).toBeVisible()
  await inspector.getByRole('link', { name: 'Investigate site' }).click()
  await expect(page).toHaveURL(/region=25&profile=human/)
  await expect(page.getByRole('heading', { name: 'Solis Planum' })).toBeVisible()
  await expect(page.getByText('Unclassified', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('HPX128:115505', { exact: true })).toBeVisible()
  await expect(page.getByText('MOLA gridded elevation at cell centroid')).toBeVisible()
  await expect(page.getByText(/No reviewed local query is packaged/)).toBeVisible()
  await expect(page.getByText('Tactical routing withheld.', { exact: true })).toBeVisible()
  await expect(page.getByText('Live hazard assessment unavailable.', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Scientific model requirements' }).click()
  await expect(page).toHaveURL(/view=models&region=25&profile=human/)
  await page.getByRole('link', { name: 'Mars Atlas' }).click()
  await expect(inspector.getByRole('heading', { name: 'Solis Planum' })).toBeVisible()
})

test('switches between the primary evidence demo, engineering control and sparse regions', async ({ page }) => {
  await page.goto('/mission')
  const evidence = page.getByRole('complementary', { name: 'Evidence' })
  const select = page.getByLabel('Atlas region')
  await expect(select.locator('option')).toHaveCount(56)
  await expect(page.getByRole('heading', { name: 'Arcadia Planitia' })).toBeVisible()
  await expect(evidence.getByRole('heading', { name: 'local_elevation_20m' })).toBeVisible()
  await expect(evidence.getByText('Refused', { exact: true })).toBeVisible()
  await expect(evidence.getByRole('heading', { name: 'coarse_elevation_context' })).toBeVisible()

  await select.selectOption('43')
  await expect(page.getByRole('heading', { name: 'Jezero Crater' })).toBeVisible()
  await expect(evidence.getByRole('heading', { name: 'elevation_20m_posts' })).toBeVisible()
  await expect(evidence.getByText('Supported fallback', { exact: true })).toBeVisible()
  await expect(evidence.getByRole('heading', { name: 'coarse_elevation_context' })).toHaveCount(0)

  await select.selectOption('28')
  await expect(page.getByRole('heading', { name: 'Icaria Planum' })).toBeVisible()
  await expect(page.getByText('HPX128:169532', { exact: true })).toBeVisible()
  await expect(evidence.getByText(/No reviewed local query/)).toBeVisible()
  await expect(evidence.getByRole('heading', { name: 'elevation_20m_posts' })).toHaveCount(0)

  await select.selectOption('01')
  await expect(page.getByRole('heading', { name: 'Planum Boreum' })).toBeVisible()
  await expect(page.getByText('HPX128:16347', { exact: true })).toBeVisible()
  await expect(page.getByText(/interpolated estimate; zero native observations/)).toBeVisible()
  await expect(evidence.getByText(/No reviewed local query/)).toBeVisible()
})

test('rejects an inconsistent query and preserves survey fallback during an API failure', async ({ page }) => {
  await page.route('**/api/v1/regions/43', async route => {
    const response = await route.fetch()
    const json = await response.json()
    json.local_evidence.query_sha256 = '0'.repeat(64)
    await route.fulfill({ response, json })
  })
  await page.goto('/mission?region=43')
  await expect(page.getByRole('alert')).toContainText('Evidence identity mismatch')
  await expect(page.getByText('Supported fallback', { exact: true })).toHaveCount(0)
  await page.route('**/api/v1/regions/28', route => route.abort())
  await page.getByLabel('Atlas region').selectOption('28')
  await expect(page.getByRole('heading', { name: 'Icaria Planum' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Atlas research context' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Planning service unreachable')
  await expect(page.getByText('Tactical routing withheld.', { exact: true })).toBeVisible()
  await page.goto('/mission?region=unknown')
  await expect(page.getByRole('alert')).toContainText('Unknown Atlas region')
})

test('uses the sourced ranking pack and discloses terms excluded from the result', async ({ page }) => {
  await page.goto('/atlas?panel=ranking')
  const objective = page.getByLabel('Science objective')
  await objective.fill('ancient lakes with hydrothermal activity')
  await page.getByRole('button', { name: 'Rank areas' }).click()
  await expect(page.getByText('Unsupported concepts: hydrothermal.', { exact: true })).toBeVisible()
  await expect(page.getByText('Unrecognized terms: activity.', { exact: true })).toBeVisible()
  await expect(page.getByText('Match tiers apply only to the evaluated concepts.')).toBeVisible()
  await expect(page.getByText(/Direct match/).first()).toBeVisible()
  await objective.fill('hydrothermal')
  await page.getByRole('button', { name: 'Rank areas' }).click()
  await expect(page.getByRole('status')).toContainText('Ranking withheld')
  await expect(page.locator('article')).toHaveCount(0)
})

test('replays the four planning outcomes separately from the current region', async ({ page }) => {
  await page.goto('/mission?region=25')
  await page.getByRole('button', { name: 'Enter simulated Marswalk' }).click()
  await expect(page.getByTestId('simulation-tag')).toBeVisible()
  await expect(page.getByTestId('return-seconds')).toHaveText('40 s')
  await expect(page.getByTestId('science-science-a')).toContainText('75 s')
  await page.getByRole('button', { name: 'Close mid corridor' }).click()
  await expect(page.getByTestId('return-seconds')).toHaveText('60 s')
  await expect(page.getByTestId('science-science-a')).toContainText('95 s')
  await expect(page.getByTestId('recommendation')).toContainText('direct_return')
  await page.getByLabel('Remaining time', { exact: true }).fill('70')
  await expect(page.getByTestId('recommendation')).toContainText('No recommendation · RETURN_OVER_RESERVE')
  await page.getByRole('button', { name: 'Close north corridor' }).click()
  await expect(page.getByTestId('recommendation')).toContainText('No recommendation · NO_RETURN_ROUTE')
  await expect(page.getByTestId('completed-work')).toContainText('survey-done')
  await page.getByRole('button', { name: 'Site investigation' }).click()
  await expect(page.getByRole('heading', { name: 'Solis Planum' })).toBeVisible()
})

test('serves the offline Arcadia showcase and keeps operator control over simulated reroutes', async ({ page }) => {
  await page.goto('/demo/#demo/arcadia')
  await expect(page.getByRole('heading', { name: 'Arcadia Planitia Science Tasks' })).toBeVisible()
  await expect(page.getByText(/routing withheld/i)).toBeVisible()
  await page.getByRole('link', { name: 'Atlas evidence workspace' }).click()
  await expect(page.getByRole('heading', { name: 'Arcadia Planitia' })).toBeVisible()
  await page.getByRole('link', { name: 'Open separate simulated hazard drill' }).click()
  await expect(page.getByText(/Update 1 \/ 6 · (Local compute|Bundled fallback)/)).toBeVisible()
  const next = page.getByRole('button', { name: 'Next update' })
  for (let update = 0; update < 3; update++) await next.click()
  await expect(page.getByRole('status')).toHaveText('Active route blocked')
  await expect(page.locator('article').filter({ hasText: /Route A ·/ })).toContainText('ACTIVE PLAN')
  await page.getByRole('button', { name: /Route B ·/ }).click()
  await page.getByRole('button', { name: 'Approve route B' }).click()
  await expect(page.getByText('Approved · Route B', { exact: true })).toBeVisible()
  await next.click()
  await expect(page.getByRole('status')).toHaveText('Station data stale')
  await page.getByRole('button', { name: 'Hold position' }).click()
  await expect(page.getByRole('button', { name: 'Resume B' })).toBeDisabled()
  await page.getByRole('link', { name: 'Atlas evidence workspace' }).click()
  await expect(page).toHaveURL(/region=03&profile=human/)
})

test('unknown API paths and missing assets return explicit 404 responses', async ({ request }) => {
  for (const path of ['/api/v1/unknown', '/api/v1/regions/nope', '/demo/maps/no-such-map.webp']) {
    const response = await request.get(path)
    expect(response.status()).toBe(404)
    expect(response.headers()['content-type']).toContain('application/json')
  }
})

test('the released pack provides a matching anchor cell for all Atlas regions', async ({ request }) => {
  for (const region of registry.regions) {
    const response = await request.get('/api/v1/regions/' + region.id)
    expect(response.status()).toBe(200)
    const result = await response.json()
    expect(result.region_id).toBe(region.id)
    expect(result.anchor_cell_id).toMatch(/^HPX128:/)
    expect(result.cell_context.pack.version).toBe('cell-ranking-v3')
    expect(result.tactical_routing).toBe('withheld_no_qualified_pack')
    expect(result.live_hazards).toBe('unavailable_no_qualified_feed')
  }
})

test('blocks planning deep links without moving a rehearsal to the selected site', async ({ page }) => {
  await page.goto('/demo/#route/rover/08')
  await expect(page.getByRole('heading', { name: /Regional planning withheld.*Utopia Planitia/ })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open the Jezero simulation' })).toBeVisible()
  await page.getByRole('link', { name: 'Investigate Atlas region' }).click()
  await expect(page).toHaveURL(/region=08&profile=rover/)
  await expect(page.getByRole('heading', { name: 'Utopia Planitia' })).toBeVisible()
})

test('the packaged station and hazard API returns six labeled simulated steps', async ({ request }) => {
  for (let step = 0; step < 6; step++) {
    const response = await request.get('/api/v1/hazard-replay/' + step)
    expect(response.status()).toBe(200)
    const frame = await response.json()
    expect(frame.schema_version).toBe(1)
    expect(frame.scenario_id).toBe('marswalk-north-ramp-dust-drill-v1')
    expect(frame.index).toBe(step)
    expect(frame.forecast.status).toBe('issued')
    expect(frame.forecast.model_id).toMatch(/^station-forecast-/)
  }
  expect((await request.get('/api/v1/hazard-replay/6')).status()).toBe(404)
})
