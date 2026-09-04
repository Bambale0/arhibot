import type {
  Asset,
  Generation,
  GenerationList,
  GenerationMode,
  Project,
  ProjectContext,
  ProjectList,
  TokenPair,
  User,
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
