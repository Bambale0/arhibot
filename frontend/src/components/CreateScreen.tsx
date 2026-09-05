import { useEffect, useState } from 'react'
import * as api from '../api'
import type { GenerationMode, Project } from '../types'
import { ArrowIcon, HomeIcon, PlanIcon, RoomIcon, SiteIcon } from './Icons'

const modes: { id: GenerationMode; title: string; text: string; icon: typeof HomeIcon }[] = [
  { id: 'floor_plan', title: 'Планировка дома', text: 'Сформировать функциональную схему дома по площади, этажности и составу помещений.', icon: PlanIcon },
  { id: 'facade', title: 'Внешний облик дома', text: 'Создать концепцию фасада по исходному дому или референсу.', icon: HomeIcon },
  { id: 'master_plan', title: 'Мастер-план участка', text: 'Разместить дом, парковку, террасу, баню и основные зоны участка.', icon: SiteIcon },
  { id: 'interior', title: 'Дизайн помещений', text: 'Создать интерьерную концепцию комнаты по фотографии и пожеланиям.', icon: RoomIcon },
]

export function CreateScreen({
  initialMode,
  initialPrompt,
  onOpenProject,
}: {
  initialMode?: GenerationMode | null
  initialPrompt?: string
  onOpenProject: (project: Project, mode: GenerationMode, prompt?: string) => void
}) {
  const [mode, setMode] = useState<GenerationMode>(initialMode || 'floor_plan')
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { if (initialMode) setMode(initialMode) }, [initialMode])
  useEffect(() => {
    api.listProjects(null, 50).then((page) => setProjects(page.items.filter((p) => p.status === 'active'))).catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить проекты')).finally(() => setLoading(false))
  }, [])

  return (
    <section className="page-content create-page">
      <div className="page-heading-row"><div><span className="eyebrow">СОЗДАТЬ В AUROOM</span><h1>Что проектируем?</h1><p>Выберите задачу, затем проект, с которым хотите работать.</p></div></div>
      <div className="create-mode-grid">
        {modes.map((item) => { const Icon = item.icon; return <button key={item.id} className={`create-mode-card ${mode === item.id ? 'selected' : ''}`} onClick={() => setMode(item.id)}><Icon /><div><strong>{item.title}</strong><p>{item.text}</p></div><span className="radio-dot" /></button> })}
      </div>
      <div className="create-project-section">
        <div className="section-title-row"><div><span className="eyebrow">ПРОЕКТ</span><h2>Выберите проект</h2></div><span>{projects.length} активных</span></div>
        {error && <div className="banner-error">{error}</div>}
        {loading ? <div className="create-project-list"><div className="project-pick skeleton-card"/></div> : projects.length ? (
          <div className="create-project-list">{projects.map((project) => <button className="project-pick" key={project.id} onClick={() => onOpenProject(project, mode, initialPrompt)}><div><strong>{project.name}</strong><span>{project.context.architecture_style || 'Без выбранного стиля'}</span></div><ArrowIcon /></button>)}</div>
        ) : <div className="empty-inline"><p>Пока нет активных проектов. Создайте проект на главной странице и вернитесь сюда.</p></div>}
      </div>
    </section>
  )
}
