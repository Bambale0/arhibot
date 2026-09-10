import type { Project } from './types'
import type { DesignSession, QuestionnaireApplicationSubmitResponse, QuestionnaireCatalog } from './questionnaireTypes'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const ACCESS_KEY = 'auroom.access_token'

async function questionnaireRequest<T>(path:string, options:RequestInit = {}):Promise<T> {
  const headers = new Headers(options.headers)
  const accessToken = localStorage.getItem(ACCESS_KEY)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json() as { detail?:string; title?:string }
      detail = body.detail || body.title || detail
    } catch { /* generic error */ }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function getQuestionnaireCatalog():Promise<QuestionnaireCatalog> {
  return questionnaireRequest<QuestionnaireCatalog>('/questionnaires')
}

export function startQuestionnaireProject(selectedObjects:string[]):Promise<Project> {
  return questionnaireRequest<Project>('/questionnaire-projects', {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify({ selected_objects:selectedObjects }),
  })
}

export function discardQuestionnaireDraft(projectId:string):Promise<void> {
  return questionnaireRequest<void>(`/questionnaire-projects/${projectId}/draft`, { method:'DELETE' })
}

export async function getQuestionnaireSession(projectId:string):Promise<DesignSession|null> {
  const response = await questionnaireRequest<{ session:DesignSession|null }>(`/projects/${projectId}/questionnaire-session`)
  return response.session
}

export async function saveQuestionnaireSession(projectId:string, session:DesignSession):Promise<DesignSession> {
  const response = await questionnaireRequest<{ session:DesignSession }>(`/projects/${projectId}/questionnaire-session`, {
    method:'PUT',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify(session),
  })
  return response.session
}

export function submitQuestionnaireApplication(projectId:string, session:DesignSession):Promise<QuestionnaireApplicationSubmitResponse> {
  return questionnaireRequest<QuestionnaireApplicationSubmitResponse>(`/projects/${projectId}/questionnaire-application`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify(session),
  })
}
