import { expect, test, type Page, type Locator } from '@playwright/test'

const now = '2026-09-22T12:00:00Z'
const longTitle = 'Загородный дом с террасой, мастерской и благоустройством участка'
const unbrokenTitle = 'Проект_загородногодомасмастерскойиблагоустройствомучастка'
const media = '/layout-house.svg'
const user = {
  id: '11111111-1111-4111-8111-111111111111', display_name: 'Александр Константинопольский',
  status: 'active', role: 'superadmin', credits_balance: 124, created_at: now, updated_at: now,
  capabilities: { can_generate: true },
}
const projects = [longTitle, unbrokenTitle, 'Летняя кухня'].map((name, index) => ({
  id: `33333333-3333-4333-8333-33333333333${index}`, name, description: longTitle,
  status: 'active', context: {}, created_at: now, updated_at: now,
}))
const ideas = [longTitle, unbrokenTitle, 'Летняя кухня'].map((title, index) => ({
  id: `idea-${index}`, title, category: longTitle, generation_type: 'master_plan',
  image_url: media, preview_url: media, selected_objects: ['house'], published_at: now, is_saved: false,
  objects: [{ key: 'house', title: 'Дом', answers: [
    { question: 'Архитектурный стиль', answer: longTitle }, { question: 'Пожелания', answer: unbrokenTitle },
  ] }],
}))
const generations = ['completed', 'failed', 'processing'].map((status, index) => ({
  id: `generation-${index}`, project_id: projects[index].id, type: 'master_plan', status,
  output_asset: status === 'completed' ? { id: 'asset', url: media } : null,
  credits_charged: 1, fallback_used: false, created_at: now, updated_at: now,
}))
const catalog = {
  version: 'layout-v1', sections: [{ key: 'house', title: 'Дом и архитектура', object_keys: ['house'] }],
  questionnaires: [{ key: 'house', title: longTitle, source_file: 'house', order: 0, scene_policy: {}, questions: [] }],
}
const billing = {
  enabled: true, receipt_required: true, credits_balance: 124,
  packages: [1, 2, 3].map((index) => ({ code: `pack-${index}`, label: index === 1 ? unbrokenTitle : longTitle, credits: index * 10, amount: String(index * 1000) })),
  payments: [{ id: 'payment', status: 'succeeded', refund_status: 'pending', amount: '2000', credits: 20, created_at: now }],
}

async function prepare(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('auroom.access_token', 'layout-fixture')
    window.Telegram = { WebApp: { initData: '', requestFullscreen: () => {}, exitFullscreen: () => {} } }
  })
  await page.route('**/layout-house.svg', (route) => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700"><rect width="1000" height="700" fill="#839589"/><path d="M100 550V300L500 80L900 300V550Z" fill="#ded5bb"/></svg>',
  }))
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path.includes('/admin/')) {
      // This scenario opens only the tariff tab and inspects the shared header.
      data = path.endsWith('/billing-settings') ? { receipts_enabled: false } : path.endsWith('/overview') ? {} : []
    } else if (path.endsWith('/me')) data = user
    else if (path.endsWith('/projects')) data = { items: projects, has_more: false }
    else if (path.endsWith('/ideas')) data = ideas
    else if (path.endsWith('/questionnaires')) data = catalog
    else if (path.endsWith('/generations')) data = { items: generations, has_more: false }
    else if (path.endsWith('/billing')) data = billing
    else return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `Unhandled fixture: ${path}` }) })
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
}

async function expectContained(container: Locator, selector: string) {
  const escaped = await container.evaluate((parent, selector) => {
    const bounds = parent.getBoundingClientRect()
    return Array.from(parent.querySelectorAll<HTMLElement>(selector)).filter((element) => {
      const box = element.getBoundingClientRect()
      return box.width > 0 && (box.left < bounds.left - 1 || box.right > bounds.right + 1 || element.scrollWidth > element.clientWidth + 2)
    }).map((element) => element.textContent?.slice(0, 80))
  }, selector)
  expect(escaped).toEqual([])
}

const viewports = [
  { width: 320, height: 568 }, { width: 375, height: 667 }, { width: 390, height: 844 },
  { width: 430, height: 932 }, { width: 768, height: 1024 }, { width: 1024, height: 768 },
  { width: 1440, height: 900 }, { width: 1920, height: 1080 }, { width: 844, height: 390 },
]

