import { expect, test, type Page, type Route } from '@playwright/test'

const now = '2026-09-16T12:00:00Z'
const user = {
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Очень длинное имя пользователя для проверки интерфейса',
  status: 'active',
  role: 'user',
  credits_balance: 7,
  created_at: now,
  updated_at: now,
  capabilities: { can_generate: true },
}
const admin = { ...user, role: 'superadmin' }
const catalog = {
  version: 'ux-audit-v1',
  sections: [{ key: 'house', title: 'Дом', object_keys: ['house'] }],
  questionnaires: [{
    key: 'house',
    title: 'Дом, фасад',
    source_file: 'fixture',
    order: 0,
    scene_policy: {},
    questions: [],
  }],
}

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

async function authenticate(page: Page, asAdmin = false) {
  await page.addInitScript(() => sessionStorage.setItem('auroom.access_token', 'ux-audit'))
  await page.route('**/api/v1/me', (route) => json(route, asAdmin ? admin : user))
}

async function routeNavigationData(page: Page) {
  await page.route('**/api/v1/projects?**', (route) => json(route, { items: [], next_cursor: null, has_more: false }))
  await page.route('**/api/v1/ideas?**', (route) => json(route, []))
  await page.route('**/api/v1/questionnaires', (route) => json(route, catalog))
  await page.route('**/api/v1/billing', (route) => json(route, {
    enabled: false,
    receipt_required: false,
    credits_balance: 7,
    packages: [],
    payments: [],
  }))
}

test('section navigation survives refresh and follows browser Back/Forward', async ({ page }) => {
  await authenticate(page)
  await routeNavigationData(page)
  await page.goto('/?section=home')

  await page.getByRole('button', { name: 'Идеи', exact: true }).click()
  await expect(page).toHaveURL(/section=ideas/)
  await expect(page.getByRole('button', { name: 'Идеи', exact: true })).toHaveAttribute('aria-current', 'page')

  await page.getByRole('button', { name: 'Профиль' }).click()
  await expect(page).toHaveURL(/section=profile/)
  await page.goBack()
  await expect(page).toHaveURL(/section=ideas/)
  await expect(page.getByText('Пока нет опубликованных работ.')).toBeVisible()

  await page.reload()
  await expect(page.getByText('Пока нет опубликованных работ.')).toBeVisible()

  await page.getByRole('button', { name: 'Главная' }).click()
  await page.getByRole('button', { name: 'Создать проект' }).click()
  await expect(page).toHaveURL(/section=create/)
  await page.goBack()
  await expect(page).toHaveURL(/section=home/)
})

test('logout completes locally when the server is unavailable', async ({ page }) => {
  await authenticate(page)
  await routeNavigationData(page)
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.route('**/api/v1/auth/logout', (route) => json(route, {
    title: 'Service unavailable',
    detail: 'Temporary outage',
  }, 503))

  await page.goto('/')
  await page.getByRole('button', { name: 'Выйти' }).click()

  await expect(page.getByRole('heading', { name: 'Вход' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('auroom.access_token'))).toBeNull()
  expect(pageErrors).toEqual([])
})

test('Create retries a failed catalog load without a page refresh', async ({ page }) => {
  await authenticate(page)
  let attempts = 0
  await page.route('**/api/v1/questionnaires', async (route) => {
    attempts += 1
    if (attempts === 1) return json(route, { title: 'Недоступно', detail: 'Каталог временно недоступен' }, 503)
    return json(route, catalog)
  })

  await page.goto('/?section=create')
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByRole('button', { name: /Дом/ })).toBeVisible()
  expect(attempts).toBe(2)
})

test('Profile retries billing after an initial API failure', async ({ page }) => {
  await authenticate(page)
  let attempts = 0
  await page.route('**/api/v1/billing', async (route) => {
    attempts += 1
    if (attempts === 1) return json(route, { title: 'Недоступно', detail: 'Платежи временно недоступны' }, 503)
    return json(route, {
      enabled: false,
      receipt_required: false,
      credits_balance: 7,
      packages: [],
      payments: [],
    })
  })

  await page.goto('/?section=profile')
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByText('Оплата временно недоступна. Доступные способы пополнения появятся здесь позже.')).toBeVisible()
  expect(attempts).toBe(2)
})

