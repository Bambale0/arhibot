import type {
  AdminAudit,
  AdminBroadcast,
  AdminGenerationSettings,
  AdminIdea,
  AdminOverview,
  AdminPayment,
  AdminPrompt,
  AdminTariff,
  AdminUser,
  Asset,
  BillingPayment,
  BillingSummary,
  Generation,
  GenerationList,
  GenerationMode,
  Idea,
  Project,
  ProjectContext,
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

function migrateLegacyTokens() {
  if (!localStorage.getItem(ACCESS_KEY) && localStorage.getItem(LEGACY_ACCESS_KEY)) {
    localStorage.setItem(ACCESS_KEY, localStorage.getItem(LEGACY_ACCESS_KEY) || '')
  }
  if (!localStorage.getItem(REFRESH_KEY) && localStorage.getItem(LEGACY_REFRESH_KEY)) {
    localStorage.setItem(REFRESH_KEY, localStorage.getItem(LEGACY_REFRESH_KEY) || '')
  }
  localStorage.removeItem(LEGACY_ACCESS_KEY)
  localStorage.removeItem(LEGACY_REFRESH_KEY)
}

migrateLegacyTokens()

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

type RequestOptions = RequestInit & { auth?: boolean; retryAuth?: boolean }

function saveTokens(pair: TokenPair) {
  localStorage.setItem(ACCESS_KEY, pair.access_token)
  localStorage.setItem(REFRESH_KEY, pair.refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(LEGACY_ACCESS_KEY)
  localStorage.removeItem(LEGACY_REFRESH_KEY)
}

export function hasStoredSession() {
  return Boolean(localStorage.getItem(ACCESS_KEY) || localStorage.getItem(REFRESH_KEY))
}

async function parseError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {}
  try {
    body = await response.json()
  } catch {
    // keep generic error
  }
  const title = typeof body.title === 'string' ? body.title : `HTTP ${response.status}`
  const detail = typeof body.detail === 'string' ? body.detail : undefined
  return new ApiError(response.status, detail || title, detail)
}

let refreshPromise: Promise<TokenPair> | null = null

async function refreshSession(): Promise<TokenPair> {
  const token = localStorage.getItem(REFRESH_KEY)
  if (!token) throw new ApiError(401, 'Сессия закончилась')

  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
    })
      .then(async (response) => {
        if (!response.ok) throw await parseError(response)
        const pair = (await response.json()) as TokenPair
        saveTokens(pair)
        return pair
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true, retryAuth = true, headers, ...rest } = options
  const finalHeaders = new Headers(headers)
  const accessToken = localStorage.getItem(ACCESS_KEY)
  if (auth && accessToken) finalHeaders.set('Authorization', `Bearer ${accessToken}`)

  const response = await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders })
  if (response.status === 401 && auth && retryAuth && localStorage.getItem(REFRESH_KEY)) {
    try {
      await refreshSession()
      return request<T>(path, { ...options, retryAuth: false })
    } catch (error) {
      clearTokens()
      throw error
    }
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const pair = await request<TokenPair>('/auth/login', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  saveTokens(pair)
  return pair
}

export async function loginTelegram(initData: string): Promise<TokenPair> {
  const pair = await request<TokenPair>('/auth/telegram', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })
  saveTokens(pair)
  return pair
}

export function getMe() {
  return request<User>('/me')
}

