import { expect, test, type Page, type Route } from '@playwright/test'

const now = '2026-09-16T12:00:00Z'
const user = {
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Пользователь с очень длинным именем для проверки переноса',
  status: 'active',
  role: 'user',
  credits_balance: 7,
  created_at: now,
  updated_at: now,
  capabilities: { can_generate: true },
}
const catalog = {
  version: 'browser-quality-v1',
  sections: [
    { key: 'house', title: 'Дом и архитектурные объекты с длинным названием', object_keys: ['house'] },
    { key: 'landscape', title: 'Ландшафт', object_keys: ['garden'] },
  ],
  questionnaires: [
    { key: 'house', title: 'Дом, фасад', source_file: 'house', order: 0, scene_policy: {}, questions: [] },
    { key: 'garden', title: 'Сад и озеленение', source_file: 'garden', order: 1, scene_policy: {}, questions: [] },
  ],
}

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

async function prepare(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('auroom.access_token', 'browser-quality')
    const vitals = { cls: 0, lcp: 0 }
    ;(window as unknown as { __auditVitals: typeof vitals }).__auditVitals = vitals
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) vitals.lcp = Math.max(vitals.lcp, entry.startTime)
      }).observe({ type: 'largest-contentful-paint', buffered: true })
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries() as Array<PerformanceEntry & { value?: number; hadRecentInput?: boolean }>) {
          if (!entry.hadRecentInput) vitals.cls += entry.value || 0
        }
      }).observe({ type: 'layout-shift', buffered: true })
    } catch { /* metric is not exposed by every browser engine */ }
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/me')) return json(route, user)
    if (path.endsWith('/projects')) return json(route, { items: [], next_cursor: null, has_more: false })
    if (path.endsWith('/ideas')) return json(route, [])
    if (path.endsWith('/questionnaires')) return json(route, catalog)
    if (path.endsWith('/generations')) return json(route, { items: [], next_cursor: null, has_more: false })
    if (path.endsWith('/billing')) return json(route, { enabled: false, receipt_required: false, credits_balance: 7, packages: [], payments: [] })
    return json(route, { type: 'mock_unhandled', title: 'Unhandled mock', status: 404 }, 404)
  })
}

async function layoutAudit(page: Page) {
  return page.evaluate(() => {
    const visible = (element: Element) => {
      const style = getComputedStyle(element)
      const box = element.getBoundingClientRect()
      return style.visibility !== 'hidden' && style.display !== 'none' && box.width > 0 && box.height > 0
    }
    const controls = Array.from(document.querySelectorAll<HTMLElement>('button, a[href], input:not([type="hidden"]), select, textarea')).filter(visible)
    const unnamed = controls.filter((element) => {
      const labels = element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement
        ? Array.from(element.labels || []).map((label) => label.textContent || '').join(' ')
        : ''
      return !(element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || labels.trim())
    }).map((element) => element.outerHTML.slice(0, 180))
    return {
      overflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
      unnamed,
    }
  })
}

test('critical screens remain usable from 320px through 1920px without browser errors', async ({ page }, testInfo) => {
  test.setTimeout(120_000)
  await prepare(page)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const failedResponses: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('response', (response) => { if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`) })

  const viewports = [
    { width: 320, height: 700 },
    { width: 360, height: 780 },
    { width: 375, height: 812 },
    { width: 390, height: 844 },
    { width: 414, height: 896 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]
  const sections = ['home', 'ideas', 'create', 'history', 'profile'] as const

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    for (const section of sections) {
      await page.goto(`/?section=${section}`)
      await page.waitForLoadState('networkidle')
      const audit = await layoutAudit(page)
      expect(audit.overflow, `${section} overflows at ${viewport.width}px`).toBeLessThanOrEqual(1)
      expect(audit.unnamed, `${section} has unnamed controls at ${viewport.width}px`).toEqual([])
    }
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?section=ideas')
  await page.waitForLoadState('networkidle')
  await testInfo.attach('ideas-mobile-390.png', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?section=create')
  await page.waitForLoadState('networkidle')
  await testInfo.attach('create-desktop-1440.png', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })

  const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
    const scripts = resources.filter((entry) => entry.initiatorType === 'script')
    const styles = resources.filter((entry) => entry.initiatorType === 'link' && entry.name.includes('.css'))
    const fcp = performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0
    const vitals = (window as unknown as { __auditVitals?: { cls: number; lcp: number } }).__auditVitals
    return {
      ttfb_ms: navigation ? navigation.responseStart - navigation.startTime : null,
      dom_content_loaded_ms: navigation?.domContentLoadedEventEnd ?? null,
      load_ms: navigation?.loadEventEnd ?? null,
      fcp_ms: fcp || null,
      lcp_ms: vitals?.lcp || null,
      cls: vitals?.cls ?? null,
      script_requests: scripts.length,
      script_transfer_bytes: scripts.reduce((total, entry) => total + entry.transferSize, 0),
      stylesheet_requests: styles.length,
      stylesheet_transfer_bytes: styles.reduce((total, entry) => total + entry.transferSize, 0),
    }
  })
  await testInfo.attach('local-performance.json', { body: Buffer.from(JSON.stringify(metrics, null, 2)), contentType: 'application/json' })

  expect(consoleErrors).toEqual([])
  expect(pageErrors).toEqual([])
  expect(failedResponses).toEqual([])
})

test('critical mobile controls expose touch-sized targets', async ({ page }) => {
  await prepare(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?section=home')
  const navigationTargets = await page.locator('.bottom-nav button').evaluateAll((buttons) => buttons.map((button) => {
    const box = button.getBoundingClientRect()
    return { name: button.textContent?.trim(), width: box.width, height: box.height }
  }))
  expect(navigationTargets.every((target) => target.width >= 44 && target.height >= 44)).toBe(true)

  const logout = await page.getByRole('button', { name: 'Выйти' }).boundingBox()
  expect(logout?.width).toBeGreaterThanOrEqual(44)
  expect(logout?.height).toBeGreaterThanOrEqual(44)
})
