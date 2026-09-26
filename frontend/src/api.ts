import type { AdminQuestionnaireCatalog, NormalizedRect, QuestionnaireApplication, QuestionnaireCatalog, QuestionnaireSourceText } from './questionnaireTypes'
import type {
  AdminAiHistoryItem,
  AdminAudit,
  AdminBillingSettings,
  AdminBroadcast,
  AdminCreditTransaction,
  AdminGenerationPrice,
  AdminGenerationSettings,
  AdminIdea,
  AdminOperationalSettings,
  AdminOverview,
  AdminPayment,
  AdminPrompt,
  AdminTariff,
  AdminTelegramContent,
  AdminUser,
  Asset,
  BillingPayment,
  BillingSummary,
  BroadcastSegment,
  Generation,
  GenerationList,
  GenerationMode,
  Idea,
  Project,
  ProjectContextWrite,
  ProjectList,
  TokenPair,
  User,
  UserRole,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const ACCESS_KEY = 'auroom.access_token'
const REFRESH_KEY = 'auroom.refresh_token'
const LEGACY_ACCESS_KEY = 'archiai.access_token'
const LEGACY_REFRESH_KEY = 'archiai.refresh_token'
const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS || 20_000)
const API_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 20_000

function migrateLegacyTokens() {
  const previousAccess = localStorage.getItem(ACCESS_KEY) || localStorage.getItem(LEGACY_ACCESS_KEY)
  if (!sessionStorage.getItem(ACCESS_KEY) && previousAccess) sessionStorage.setItem(ACCESS_KEY, previousAccess)
  if (!localStorage.getItem(REFRESH_KEY) && localStorage.getItem(LEGACY_REFRESH_KEY)) localStorage.setItem(REFRESH_KEY, localStorage.getItem(LEGACY_REFRESH_KEY) || '')
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(LEGACY_ACCESS_KEY)
  localStorage.removeItem(LEGACY_REFRESH_KEY)
}
migrateLegacyTokens()

export class ApiError extends Error {
  status: number
  detail?: string
  errorType?: string
  constructor(status: number, message: string, detail?: string, errorType?: string) {
    super(message); this.name = 'ApiError'; this.status = status; this.detail = detail; this.errorType = errorType
  }
}

type RequestOptions = RequestInit & { auth?: boolean; retryAuth?: boolean }
function saveTokens(pair: TokenPair) {
  sessionStorage.setItem(ACCESS_KEY, pair.access_token)
  // New browser sessions keep refresh credentials only in the HttpOnly cookie.
  // Keep the localStorage key solely as a one-time migration source for old clients.
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}
let sessionVersion = 0
export function clearTokens() {
  sessionVersion += 1
  sessionStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(LEGACY_ACCESS_KEY)
  localStorage.removeItem(LEGACY_REFRESH_KEY)
}
export function hasStoredSession() { return Boolean(sessionStorage.getItem(ACCESS_KEY) || localStorage.getItem(REFRESH_KEY)) }

