import { useEffect, useMemo, useState } from 'react'
import * as api from '../api'
import { getQuestionnaireCatalog } from '../questionnaireApi'
import type { QuestionnaireCatalog } from '../questionnaireTypes'
import type { GenerationMode, Project } from '../types'
import { ArrowIcon, HomeIcon, PlanIcon, RoomIcon, SiteIcon } from './Icons'
import '../questionnaire.css'
import '../create-questionnaire.css'

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
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [projectsError, setProjectsError] = useState<string | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const legacy = Boolean(initialMode || initialPrompt)

  useEffect(() => { if (initialMode) setLegacyMode(initialMode) }, [initialMode])
  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    setProjectsError(null)
    void api.listProjects(null, 50)
      .then((page) => { if (!cancelled) setProjects(page.items.filter((project) => project.status === 'active')) })
      .catch((err) => { if (!cancelled) setProjectsError(err instanceof Error ? err.message : 'Не удалось загрузить проекты') })
      .finally(() => { if (!cancelled) setProjectsLoading(false) })

    if (legacy) {
      setCatalogLoading(false)
      setCatalogError(null)
      return () => { cancelled = true }
    }

    setCatalogLoading(true)
    setCatalogError(null)
    void getQuestionnaireCatalog()
      .then((loadedCatalog) => {
        if (cancelled) return
        setCatalog(loadedCatalog)
        setActiveSection((current) => current && loadedCatalog.sections.some((section) => section.key === current) ? current : loadedCatalog.sections[0]?.key || null)
      })
      .catch((err) => { if (!cancelled) setCatalogError(err instanceof Error ? err.message : 'Не удалось загрузить опросники') })
      .finally(() => { if (!cancelled) setCatalogLoading(false) })

    return () => { cancelled = true }
  }, [legacy])

  const definitions = useMemo(() => new Map((catalog?.questionnaires || []).map((item) => [item.key, item])), [catalog])
  function toggleObject(key: string) { setSelectedObjects((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]) }

  if (legacy) return <section className="page-content create-page"><div className="page-heading-row"><div><span className="eyebrow">ИДЕЯ AUROOM</span><h1>Использовать идею</h1><p>Этот вход сохранён для существующей ленты идей. Новый проектный сценарий работает через точные опросники.</p></div></div><div className="create-mode-grid">{legacyModes.map((item) => { const Icon = item.icon; return <button key={item.id} className={`create-mode-card ${legacyMode === item.id ? 'selected' : ''}`} onClick={() => setLegacyMode(item.id)}><Icon /><div><strong>{item.title}</strong><p>{item.text}</p></div><span className="radio-dot" /></button> })}</div><ProjectPicker projects={projects} loading={projectsLoading} error={projectsError} onPick={(project) => onOpenProject(project, legacyMode, initialPrompt)} /></section>

  const section = catalog?.sections.find((item) => item.key === activeSection) || null
  const selectedTitles = selectedObjects.map((key) => definitions.get(key)?.title).filter(Boolean)

  return <section className="page-content create-page questionnaire-create">
    <div className="page-heading-row">
      <div>
        <h1>Что проектируем?</h1>
        <p>Выберите раздел и один или несколько объектов. Дальше AuRoom задаст только нужные вопросы.</p>
      </div>
    </div>

    {catalogError && <div className="banner-error">{catalogError}</div>}
    {catalogLoading ? <div>Загружаем опросники…</div> : !catalog ? <div>Опросники сейчас недоступны.</div> : <>
      <div className="questionnaire-section-tabs" role="tablist" aria-label="Разделы проектирования">
        {catalog.sections.map((item) => {
          const count = item.object_keys.filter((key) => selectedObjects.includes(key)).length
          return <button
            key={item.key}
            role="tab"
            aria-selected={item.key === activeSection}
            className={item.key === activeSection ? 'selected' : ''}
            onClick={() => setActiveSection(item.key)}
          >
            <strong>{item.title}</strong>
            <span aria-label={count ? `Выбрано: ${count}` : 'Ничего не выбрано'}>{count || ''}</span>
          </button>
        })}
      </div>

      {section && <div className="questionnaire-object-grid" role="group" aria-label={section.title}>
        {section.object_keys.map((key) => {
          const definition = definitions.get(key)
          const selected = selectedObjects.includes(key)
          return <button
            key={key}
            className={`questionnaire-object-card ${selected ? 'selected' : ''}`}
            aria-pressed={selected}
            onClick={() => toggleObject(key)}
          >
            <div><strong>{definition?.title || key}</strong></div>
            <span className="questionnaire-check" aria-hidden="true">{selected ? '✓' : '+'}</span>
          </button>
        })}
      </div>}

      <div className="questionnaire-selection-summary" aria-live="polite">
        <strong>{selectedObjects.length ? `Выбрано: ${selectedObjects.length}` : 'Выберите объект'}</strong>
        <span>{selectedTitles.length ? selectedTitles.join(' · ') : 'Можно выбрать несколько объектов из разных разделов.'}</span>
      </div>

      {selectedObjects.length > 0 && <ProjectPicker
        projects={projects}
        loading={projectsLoading}
        error={projectsError}
        onPick={(project) => onOpenQuestionnaire(project, selectedObjects)}
        title="Выберите проект"
      />}
    </>}
  </section>
}

function ProjectPicker({ projects, loading, error, disabled = false, onPick, title = 'Выберите проект' }: { projects:Project[]; loading:boolean; error:string|null; disabled?:boolean; onPick:(project:Project)=>void; title?:string }) {
  return <div className="create-project-section"><div className="section-title-row"><div><span className="eyebrow">ПРОЕКТ</span><h2>{title}</h2></div><span>{projects.length} активных</span></div>{error && <div className="banner-error">{error}</div>}{loading ? <div className="create-project-list"><div className="project-pick skeleton-card"/></div> : projects.length ? <div className="create-project-list">{projects.map((project) => <button disabled={disabled} className="project-pick" key={project.id} onClick={() => onPick(project)}><div><strong>{project.name}</strong><span>{disabled ? 'Сначала выберите объект' : 'Открыть опросник'}</span></div><ArrowIcon /></button>)}</div> : error ? <div className="empty-inline"><p>Не удалось загрузить проекты. Опросники доступны, но начать работу можно после восстановления списка проектов.</p></div> : <div className="empty-inline"><p>Пока нет активных проектов. Создайте проект на главной странице и вернитесь сюда.</p></div>}</div>
}
