import { useEffect, useMemo, useState } from 'react'
import * as api from '../api'
import { getQuestionnaireCatalog } from '../questionnaireApi'
import type { QuestionnaireCatalog } from '../questionnaireTypes'
import type { GenerationMode, Project } from '../types'
import { ArrowIcon, HomeIcon, PlanIcon, RoomIcon, SiteIcon } from './Icons'
import '../questionnaire.css'

const legacyModes: { id: GenerationMode; title: string; text: string; icon: typeof HomeIcon }[] = [
  { id: 'floor_plan', title: 'Планировка дома', text: 'Сформировать функциональную схему дома по площади, этажности и составу помещений.', icon: PlanIcon },
  { id: 'facade', title: 'Внешний облик дома', text: 'Создать концепцию фасада по исходному дому или референсу.', icon: HomeIcon },
  { id: 'master_plan', title: 'Мастер-план участка', text: 'Разместить дом, парковку, террасу, баню и основные зоны участка.', icon: SiteIcon },
  { id: 'interior', title: 'Дизайн помещений', text: 'Создать интерьерную концепцию комнаты по фотографии и пожеланиям.', icon: RoomIcon },
]

export function CreateScreen({ initialMode, initialPrompt, onOpenProject, onOpenQuestionnaire }: {
  initialMode?: GenerationMode | null
  initialPrompt?: string
  onOpenProject: (project: Project, mode: GenerationMode, prompt?: string) => void
  onOpenQuestionnaire: (project: Project, selectedObjects: string[]) => void
}) {
  const [catalog, setCatalog] = useState<QuestionnaireCatalog | null>(null)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [selectedObjects, setSelectedObjects] = useState<string[]>([])
  const [legacyMode, setLegacyMode] = useState<GenerationMode>(initialMode || 'facade')
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const legacy = Boolean(initialMode || initialPrompt)

  useEffect(() => { if (initialMode) setLegacyMode(initialMode) }, [initialMode])
  useEffect(() => {
    Promise.all([api.listProjects(null, 50), legacy ? Promise.resolve(null) : getQuestionnaireCatalog()])
      .then(([page, loadedCatalog]) => {
        setProjects(page.items.filter((project) => project.status === 'active'))
        if (loadedCatalog) { setCatalog(loadedCatalog); setActiveSection(loadedCatalog.sections[0]?.key || null) }
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить создание проекта'))
      .finally(() => setLoading(false))
  }, [legacy])

  const definitions = useMemo(() => new Map((catalog?.questionnaires || []).map((item) => [item.key, item])), [catalog])
  function toggleObject(key: string) { setSelectedObjects((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]) }

  if (legacy) return <section className="page-content create-page"><div className="page-heading-row"><div><span className="eyebrow">ИДЕЯ AUROOM</span><h1>Использовать идею</h1><p>Этот вход сохранён для существующей ленты идей. Новый проектный сценарий работает через точные опросники.</p></div></div><div className="create-mode-grid">{legacyModes.map((item) => { const Icon = item.icon; return <button key={item.id} className={`create-mode-card ${legacyMode === item.id ? 'selected' : ''}`} onClick={() => setLegacyMode(item.id)}><Icon /><div><strong>{item.title}</strong><p>{item.text}</p></div><span className="radio-dot" /></button> })}</div><ProjectPicker projects={projects} loading={loading} error={error} onPick={(project) => onOpenProject(project, legacyMode, initialPrompt)} /></section>

  const section = catalog?.sections.find((item) => item.key === activeSection) || null
  return <section className="page-content create-page questionnaire-create">
    <div className="page-heading-row"><div><span className="eyebrow">СОЗДАТЬ В AUROOM</span><h1>Что проектируем?</h1><p>Сначала раздел, затем один или несколько элементов. Порядок и вопросы берутся из утверждённой сборки опросников.</p></div></div>
    {error && <div className="banner-error">{error}</div>}
    {loading || !catalog ? <div>Загружаем опросники…</div> : <>
      <div className="questionnaire-section-tabs">{catalog.sections.map((item) => <button key={item.key} className={item.key === activeSection ? 'selected' : ''} onClick={() => setActiveSection(item.key)}><strong>{item.title}</strong><span>{item.object_keys.filter((key) => selectedObjects.includes(key)).length || ''}</span></button>)}</div>
      {section && <div className="questionnaire-object-grid">{section.object_keys.map((key) => { const definition = definitions.get(key); const selected = selectedObjects.includes(key); return <button key={key} className={`questionnaire-object-card ${selected ? 'selected' : ''}`} onClick={() => toggleObject(key)}><div><strong>{definition?.title || key}</strong><small>{definition?.source_file}</small></div><span className="questionnaire-check">{selected ? '✓' : '+'}</span></button> })}</div>}
      <div className="questionnaire-selection-summary"><strong>Выбрано: {selectedObjects.length}</strong><span>{selectedObjects.map((key) => definitions.get(key)?.title).filter(Boolean).join(' · ') || 'Выберите хотя бы один объект'}</span></div>
      <ProjectPicker projects={projects} loading={false} error={null} disabled={!selectedObjects.length} onPick={(project) => onOpenQuestionnaire(project, selectedObjects)} title="Выберите проект и начните опрос" />
    </>}
  </section>
}

function ProjectPicker({ projects, loading, error, disabled = false, onPick, title = 'Выберите проект' }: { projects:Project[]; loading:boolean; error:string|null; disabled?:boolean; onPick:(project:Project)=>void; title?:string }) {
  return <div className="create-project-section"><div className="section-title-row"><div><span className="eyebrow">ПРОЕКТ</span><h2>{title}</h2></div><span>{projects.length} активных</span></div>{error && <div className="banner-error">{error}</div>}{loading ? <div className="create-project-list"><div className="project-pick skeleton-card"/></div> : projects.length ? <div className="create-project-list">{projects.map((project) => <button disabled={disabled} className="project-pick" key={project.id} onClick={() => onPick(project)}><div><strong>{project.name}</strong><span>{disabled ? 'Сначала выберите объект' : 'Открыть опросник'}</span></div><ArrowIcon /></button>)}</div> : <div className="empty-inline"><p>Пока нет активных проектов. Создайте проект на главной странице и вернитесь сюда.</p></div>}</div>
}