export async function logout() {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  try {
    if (refreshToken) {
      await request('/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    }
  } finally {
    clearTokens()
  }
}

export function listProjects(cursor?: string | null, limit = 20) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return request<ProjectList>(`/projects?${params}`)
}

export function createProject(payload: { name: string; description?: string; context?: ProjectContext }) {
  return request<Project>('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateProject(projectId: string, payload: Partial<{ name: string; description: string | null; status: string; context: ProjectContext }>) {
  return request<Project>(`/projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteProject(projectId: string) {
  return request<void>(`/projects/${projectId}`, { method: 'DELETE' })
}

export async function uploadAsset(projectId: string, file: File, purpose: 'generation_input' | 'project_reference' = 'generation_input') {
  const form = new FormData()
  form.append('file', file)
  form.append('purpose', purpose)
  form.append('project_id', projectId)
  return request<Asset>('/assets', { method: 'POST', body: form })
}

export function deleteAsset(assetId: string) {
  return request<void>(`/assets/${assetId}`, { method: 'DELETE' })
}

export function createGeneration(payload: {
  project_id: string
  input_asset_id: string
  type: GenerationMode
  prompt: string
}) {
  return request<Generation>('/generations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getGeneration(generationId: string) {
  return request<Generation>(`/generations/${generationId}`)
}

export function listGenerations(projectId?: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (projectId) params.set('project_id', projectId)
  return request<GenerationList>(`/generations?${params}`)
}

export function listIdeas() {
  return request<Idea[]>('/ideas')
}

export function getBillingSummary() {
  return request<BillingSummary>('/billing')
}

export function createBillingPayment(packageCode: string) {
  return request<BillingPayment>('/billing/payments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_code: packageCode }),
  })
}

export function getBillingPayment(paymentId: string) {
  return request<BillingPayment>(`/billing/payments/${paymentId}`)
}

export function adminOverview() {
  return request<AdminOverview>('/admin/overview')
}

export function adminListTariffs() {
  return request<AdminTariff[]>('/admin/tariffs')
}

export function adminCreateTariff(payload: {
  code: string
  name: string
  description?: string | null
  credits: number
  amount: string
  currency: string
  is_active: boolean
  sort_order: number
}) {
  return request<AdminTariff>('/admin/tariffs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminUpdateTariff(id: string, payload: Partial<{
  name: string
  description: string | null
  credits: number
  amount: string
  currency: string
  is_active: boolean
  sort_order: number
}>) {
  return request<AdminTariff>(`/admin/tariffs/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminArchiveTariff(id: string) {
  return request<AdminTariff>(`/admin/tariffs/${id}`, { method: 'DELETE' })
}

export function adminListIdeas() {
  return request<AdminIdea[]>('/admin/ideas')
}

export function adminCreateIdea(payload: {
  title: string
  category: string
  text: string
  generation_type: GenerationMode
  prompt: string
  is_active: boolean
  sort_order: number
}) {
  return request<AdminIdea>('/admin/ideas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminUpdateIdea(id: string, payload: Partial<{
  title: string
  category: string
  text: string
  generation_type: GenerationMode
  prompt: string
  is_active: boolean
  sort_order: number
}>) {
  return request<AdminIdea>(`/admin/ideas/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminArchiveIdea(id: string) {
  return request<AdminIdea>(`/admin/ideas/${id}`, { method: 'DELETE' })
}

export function adminGetGenerationSettings() {
  return request<AdminGenerationSettings>('/admin/generation')
}

export function adminUpdateGenerationSettings(payload: Omit<AdminGenerationSettings, 'updated_at'>) {
  return request<AdminGenerationSettings>('/admin/generation', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminListPrompts() {
  return request<AdminPrompt[]>('/admin/prompts')
}

export function adminUpdatePrompt(mode: GenerationMode, template: string) {
  return request<AdminPrompt>(`/admin/prompts/${mode}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template }),
  })
}

export function adminListUsers() {
  return request<AdminUser[]>('/admin/users')
}

export function adminAdjustCredits(userId: string, delta: number, reason: string) {
  return request<AdminUser>(`/admin/users/${userId}/credits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delta, reason }),
  })
}

export function adminUpdateUser(userId: string, payload: { status?: 'active' | 'disabled'; role?: UserRole }) {
  return request<AdminUser>(`/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function adminListPayments() {
  return request<AdminPayment[]>('/admin/payments')
}

export function adminReconcilePayment(paymentId: string) {
  return request<AdminPayment>(`/admin/payments/${paymentId}/reconcile`, { method: 'POST' })
}

export function adminListBroadcasts() {
  return request<AdminBroadcast[]>('/admin/broadcasts')
}

export function adminCreateBroadcast(text: string) {
  return request<AdminBroadcast>('/admin/broadcasts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export function adminSendBroadcast(id: string) {
  return request<AdminBroadcast>(`/admin/broadcasts/${id}/send`, { method: 'POST' })
}

export function adminListAudit() {
  return request<AdminAudit[]>('/admin/audit')
}