async function parseError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {}
  try { body = await response.json() } catch { /* generic */ }
  const title = typeof body.title === 'string' ? body.title : `HTTP ${response.status}`
  const detail = typeof body.detail === 'string' ? body.detail : undefined
  const errorType = typeof body.type === 'string' ? body.type : undefined
  const tokenError = errorType === 'invalid_access_token' || errorType === 'invalid_refresh_token' || errorType === 'refresh_token_reused'
  if (response.status === 401 && tokenError) {
    return new ApiError(response.status, 'Сессия истекла. Откройте приложение заново.', detail, errorType)
  }
  const message = response.status === 401
    ? 'Не удалось подтвердить вход. Проверьте данные или откройте приложение заново.'
    : response.status === 403
      ? 'Недостаточно прав для этого действия.'
      : response.status === 404
        ? 'Запрошенные данные не найдены или больше недоступны.'
        : response.status === 408
          ? 'Сервер отвечает слишком долго. Повторите попытку.'
          : response.status === 409
            ? 'Действие нельзя выполнить в текущем состоянии. Обновите данные и попробуйте снова.'
            : response.status === 413
              ? 'Файл слишком большой. Выберите файл меньшего размера.'
              : response.status === 422
                ? 'Проверьте введённые данные и попробуйте снова.'
                : response.status === 429
                  ? 'Слишком много запросов. Подождите немного и повторите попытку.'
                  : response.status >= 500
                    ? 'Сервис временно недоступен. Повторите попытку.'
                    : 'Не удалось выполнить запрос. Повторите попытку.'
  return new ApiError(response.status, message, detail || title, errorType)
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}) {
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort(init.signal?.reason)
  if (init.signal?.aborted) abortFromCaller()
  else init.signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, API_TIMEOUT_MS)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (error) {
    if (timedOut) throw new ApiError(408, 'Сервер отвечает слишком долго. Повторите попытку.')
    if (init.signal?.aborted) throw error
    throw new ApiError(0, 'Не удалось связаться с сервером. Проверьте соединение и повторите попытку.')
  } finally {
    window.clearTimeout(timeout)
    init.signal?.removeEventListener('abort', abortFromCaller)
  }
}

let refreshPromise: Promise<void> | null = null

type BrowserLockManager = {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>
}

let authQueue: Promise<unknown> = Promise.resolve()
async function serializeAuth<T>(action: () => Promise<T>): Promise<T> {
  const queued = authQueue.catch(() => {}).then(async () => {
    const locks = (navigator as Navigator & { locks?: BrowserLockManager }).locks
    return locks ? locks.request('auroom-auth-refresh', action) : action()
  })
  authQueue = queued.catch(() => {})
  return queued
}
function requireCurrentSession(version: number) {
  if (version !== sessionVersion) throw new ApiError(401, 'Сессия завершена. Войдите снова.')
}

async function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    const version = sessionVersion
    refreshPromise = serializeAuth(async () => {
        requireCurrentSession(version)
        if (sessionStorage.getItem('auroom.explicit_logout') === '1') throw new ApiError(401, 'Вы вышли из аккаунта.')
        const legacyToken = localStorage.getItem(REFRESH_KEY)
        const options: RequestInit = {
          method: 'POST',
          credentials: 'same-origin',
        }
        if (legacyToken) {
          options.headers = { 'Content-Type': 'application/json' }
          options.body = JSON.stringify({ refresh_token: legacyToken })
        }
        const response = await fetchWithTimeout(`${API_BASE}/auth/refresh`, options)
        if (!response.ok) throw await parseError(response)
        const pair = (await response.json()) as TokenPair
        requireCurrentSession(version)
        saveTokens(pair)
    }).finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

async function clearBrowserRefreshCookie(): Promise<void> {
  try {
    await serializeAuth(() => fetchWithTimeout(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'same-origin',
    }))
  } catch { /* best-effort cookie cleanup */ }
}

