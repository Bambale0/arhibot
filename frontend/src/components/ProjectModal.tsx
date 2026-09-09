import { useState, type FormEvent } from 'react'
import type { ProjectContext } from '../types'

export type NewProjectPayload = { name: string; description?: string; context?: ProjectContext }

export function ProjectModal({ onClose, onCreate }: { onClose: () => void; onCreate: (payload: NewProjectPayload) => Promise<void> }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try { await onCreate({ name: name.trim(), context: {} }) }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось создать проект'); setBusy(false) }
  }

  return <div className="modal-backdrop" onMouseDown={onClose}><div className="modal-card" onMouseDown={(e) => e.stopPropagation()}><div className="modal-header"><div><span className="eyebrow">НОВЫЙ ПРОЕКТ</span><h2>С чего начнём?</h2></div><button className="icon-button" onClick={onClose}>×</button></div><form onSubmit={submit} className="project-form"><label>Название проекта<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Дом у озера" required maxLength={160} /></label><p>Стиль, площадь, этажность и остальные параметры задаются только в профильных опросниках — без дублирующих вопросов при создании проекта.</p>{error && <div className="inline-error">{error}</div>}<div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Отмена</button><button className="primary-button" disabled={busy}>{busy ? 'Создаём…' : 'Создать проект'}</button></div></form></div></div>
}
