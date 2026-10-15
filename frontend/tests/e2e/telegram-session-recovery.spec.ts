import { expect, test, type Page, type Route } from '@playwright/test'

const user = {
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Telegram Test User',
  status: 'active',
  role: 'user',
  credits_balance: 3,
  created_at: '2026-10-15T00:00:00Z',
  updated_at: '2026-10-15T00:00:00Z',
  capabilities: { can_generate: true },
}

async function json(route: Route, status: number, data: object) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

async function telegramFrame(page: Page) {
  await page.addInitScript(() => {
    ;(window as unknown as { __telegramCloseCount: number }).__telegramCloseCount = 0
    window.Telegram = {
      WebApp: {
        initData: 'auth_date=synthetic&hash=synthetic',
        ready: () => {},
        expand: () => {},
        close: () => {
          ;(window as unknown as { __telegramCloseCount: number }).__telegramCloseCount += 1
        },
      },
    }
  })
}

test('Telegram expired initData does not logout the newly refreshed session', async ({ page }) => {
  await telegramFrame(page)
  let refreshRequests = 0
  let logoutRequests = 0
  let telegramRequests = 0

  await page.route('**/api/v1/auth/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/refresh')) {
      refreshRequests += 1
      return json(route, 401, { type: 'refresh_token_rotated', title: 'Already rotated', status: 401 })
    }
    if (path.endsWith('/auth/logout')) {
      logoutRequests += 1
      return json(route, 200, { status: 'ok' })
    }
    if (path.endsWith('/auth/telegram')) {
      telegramRequests += 1
      return json(route, 401, {
        type: 'telegram_auth_invalid',
        title: 'Invalid Telegram authentication data',
        status: 401,
        detail: 'Telegram initData has expired.',
      })
    }
    return json(route, 404, { type: 'not_found', status: 404 })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Не удалось войти через Telegram' })).toBeVisible()
  await expect(page.getByText(/Данные Telegram устарели/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Закрыть AuRoom' })).toBeVisible()
  expect(refreshRequests).toBe(1)
  expect(telegramRequests).toBe(1)
  expect(logoutRequests).toBe(0)

  await page.getByRole('button', { name: 'Закрыть AuRoom' }).click()
  expect(await page.evaluate(() => (window as unknown as { __telegramCloseCount: number }).__telegramCloseCount)).toBe(1)
})

test('a stale refresh cookie cannot trigger logout before successful Telegram recovery', async ({ page }) => {
  await telegramFrame(page)
  let logoutRequests = 0
  let telegramRequests = 0

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/refresh')) {
      return json(route, 401, { type: 'refresh_token_rotated', title: 'Already rotated', status: 401 })
    }
    if (path.endsWith('/auth/logout')) {
      logoutRequests += 1
      return json(route, 200, { status: 'ok' })
    }
    if (path.endsWith('/auth/telegram')) {
      telegramRequests += 1
      return json(route, 200, {
        access_token: 'telegram-test-access',
        refresh_token: 'telegram-test-refresh',
        token_type: 'bearer',
        expires_in: 900,
        user,
      })
    }
    if (path.endsWith('/projects')) return json(route, 200, { items: [], next_cursor: null, has_more: false })
    if (path.endsWith('/me')) return json(route, 200, user)
    if (path.endsWith('/telegram/content')) return json(route, 200, {})
    return json(route, 200, { items: [] })
  })

  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Создать проект' })).toBeVisible()
  expect(telegramRequests).toBe(1)
  expect(logoutRequests).toBe(0)
})