export async function restoreSession(): Promise<User | null> {
  const version = sessionVersion
  try {
    await refreshSession()
    return await getMe()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && version === sessionVersion) {
      clearTokens()
      await clearBrowserRefreshCookie()
      return null
    }
    throw error
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const version = sessionVersion
  const { auth = true, retryAuth = true, headers, ...rest } = options
  const finalHeaders = new Headers(headers)
  const accessToken = sessionStorage.getItem(ACCESS_KEY)
  if (auth && accessToken) finalHeaders.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetchWithTimeout(`${API_BASE}${path}`, { credentials: 'same-origin', ...rest, headers: finalHeaders })
  if (auth) requireCurrentSession(version)
  if (response.status === 401 && auth && retryAuth) {
    try { await refreshSession(); return request<T>(path, { ...options, retryAuth: false }) }
    catch (error) { if (version === sessionVersion) clearTokens(); throw error }
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const version = sessionVersion
  return serializeAuth(async () => {
  requireCurrentSession(version)
  const pair = await request<TokenPair>('/auth/login', { method: 'POST', auth: false, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
  requireCurrentSession(version)
  saveTokens(pair); return pair
  })
}
export async function loginTelegram(initData: string): Promise<TokenPair> {
  const version = sessionVersion
  return serializeAuth(async () => {
  requireCurrentSession(version)
  const pair = await request<TokenPair>('/auth/telegram', { method: 'POST', auth: false, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ init_data: initData }) })
  requireCurrentSession(version)
  saveTokens(pair); return pair
  })
}
export function getMe() { return request<User>('/me') }
export async function logout() {
  const legacyRefreshToken = localStorage.getItem(REFRESH_KEY)
  const options: RequestOptions = { method: 'POST', auth: false, retryAuth: false }
  if (legacyRefreshToken) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify({ refresh_token: legacyRefreshToken })
  }
  clearTokens()
  await serializeAuth(() => request('/auth/logout', options))
}

