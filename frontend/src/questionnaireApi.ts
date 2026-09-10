import { request as apiRequest } from './api'
import type { Generation, Project } from './types'
import type { DesignSession, QuestionnaireApplicationSubmitResponse, QuestionnaireCatalog } from './questionnaireTypes'

export function getQuestionnaireCatalog():Promise<QuestionnaireCatalog> {
  return apiRequest<QuestionnaireCatalog>('/questionnaires')
}

export function startQuestionnaireProject(selectedObjects:string[]):Promise<Project> {
  return apiRequest<Project>('/questionnaire-projects', {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify({ selected_objects:selectedObjects }),
  })
}

export function discardQuestionnaireDraft(projectId:string):Promise<void> {
  return apiRequest<void>(`/questionnaire-projects/${projectId}/draft`, { method:'DELETE' })
}

export async function getQuestionnaireSession(projectId:string):Promise<DesignSession|null> {
  const response = await apiRequest<{ session:DesignSession|null }>(`/projects/${projectId}/questionnaire-session`)
  return response.session
}

export async function saveQuestionnaireSession(projectId:string, session:DesignSession):Promise<DesignSession> {
  const response = await apiRequest<{ session:DesignSession }>(`/projects/${projectId}/questionnaire-session`, {
    method:'PUT',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify(session),
  })
  return response.session
}

export function submitQuestionnaireApplication(projectId:string, session:DesignSession):Promise<QuestionnaireApplicationSubmitResponse> {
  return apiRequest<QuestionnaireApplicationSubmitResponse>(`/projects/${projectId}/questionnaire-application`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body:JSON.stringify(session),
  })
}

export function createQuestionnaireGeneration(projectId:string):Promise<Generation> {
  return apiRequest<Generation>(`/projects/${projectId}/questionnaire-generation`, { method:'POST' })
}

export function getQuestionnaireGeneration(projectId:string, generationId:string):Promise<Generation> {
  return apiRequest<Generation>(`/projects/${projectId}/questionnaire-generation/${generationId}`)
}
