import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { arcadiaScenario } from '../src/objective-methods/arcadia'

const { objective } = arcadiaScenario
const openReview = async (page: Page) => {
  await page.getByRole('button', { name: 'Review methods', exact: true }).click()
  return page.getByRole('dialog', { name: 'Review methods' })
}

const submitObjective = async (page: Page, text: string) => {
  const input = page.getByRole('textbox', { name: 'Objective', exact: true })
  await input.fill(text)
  await input.press('Enter')
}

test('reviews Arcadia and its method constraints through Science Tasks with loopback only', async ({ page, baseURL }) => {
  const external: string[] = []
  const origin = new URL(baseURL!).origin
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin === origin) return route.continue()
    external.push(url.href)
    return route.abort()
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  let review = await openReview(page)
  await review.getByRole('button', { name: 'Load Arcadia scenario' }).click()
  await expect(review).toContainText('Arcadia Planitia · ' + objective)
  const mola = review.locator('[data-method-id="review-mola-context"]')
  const stereo = review.locator('[data-method-id="analyze-stereo-dtm"]')
  await expect(mola).toContainText('Suggested')
  await expect(stereo).toContainText('Pending')
  await stereo.locator('summary').click()
  await expect(stereo.getByText('Local elevation grid and coverage note')).toBeVisible()
  await expect(stereo.getByText(/no qualifying stereo DTM/)).toBeVisible()
  const contextImage = review.getByRole('img', { name: /Coarse MOLA elevation context/ })
  expect(await contextImage.evaluate(image => (image as HTMLImageElement).decode().then(() => true))).toBe(true)
  await review.getByRole('link', { name: 'Open Science Tasks' }).click()
  const advisory = page.getByRole('main', { name: 'Arcadia Science Tasks' })
  await expect(advisory.getByRole('heading', { name: 'Arcadia Planitia Science Tasks' })).toBeVisible()
  await expect(advisory.locator('[data-method-id="review-mola-context"]')).toContainText('Suggested')
  await expect(page.getByRole('group', { name: 'Mission profile', exact: true })).toHaveCount(0)
  await expect(advisory.getByRole('button', { name: 'Run with tasks' })).toHaveCount(0)
  await expect(page.locator('.mission-map')).toHaveCount(0)
  await advisory.getByRole('link', { name: 'Return to Explore' }).click()

  await submitObjective(page, objective + ' Without MOLA.')
  review = await openReview(page)
  await expect(mola).toContainText('Excluded')
  await expect(review.locator('[data-observation-id]')).toHaveCount(2)
  await expect(review.getByRole('img', { name: /Coarse MOLA/ })).toHaveCount(0)
  await review.getByRole('button', { name: 'Rover', exact: true }).click()
  await review.getByRole('link', { name: 'Open Science Tasks' }).click()
  await expect(page).toHaveURL(/#route\/rover\/03\/tasks$/)
  await expect(advisory.locator('[data-method-id="review-mola-context"]')).toContainText('Excluded')
  await expect(advisory.locator('[data-method-id="analyze-stereo-dtm"]')).toContainText('Pending')
  await advisory.getByRole('button', { name: 'Astronaut', exact: true }).click()
  await expect(page).toHaveURL(/#route\/astronaut\/03\/tasks$/)
  await expect(advisory.locator('[data-observation-id]')).toHaveCount(2)
  await advisory.getByRole('link', { name: 'Return to Explore' }).click()

  await submitObjective(page, objective + ' With a stereo DTM.')
  review = await openReview(page)
  await expect(mola).toContainText('Suggested')
  await expect(stereo).toContainText('Requested')
  await expect(stereo).toContainText('Pending')
  await review.getByRole('link', { name: 'Open Science Tasks' }).click()
  await expect(advisory.locator('[data-method-id="analyze-stereo-dtm"]')).toContainText('Requested')
  await expect(advisory.getByRole('button', { name: 'Run with tasks' })).toHaveCount(0)
  expect(errors).toEqual([])
  expect(external).toEqual([])
})

test('keeps intent on a region change and lets the user correct goals', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 840 })
  await page.goto('/')
  let review = await openReview(page)
  await review.getByRole('button', { name: 'Load Arcadia scenario' }).click()
  await review.getByRole('button', { name: 'Close', exact: true }).click()
  await submitObjective(page, 'Map regional elevation and investigate ice. No MOLA or stereo DTM.')
  review = await openReview(page)
  await expect(review.getByRole('status')).toContainText('Confirm the interpreted goals')
  await review.getByLabel('Local elevation at 20 m posting', { exact: true }).check()
  await review.getByRole('button', { name: 'Confirm goals' }).click()
  await expect(review.locator('[data-observation-id]')).toHaveCount(2)
  await review.getByRole('button', { name: 'Use selected region' }).click()
  await expect(review).toContainText('Jezero Crater')
  await expect(review.getByLabel('Local elevation at 20 m posting', { exact: true })).toBeChecked()
  await expect(review.locator('[data-method-id="review-mola-context"]')).toContainText('Excluded')
  await expect(review.getByText('arcadia-mola-context', { exact: false })).toHaveCount(0)
  await review.getByRole('button', { name: 'Use Arcadia footprint' }).click()
  await expect(review).toContainText('Arcadia Planitia')
  await expect(review.locator('[data-method-id="review-mola-context"]')).toContainText('Excluded')
  await review.getByRole('button', { name: 'Close', exact: true }).click()

  for (const [suffix, message] of [
    ['With MOLA. Without MOLA.', 'both requested and excluded'],
    ['Without unknown instrument.', 'Clarify which method to exclude'],
  ]) {
    await submitObjective(page, objective + ' ' + suffix)
    review = await openReview(page)
    await expect(review.getByRole('status')).toContainText(message)
    await expect(review.locator('[data-method-id]').filter({ hasText: 'Suggested' })).toHaveCount(0)
    await review.getByRole('button', { name: 'Close', exact: true }).click()
  }
  await submitObjective(page, 'Search for ancient biosignatures.')
  review = await openReview(page)
  await expect(review.getByRole('status')).toContainText('Choose broad elevation context')
  await expect(review.locator('[data-method-id]')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
})

test('Arcadia direct links and reloads show recovery without entering the simulation', async ({ page }) => {
  for (const hash of ['route/astronaut/03/tasks', 'route/rover/03', 'analysis/astronaut/03', 'monitor/rover/03']) {
    await page.goto('/#' + hash)
    const advisory = page.getByRole('main', { name: 'Arcadia Science Tasks' })
    await expect(advisory.getByRole('heading', { name: 'Arcadia Planitia Science Tasks' })).toBeVisible()
    await expect(advisory.getByRole('status')).toContainText('load the Arcadia scenario')
    await expect(page.getByRole('link', { name: 'Monitor', exact: true })).toHaveCount(0)
    await expect(page.locator('.mission-map')).toHaveCount(0)
  }
  await page.reload()
  await expect(page.getByRole('main', { name: 'Arcadia Science Tasks' }).getByRole('status')).toBeVisible()
})