export function listProjects(cursor?: string | null, limit = 20, sort?: 'created' | 'updated') {
  const params = new URLSearchParams({ limit: String(limit) }); if (cursor) params.set('cursor', cursor); if (sort) params.set('sort', sort); return request<ProjectList>(`/projects?${params}`)
}
export function getProject(projectId: string) { return request<Project>(`/projects/${projectId}`) }
export function createProject(payload: { name: string; description?: string; context?: ProjectContextWrite }) { return request<Project>('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export function updateProject(projectId: string, payload: Partial<{ name: string; description: string | null; status: string; context: ProjectContextWrite }>) { return request<Project>(`/projects/${projectId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export function deleteProject(projectId: string) { return request<void>(`/projects/${projectId}`, { method: 'DELETE' }) }

export async function uploadAsset(projectId: string | null, file: File, purpose: 'generation_input' | 'project_reference' = 'generation_input') {
  const form = new FormData(); form.append('file', file); form.append('purpose', purpose); if (projectId) form.append('project_id', projectId)
  return request<Asset>('/assets', { method: 'POST', body: form })
}
export function getAsset(assetId: string) { return request<Asset>(`/assets/${assetId}`) }
export function deleteAsset(assetId: string) { return request<void>(`/assets/${assetId}`, { method: 'DELETE' }) }

export function createGeneration(payload: { project_id: string; input_asset_id?: string | null; type: GenerationMode; prompt: string; composition_mode?: 'replace'|'masked_edit'; edit_region?: NormalizedRect|null; protected_regions?: NormalizedRect[] }) {
  return request<Generation>('/generations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function repeatGeneration(generationId: string) { return request<Generation>(`/generations/${generationId}/repeat`, { method: 'POST' }) }
export function getGeneration(generationId: string) { return request<Generation>(`/generations/${generationId}`) }
export function listGenerations(projectId?: string, limit = 50, cursor?: string | null) {
  const params = new URLSearchParams({ limit: String(limit) }); if (projectId) params.set('project_id', projectId); if (cursor) params.set('cursor', cursor)
  return request<GenerationList>(`/generations?${params}`)
}
export function listIdeas(limit = 50, offset = 0) {
  const params = new URLSearchParams({ limit:String(limit), offset:String(offset) })
  return request<Idea[]>(`/ideas?${params}`)
}
export function getIdea(ideaId: string) { return request<Idea>(`/ideas/${ideaId}`) }
export function publishIdea(generationId: string) { return request<AdminIdea>('/ideas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ generation_id: generationId }) }) }
export function getOwnIdeaPublication(generationId: string) { return request<AdminIdea | null>(`/ideas/mine/${generationId}`) }
export function unpublishIdea(generationId: string) { return request<AdminIdea>(`/ideas/mine/${generationId}`, { method: 'DELETE' }) }
export function saveIdea(ideaId: string) { return request<{ idea_id:string; is_saved:boolean }>(`/ideas/${ideaId}/save`, { method: 'PUT' }) }
export function unsaveIdea(ideaId: string) { return request<{ idea_id:string; is_saved:boolean }>(`/ideas/${ideaId}/save`, { method: 'DELETE' }) }
export function startProjectFromIdea(ideaId: string) { return request<Project>(`/ideas/${ideaId}/project`, { method: 'POST' }) }

export function getBillingSummary() { return request<BillingSummary>('/billing') }
export function createBillingPayment(packageCode: string, receiptEmail?: string | null) {
  return request<BillingPayment>('/billing/payments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ package_code: packageCode, receipt_email: receiptEmail || null }) })
}
export function getBillingPayment(paymentId: string) { return request<BillingPayment>(`/billing/payments/${paymentId}`) }

export function adminOverview() { return request<AdminOverview>('/admin/overview') }
export function adminListTariffs() { return request<AdminTariff[]>('/admin/tariffs') }
export function adminCreateTariff(payload: { code: string; name: string; description?: string | null; credits: number; amount: string; currency: string; is_active: boolean; sort_order: number }) {
  return request<AdminTariff>('/admin/tariffs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminUpdateTariff(id: string, payload: Partial<{ name: string; description: string | null; credits: number; amount: string; currency: string; is_active: boolean; sort_order: number }>) {
  return request<AdminTariff>(`/admin/tariffs/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminArchiveTariff(id: string) { return request<AdminTariff>(`/admin/tariffs/${id}`, { method: 'DELETE' }) }
export function adminGetBillingSettings() { return request<AdminBillingSettings>('/admin/billing-settings') }
export function adminUpdateBillingSettings(payload: Omit<AdminBillingSettings, 'updated_at'>) { return request<AdminBillingSettings>('/admin/billing-settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }

export function adminGetQuestionnaireCatalog() { return request<AdminQuestionnaireCatalog>('/admin/questionnaires') }
export function adminUpdateQuestionnaireCatalog(payload: { catalog: QuestionnaireCatalog; source_texts: Record<string, QuestionnaireSourceText> }) {
  return request<AdminQuestionnaireCatalog>('/admin/questionnaires', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminListQuestionnaireApplications() { return request<QuestionnaireApplication[]>('/admin/questionnaire-applications') }
export function adminRetryQuestionnaireApplicationTelegram(applicationId: string) { return request<void>(`/admin/questionnaire-applications/${applicationId}/telegram-retry`, { method: 'POST' }) }

export function adminListIdeas() { return request<AdminIdea[]>('/admin/ideas') }
export function adminUpdateIdea(id: string, payload: Partial<{ is_active: boolean; sort_order: number }>) {
  return request<AdminIdea>(`/admin/ideas/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminArchiveIdea(id: string) { return request<AdminIdea>(`/admin/ideas/${id}`, { method: 'DELETE' }) }

export function adminGetGenerationSettings() { return request<AdminGenerationSettings>('/admin/generation') }
export function adminUpdateGenerationSettings(payload: {
  primary_model: string
  fallback_model: string | null
  primary_timeout_seconds: number
  primary_params: Record<string, unknown>
  fallback_params: Record<string, unknown>
  mode_params: Record<string, Record<string, unknown>>
  masked_edit_provider_context_margin_fraction: number
  masked_edit_feather_fraction: number
  masked_edit_feather_min_px: number
  masked_edit_feather_max_px: number
  masked_edit_recomposite_feather_multiplier: number
  masked_edit_boundary_band_px: number
  masked_edit_max_luma_excess: number
  masked_edit_max_color_excess: number
  masked_edit_max_straight_edge_fraction: number
  generation_quality_max_retries: number
}) {
  return request<AdminGenerationSettings>('/admin/generation', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminListGenerationSandboxHistory(limit = 30) {
  return request<AdminAiHistoryItem[]>(`/admin/generation/sandbox/history?limit=${limit}`)
}
export function adminCreateGenerationSandbox(payload: { model_name: string; prompt: string; params: Record<string, unknown> }) {
  return request<Generation>('/admin/generation/sandbox', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminCreateGenerationFlyoverGif(payload: { source_generation_id: string; model_name: string; prompt: string; params: Record<string, unknown>; keyframe_count: number; inbetween_frames: number; frame_duration_ms: number }) {
  return request<Generation>('/admin/generation/flyover-gif', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminCreateGenerationOrbit(payload: { source_generation_id: string; model_name: string; prompt: string; params: Record<string, unknown>; frame_count: number; frame_duration_ms: number }) {
  return request<Generation>('/admin/generation/orbit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
export function adminListGenerationPrices() { return request<AdminGenerationPrice[]>('/admin/generation-prices') }
export function adminUpdateGenerationPrice(mode: GenerationMode, credits: number, isActive: boolean) { return request<AdminGenerationPrice>(`/admin/generation-prices/${mode}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ credits, is_active: isActive }) }) }
export function adminListPrompts() { return request<AdminPrompt[]>('/admin/prompts') }
export function adminUpdatePrompt(mode: GenerationMode, template: string) { return request<AdminPrompt>(`/admin/prompts/${mode}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ template }) }) }

export function adminListUsers() { return request<AdminUser[]>('/admin/users') }
export function adminAdjustCredits(userId: string, delta: number, reason: string) { return request<AdminUser>(`/admin/users/${userId}/credits`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delta, reason }) }) }
export function adminListCreditTransactions(userId?: string) { const params = new URLSearchParams({ limit: '200' }); if (userId) params.set('user_id', userId); return request<AdminCreditTransaction[]>(`/admin/credit-transactions?${params}`) }
export function adminUpdateUser(userId: string, payload: { status?: 'active' | 'disabled'; role?: UserRole }) { return request<AdminUser>(`/admin/users/${userId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }

export function adminListPayments() { return request<AdminPayment[]>('/admin/payments') }
export function adminReconcilePayment(paymentId: string, providerPaymentId?: string) { return request<AdminPayment>(`/admin/payments/${paymentId}/reconcile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: providerPaymentId ? JSON.stringify({ provider_payment_id: providerPaymentId }) : undefined }) }
export function adminRefundPayment(paymentId: string) { return request<AdminPayment>(`/admin/payments/${paymentId}/refund`, { method: 'POST' }) }

export function adminListBroadcasts() { return request<AdminBroadcast[]>('/admin/broadcasts') }
export function adminCreateBroadcast(text: string, segment: BroadcastSegment = 'all', scheduledAt?: string | null) { return request<AdminBroadcast>('/admin/broadcasts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, segment, scheduled_at: scheduledAt || null }) }) }
export function adminSendBroadcast(id: string) { return request<AdminBroadcast>(`/admin/broadcasts/${id}/send`, { method: 'POST' }) }
export function adminRetryBroadcast(id: string) { return request<AdminBroadcast>(`/admin/broadcasts/${id}/retry`, { method: 'POST' }) }
export function adminCancelBroadcast(id: string) { return request<AdminBroadcast>(`/admin/broadcasts/${id}/cancel`, { method: 'POST' }) }

export function adminGetTelegramContent() { return request<AdminTelegramContent>('/admin/telegram-content') }
export function adminUpdateTelegramContent(payload: Omit<AdminTelegramContent, 'configured' | 'updated_at'>) { return request<AdminTelegramContent>('/admin/telegram-content', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }

export function adminGetOperationalSettings() { return request<AdminOperationalSettings>('/admin/operations') }
export function adminUpdateOperationalSettings(payload: Omit<AdminOperationalSettings, 'updated_at'>) { return request<AdminOperationalSettings>('/admin/operations', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export function adminListAudit() { return request<AdminAudit[]>('/admin/audit') }