test('populated home, history and billing keep text and actions within their cards', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  await prepare(page)
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    for (const section of ['home', 'history', 'profile']) {
      await page.goto(`/?section=${section}`)
      await page.waitForLoadState('networkidle')
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth), `${section} at ${viewport.width}`).toBeLessThanOrEqual(1)
      if (section === 'home') await expectContained(page.locator('.home-last-card'), 'h2, .home-last-date, button')
      if (section === 'history') for (const card of await page.locator('.history-card').all()) await expectContained(card, 'h3, p, button')
      if (section === 'profile') {
        await expectContained(page.locator('.profile-card'), 'h2, button')
        for (const card of await page.locator('.billing-package').all()) await expectContained(card, 'h3, button')
        const admin = page.getByRole('button', { name: 'Веб-админка' })
        expect(await admin.evaluate((element) => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(12)
        await admin.click({ trial: true })
      }
      if (viewport.width === 320 || viewport.width === 1440) {
        await testInfo.attach(`${section}-${viewport.width}.png`, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
      }
    }
  }
})

test('Ideas preserve usable media, reachable actions and search with long titles', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  await prepare(page)
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await page.goto('/?section=ideas')
    await page.waitForLoadState('networkidle')
    for (const card of await page.locator('.idea-work-card').all()) {
      await card.scrollIntoViewIfNeeded()
      await card.locator('summary').click()
      await expectContained(card, 'h1, .idea-work-summary span, .idea-use-button')
      expect((await card.locator('.idea-work-stage').boundingBox())!.height).toBeGreaterThanOrEqual(180)
      await card.getByRole('button', { name: 'Сохранить', exact: true }).click({ trial: true })
      await card.locator('.idea-use-button').click({ trial: true })
    }
    await page.getByRole('button', { name: 'Открыть поиск' }).click()
    const search = page.getByRole('textbox', { name: 'Поиск работ' })
    await search.fill('Летняя')
    await expect(page.locator('.idea-work-card')).toHaveCount(1)
    await expectContained(page.locator('.ideas-concept-topbar'), 'input, button')
    const brand = (await page.locator('.ideas-concept-topbar .wordmark').boundingBox())!
    const input = (await search.boundingBox())!
    expect(input.x).toBeGreaterThanOrEqual(brand.x + brand.width + 4)
    await page.getByRole('button', { name: 'Закрыть поиск' }).click()
    if (viewport.width === 320 || viewport.width === 1440) {
      await testInfo.attach(`ideas-${viewport.width}.png`, { body: await page.screenshot(), contentType: 'image/png' })
    }
  }
})


test('fullscreen leaves desktop admin header actions unobstructed', async ({ page }) => {
  await prepare(page)
  for (const width of [1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/?admin=1')
    await page.waitForLoadState('networkidle')
    const fullscreen = (await page.locator('.telegram-fullscreen-button').boundingBox())!
    const back = page.getByRole('button', { name: '← В приложение' })
    const bounds = (await back.boundingBox())!
    expect(fullscreen.x < bounds.x + bounds.width && fullscreen.x + fullscreen.width > bounds.x && fullscreen.y < bounds.y + bounds.height && fullscreen.y + fullscreen.height > bounds.y).toBe(false)
    await back.click({ trial: true })
  }
})

test('Ideas load previews when a publication is taller than the viewport', async ({ page }) => {
  await prepare(page)
  await page.route('**/api/v1/ideas?*', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([...ideas, ...ideas].map((idea, index) => ({ ...idea, id: `tall-${index}`, title: longTitle.repeat(4).slice(0, 255) }))),
  }))
  for (const viewport of [{ width: 320, height: 568 }, { width: 844, height: 390 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/?section=ideas')
    await expect(page.locator('[data-feed-index="0"] img')).toHaveCount(1)
    await expect(page.locator('[data-feed-index="4"] img')).toHaveCount(0)
    for (const index of [2, 4]) {
      const card = page.locator(`[data-feed-index="${index}"]`)
      await card.scrollIntoViewIfNeeded()
      await expect(card.locator('img')).toHaveCount(1)
    }
  }
})
