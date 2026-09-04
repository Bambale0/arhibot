import { useState, type FormEvent } from 'react'
import type { ProjectContext } from '../types'

export type NewProjectPayload = { name: string; description?: string; context?: ProjectContext }

export function ProjectModal({ onClose, onCreate }: { onClose: () => void; onCreate: (payload: NewProjectPayload) => Promise<void> }) {
  const [name, setName] = useState('')
  const [style, setStyle] = useState('')
  const [area, setArea] = useState('')
  const [floors, setFloors] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const context: ProjectContext = {}
      if (style.trim()) context.architecture_style = style.trim()
      if (area) context.house_area_m2 = Number(area)
      if (floors) context.floors = Number(floors)
      await onCreate({ name: name.trim(), context })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать проект')
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-header"><div><span className="eyebrow">НОВЫЙ ПРОЕКТ</span><h2>С чего начнём?</h2></div><button className="icon-button" onClick={onClose}>×</button></div>
        <form onSubmit={submit} className="project-form">
          <label>Название проекта<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Дом у озера" required maxLength={160} /></label>
          <div className="form-grid-2">
            <label>Стиль<input value={style} onChange={(e) => setStyle(e.target.value)} placeholder="Современный минимализм" maxLength={80} /></label>
            <label>Площадь дома, м²<input value={area} onChange={(e) => setArea(e.target.value)} inputMode="decimal" type="number" min="1" step="1" placeholder="160" /></label>
          </div>
          <label>Этажей<input value={floors} onChange={(e) => setFloors(e.target.value)} inputMode="numeric" type="number" min="1" max="10" placeholder="2" /></label>
          {error && <div className="inline-error">{error}</div>}
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Отмена</button><button className="primary-button" disabled={busy}>{busy ? 'Создаём…' : 'Создать проект'}</button></div>
        </form>
      </div>
    </div>
  )
}