test('History recovers from load, media, and result-opening failures', async ({ page }) => {
  await authenticate(page)
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  let attempts = 0
  await page.route('**/api/v1/generations?**', async (route) => {
    attempts += 1
    if (attempts === 1) return json(route, { title: 'Недоступно', detail: 'История недоступна' }, 503)
    return json(route, { items: [{
      id: 'generation-1', project_id: 'project-1', input_asset_id: null,
      output_asset: { id: 'asset-1', project_id: 'project-1', type: 'image', purpose: 'generation_output', original_filename: 'result.png', mime_type: 'image/png', size_bytes: 10, width: 640, height: 480, url: '/broken/history.png', created_at: now },
      type: 'master_plan', status: 'completed', credits_charged: 1, model_name: 'model',
      fallback_used: false, composition_mode: 'replace', edit_region: null, protected_regions: [],
      error: null, created_at: now, updated_at: now, started_at: now, completed_at: now,
    }], next_cursor: null, has_more: false })
  })
  await page.route('**/api/v1/projects?**', (route) => json(route, { items: [{
    id: 'project-1', name: 'Дом', description: null, status: 'active', context: {}, created_at: now, updated_at: now,
  }], next_cursor: null, has_more: false }))
  await page.route('**/api/v1/projects/project-1', (route) => json(route, { title: 'Недоступно', detail: 'Проект временно недоступен' }, 503))
  await page.route('**/broken/history.png', (route) => route.abort('failed'))

  await page.goto('/?section=history')
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByText('Изображение временно недоступно')).toBeVisible()
  await page.getByRole('button', { name: 'Открыть работу' }).click()
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  expect(attempts).toBe(2)
  expect(pageErrors).toEqual([])
})

test('Ideas retries its initial load and explains a broken final image', async ({ page }) => {
  await authenticate(page)
  let attempts = 0
  await page.route('**/api/v1/ideas?**', async (route) => {
    attempts += 1
    if (attempts === 1) return json(route, { title: 'Недоступно', detail: 'Лента временно недоступна' }, 503)
    return json(route, [{
      id: 'broken-image-idea',
      title: 'Дом с очень длинным названием, которое должно корректно переноситься на узком экране',
      category: 'Современная архитектура',
      generation_type: 'master_plan',
      image_url: '/broken/original.png',
      preview_url: '/broken/preview.webp',
      objects: [],
      selected_objects: ['house'],
      published_at: now,
      is_saved: false,
    }])
  })
  await page.route('**/broken/**', (route) => route.abort('failed'))

  await page.goto('/?section=ideas')
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByRole('heading', { name: /Дом с очень длинным названием/ })).toBeVisible()
  await expect(page.getByText('Изображение временно недоступно')).toBeVisible()
  expect(attempts).toBe(2)
})

test('Ideas confirms that a share link was copied', async ({ page }) => {
  await authenticate(page)
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: undefined })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async () => undefined },
    })
  })
  await page.route('**/api/v1/ideas?**', (route) => json(route, [{
    id: 'shared-idea', title: 'Дом', category: 'Архитектура', generation_type: 'master_plan',
    image_url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"></svg>',
    preview_url: null, objects: [], selected_objects: ['house'], published_at: now, is_saved: false,
  }]))

  await page.goto('/?section=ideas')
  await page.getByRole('button', { name: 'Поделиться' }).click()
  await expect(page.getByText('Ссылка скопирована.')).toBeVisible()
})

test('questionnaire bootstrap can be retried in place after an API failure', async ({ page }) => {
  await authenticate(page)
  const projectId = '33333333-3333-4333-8333-333333333333'
  const session = {
    session_id: '77777777-7777-4777-8777-777777777777', catalog_version: catalog.version,
    selected_objects: ['house'], initial_concept_mode: true, survey_completed_objects: [],
    initial_generation_id: null, initial_concept_accepted: false, current_object: 'house',
    current_question_id: null, source_step_completed: false, source_asset_id: null,
    scene_asset_id: null, scene_generation_id: null, answers: {}, accepted_objects: [],
    removed_objects: [], pending_removal_object: null, generation_ids: {}, edit_question_ids: [],
    review_comments: {}, edit_regions: {}, lock_regions: {}, region_mode: null,
    region_object: null, application_submitted: false,
  }
  const project = {
    id: projectId, name: 'Дом', description: null, status: 'active',
    context: { questionnaire_draft: false, design_session: session }, created_at: now, updated_at: now,
  }
  let catalogAttempts = 0
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/me')) return json(route, user)
    if (path.endsWith(`/projects/${projectId}`)) return json(route, project)
    if (path.endsWith('/questionnaires')) {
      catalogAttempts += 1
      if (catalogAttempts === 1) return json(route, { title: 'Недоступно', detail: 'Каталог недоступен' }, 503)
      return json(route, catalog)
    }
    if (path.endsWith(`/projects/${projectId}/questionnaire-session`)) return json(route, { session })
    if (path.endsWith('/questionnaire-generation-cost')) return json(route, { generation_type: 'master_plan', initial_credits: 0, credits: 1, initial_offer_available: true, is_available: true })
    return json(route, { type: 'mock_unhandled', title: 'Unhandled', status: 404 }, 404)
  })

  await page.goto(`/?project=${projectId}`)
  await expect(page.getByRole('heading', { name: 'Опросник не открылся' })).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByRole('heading', { name: 'Загрузите фото участка' })).toBeVisible()
  expect(catalogAttempts).toBe(2)
})

