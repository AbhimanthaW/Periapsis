import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const capture = async (page: Page, name: string) => {
  await page.evaluate(async () => {
    await document.fonts.ready
    await Promise.all(Array.from(document.images, img => img.decode()))
  })
  expect(await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio])).toEqual([1440, 900, 2])
  await page.mouse.move(2, 898)
  await page.screenshot({ path: `qa/captures/${name}.png`, scale: 'device', animations: 'disabled' })
}

test('captures the three reference states through the normal flow', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('response', response => { if (response.status() >= 400) errors.push(response.url()) })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Jezero Crater' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Polar', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: 'Jezero Crater', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await capture(page, '01-planetary-explore')

  await page.getByRole('link', { name: 'All 56 ranked' }).click()
  await expect(page.getByRole('main', { name: 'Region Ranking' })).toBeFocused()
  await expect(page.getByRole('row', { name: /Jezero Crater/ })).toHaveClass('selected')
  await expect(page.getByRole('row').nth(1)).toContainText('Jezero Crater')
  await expect(page.getByRole('row').nth(2)).toContainText('Nili Fossae')
  await capture(page, '01a-region-ranking')

  await page.getByRole('link', { name: 'Investigate Jezero Crater' }).click()
  await expect(page.getByRole('tab', { name: 'Data' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('row', { name: /CTX optical/ })).toContainText('Partial')
  await capture(page, '02-region-investigation')
  expect(errors).toEqual([])
})

test('edits the objective and targets, filters and sorts, and preserves state across selections', async ({ page }) => {
  await page.goto('/')
  const objective = page.getByRole('textbox', { name: 'Objective', exact: true })
  await objective.fill('Water ice and glacial deposits')
  await objective.press('Enter')
  await expect(page.getByText('Water ice and glaciation', { exact: true })).toBeVisible()
  const edit = page.getByRole('button', { name: 'Edit targets' })
  await edit.focus()
  await edit.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Edit targets' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('textbox').fill('ice\nglacial\nice')
  await dialog.getByRole('button', { name: 'Apply targets' }).click()
  await expect(edit).toBeFocused()
  await expect(page.getByText('glacial', { exact: true })).toBeVisible()
  await edit.press('Enter')
  await dialog.getByRole('textbox').fill('discard this edit')
  await page.keyboard.press('Escape')
  await expect(edit).toBeFocused()
  await expect(page.getByText('glacial', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Investigate ice' }).click()
  const polar = page.getByRole('button', { name: 'Polar', exact: true })
  await polar.click()
  await expect(polar).toHaveAttribute('aria-pressed', 'false')
  await page.getByRole('button', { name: 'Volcanic', exact: true }).click()
  const globe = page.getByRole('group', { name: 'Mars globe and regions' })
  const marker = globe.getByRole('button', { name: 'Planum Boreum', exact: true })
  await marker.hover()
  await expect(marker.locator('.marker-label')).toBeVisible()
  await marker.focus()
  await marker.press('Space')
  await expect(marker).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: 'Planum Boreum' })).toBeVisible()

  await page.getByRole('link', { name: 'All 56 ranked' }).click()
  await expect(page.getByRole('heading', { name: 'Water ice and glacial deposits' })).toBeVisible()
  await expect(page.getByText('Exclude volcanic')).toBeVisible()
  await expect(page.getByRole('row', { name: /Syrtis Major Planum/ })).toContainText('Excluded · volcanic')
  await expect(page.getByRole('row', { name: /Planum Boreum/ })).toHaveClass('selected')
  await page.getByRole('button', { name: 'Records', exact: true }).click()
  await expect(page.getByRole('row').nth(1)).toContainText('Nili Fossae')
  await page.getByRole('button', { name: 'Traversal', exact: true }).click()
  await expect(page.getByRole('row').nth(1)).toContainText('Planum Boreum')
  await page.getByRole('button', { name: 'Astronaut', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Traversal · Astronaut' })).toBeVisible()
  const listRegion = page.getByRole('button', { name: 'Nili Fossae', exact: true })
  await listRegion.focus()
  await listRegion.press('Enter')
  await expect(listRegion).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('link', { name: 'Investigate Nili Fossae' }).click()
  await expect(page.getByRole('heading', { name: 'Nili Fossae', exact: true })).toBeVisible()
  await expect(page.getByRole('row', { name: /CTX optical/ })).toContainText('Not packaged')
  const dataTab = page.getByRole('tab', { name: 'Data' })
  await dataTab.focus()
  await dataTab.press('ArrowLeft')
  await expect(page.getByRole('tab', { name: 'Science' })).toBeFocused()
  await expect(page.getByRole('tabpanel')).toContainText('Water ice and glacial deposits')
  await expect(page.getByRole('tabpanel')).toContainText('glacial')

  await page.getByRole('link', { name: 'Compare', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Traversal', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('row', { name: /Nili Fossae/ })).toHaveClass('selected')
  await page.getByRole('link', { name: 'Globe', exact: true }).click()
  await expect(objective).toHaveValue('Water ice and glacial deposits')
  await expect(page.getByRole('heading', { name: 'Nili Fossae', exact: true })).toBeVisible()
})

test('checks layer and zoom controls, Jezero landmarks, and responsive layout', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Viking colour/ }).click()
  await page.getByRole('button', { name: 'MOLA relief', exact: true }).click()
  await expect(page.locator('.globe-disc img')).toHaveAttribute('src', './maps/mars-mola.webp')
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await expect(page.locator('.globe-disc')).toHaveCSS('--zoom', '1.1')
  await page.getByRole('button', { name: 'Reset globe view' }).click()
  await expect(page.locator('.globe-disc')).toHaveCSS('--zoom', '1')

  await page.getByRole('link', { name: 'Investigate', exact: true }).click()
  await page.getByRole('button', { name: 'Delta front' }).click()
  await expect(page.getByRole('status')).toContainText('western delta deposits')
  await page.getByRole('button', { name: 'Sources' }).click()
  await expect(page.getByRole('dialog', { name: 'Imagery sources' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Sources' })).toBeFocused()

  for (const width of [1100, 768, 390]) {
    await page.setViewportSize({ width, height: 840 })
    for (const hash of ['globe', 'ranking', 'region/43']) {
      await page.goto('/#' + hash)
      const main = page.getByRole('main', { name: hash === 'globe' ? 'Planetary Explore'
        : hash === 'ranking' ? 'Region Ranking' : 'Region Investigation' })
      await expect(main).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
      const panel = hash === 'globe' ? page.getByRole('complementary', { name: 'Selected region' })
        : hash === 'ranking' ? page.getByRole('region', { name: 'Region ranking table' })
        : page.getByRole('complementary', { name: 'Region investigation panel' })
      const box = await panel.boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
      if (width > 900 || (hash !== 'region/43' && width > 690)) {
        expect(box!.y + box!.height).toBeLessThanOrEqual(841)
      }
      const action = hash === 'ranking' ? page.getByRole('link', { name: 'Investigate Jezero Crater' })
        : hash === 'globe' ? page.getByRole('link', { name: 'Investigate', exact: true })
        : page.getByRole('button', { name: 'Sources', exact: true })
      await action.scrollIntoViewIfNeeded()
      await expect(action).toBeInViewport()
      await action.hover()
      if (hash === 'globe') {
        const shortlist = (await page.getByRole('region', { name: 'Top matching regions' }).boundingBox())!
        expect(shortlist.y >= box!.y + box!.height - 1 || box!.y >= shortlist.y + shortlist.height - 1).toBe(true)
      }
    }
  }
})
