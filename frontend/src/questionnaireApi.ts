import type { QuestionnaireCatalog } from './questionnaireTypes'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export async function getQuestionnaireCatalog(): Promise<QuestionnaireCatalog> {
  const response = await fetch(`${API_BASE}/questionnaires`)
  if (!response.ok) throw new Error('Не удалось загрузить опросники AuRoom.')
  return response.json() as Promise<QuestionnaireCatalog>
}