function adminResponse(path: string) {
  if (path.endsWith('/admin/overview')) return { yookassa_configured: true, nexus_configured: true, telegram_configured: true }
  if (path.endsWith('/admin/billing-settings')) return { receipts_enabled: false, vat_code: null, payment_subject: null, payment_mode: null, updated_at: null }
  if (path.endsWith('/admin/questionnaires')) return { catalog: { ...catalog, application_key: 'application', source_rules: [] }, source_texts: {}, updated_at: now }
  if (path.endsWith('/admin/generation')) return { primary_model: 'model', fallback_model: null, primary_timeout_seconds: 90, primary_params: {}, fallback_params: {}, mode_params: {}, updated_at: now }
  if (path.endsWith('/admin/telegram-content')) return { configured: false, bot_name: null, short_description: null, description: null, start_text: null, open_button_text: null, start_command_description: null, app_command_description: null, updated_at: null }
  if (path.endsWith('/admin/operations')) return { auth_rate_limit_per_minute: 30, generation_rate_limit_per_minute: 10, payment_rate_limit_per_minute: 10, registration_rate_limit_per_day: 20, yookassa_webhook_rate_limit_per_minute: 120, asset_upload_rate_limit_per_minute: 12, asset_max_retained_count_per_user: 200, asset_max_retained_bytes_per_user: 536870912, generation_max_inflight_per_user: 2, initial_concept_offer_limit_per_day: 3, starter_credits: 0, initial_concept_credits: 0, media_retention_days: 30, backup_interval_hours: 24, backup_retention_days: 14, media_min_free_bytes: 2147483648, updated_at: null }
  return []
}

test('admin initial load has a retry path and refund requires confirmation', async ({ page }) => {
  await authenticate(page, true)
  let overviewAttempts = 0
  let refundRequests = 0
  let broadcastRequests = 0
  await page.route('**/api/v1/admin/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/admin/overview')) {
      overviewAttempts += 1
      if (overviewAttempts === 1) return json(route, { title: 'Недоступно', detail: 'Админка временно недоступна' }, 503)
    }
    if (path.endsWith('/admin/payments')) return json(route, [{
      id: 'payment-1', user_id: user.id, package_code: 'starter', credits: 10,
      amount: '990.00', currency: 'RUB', status: 'succeeded', yookassa_payment_id: 'provider-1',
      receipt_email: null, refund_id: null, refund_status: null, provider_error: null,
      created_at: now, updated_at: now, paid_at: now, refunded_at: null,
    }])
    if (path.endsWith('/admin/payments/payment-1/refund')) {
      refundRequests += 1
      return json(route, {})
    }
    if (path.endsWith('/admin/broadcasts') && route.request().method() === 'GET') return json(route, [{
      id: 'broadcast-1', text: 'Важное сообщение', segment: 'all', status: 'draft',
      scheduled_at: null, sent_at: null, recipient_count: 0, sent_count: 0, failed_count: 0,
      created_at: now, updated_at: now,
    }])
    if (path.endsWith('/admin/broadcasts/broadcast-1/send')) {
      broadcastRequests += 1
      return json(route, {})
    }
    return json(route, adminResponse(path))
  })

  await page.goto('/?admin=1')
  await expect(page.getByText('Сервис временно недоступен. Повторите попытку.')).toBeVisible()
  await page.getByRole('button', { name: 'Повторить' }).click()
  await expect(page.getByText('YooKassa: настроен')).toBeVisible()

  await page.getByRole('button', { name: 'Платежи' }).click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Возврат' }).click()
  await page.waitForTimeout(100)
  expect(refundRequests).toBe(0)

  await page.getByRole('button', { name: 'Рассылки' }).click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'В очередь' }).click()
  await page.waitForTimeout(100)
  expect(broadcastRequests).toBe(0)
})
