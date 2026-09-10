import { useEffect, useMemo, useState } from 'react'
import * as api from '../api'
import { getQuestionnaireCatalog, startQuestionnaireProject as startQuestionnaireProjectApi } from '../questionnaireApi'
import type { QuestionnaireCatalog } from '../questionnaireTypes'
import type { GenerationMode, Project } from '../types'
import { ArrowIcon, BackIcon, HomeIcon, PlanIcon, RoomIcon, SiteIcon } from './Icons'
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
  const legacy = Boolean(initialMode || initialPrompt)
  const [catalog, setCatalog] = useState<QuestionnaireCatalog | null>(null)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [selectedObjects, setSelectedObjects] = useState<string[]>([])
  const [catalogLoading, setCatalogLoading] = useState(!legacy)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const [legacyMode, setLegacyMode] = useState<GenerationMode>(initialMode || 'facade')
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(legacy)
  const [projectsError, setProjectsError] = useState<string | null>(null)

  useEffect(() => { if (initialMode) setLegacyMode(initialMode) }, [initialMode])

  useEffect(() => {
    if (!legacy) return
    let cancelled = false
    setProjectsLoading(true)
    setProjectsError(null)
    void api.listProjects(null, 50)
      .then((page) => { if (!cancelled) setProjects(page.items.filter((project) => project.status === 'active')) })
      .catch((err) => { if (!cancelled) setProjectsError(err instanceof Error ? err.message : 'Не удалось загрузить проекты') })
      .finally(() => { if (!cancelled) setProjectsLoading(false) })
    return () => { cancelled = true }
  }, [legacy])

  useEffect(() => {
    if (legacy) return
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void getQuestionnaireCatalog()
      .then((loadedCatalog) => { if (!cancelled) setCatalog(loadedCatalog) })
      .catch((err) => { if (!cancelled) setCatalogError(err instanceof Error ? err.message : 'Не удалось загрузить опросники') })
      .finally(() => { if (!cancelled) setCatalogLoading(false) })
    return () => { cancelled = true }
  }, [legacy])

  const definitions = useMemo(() => new Map((catalog?.questionnaires || []).map((item) => [item.key, item])), [catalog])
  const section = catalog?.sections.find((item) => item.key === activeSection) || null
  const selectedTitles = selectedObjects.map((key) => definitions.get(key)?.title).filter((value): value is string => Boolean(value))

  function toggleObject(key: string) {
    setSelectedObjects((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])
  }

  async function startQuestionnaireProject() {
    if (!catalog || selectedObjects.length === 0 || starting) return
    setStarting(true)
    setStartError(null)
    try {
      const catalogOrder = catalog.sections.flatMap((item) => item.object_keys)
      const orderedObjects = catalogOrder.filter((key) => selectedObjects.includes(key))
      const project = await startQuestionnaireProjectApi(orderedObjects)
      onOpenQuestionnaire(project, orderedObjects)
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Не удалось создать проект')
    } finally {
      setStarting(false)
    }
  }

  if (legacy) return <section className="page-content create-page"><div className="page-heading-row"><div><span className="eyebrow">ИДЕЯ AUROOM</span><h1>Использовать идею</h1><p>Этот вход сохранён для существующей ленты идей. Новый проектный сценарий работает через точные опросники.</p></div></div><div className="create-mode-grid">{legacyModes.map((item) => { const Icon = item.icon; return <button key={item.id} className={`create-mode-card ${legacyMode === item.id ? 'selected' : ''}`} onClick={() => setLegacyMode(item.id)}><Icon /><div><strong>{item.title}</strong><p>{item.text}</p></div><span className="radio-dot" /></button> })}</div><ProjectPicker projects={projects} loading={projectsLoading} error={projectsError} onPick={(project) => onOpenProject(project, legacyMode, initialPrompt)} /></section>

  return <section className="page-content create-page questionnaire-create">
    {catalogError && <div className="banner-error">{catalogError}</div>}
    {catalogLoading ? <div className="create-loading">Загружаем варианты…</div> : !catalog ? <div className="create-loading">Варианты проектирования сейчас недоступны.</div> : activeSection && section ? <>
      <button className="create-back" type="button" onClick={() => setActiveSection(null)}><BackIcon />Все разделы</button>
      <div className="page-heading-row create-step-heading"><div><h1>{section.title}</h1><p>Выберите один или несколько объектов. Выбор можно дополнить из других разделов.</p></div></div>

      <div className="create-object-list" role="group" aria-label={section.title}>
        {section.object_keys.map((key) => {
          const definition = definitions.get(key)
          const selected = selectedObjects.includes(key)
          return <button key={key} type="button" className={`create-object-row ${selected ? 'selected' : ''}`} aria-pressed={selected} onClick={() => toggleObject(key)}>
            <span><strong>{definition?.title || key}</strong></span>
            <i aria-hidden="true">{selected ? '✓' : '+'}</i>
          </button>
        })}
      </div>

      <CreateSelectionDock
        selectedTitles={selectedTitles}
        starting={starting}
        error={startError}
        onAddSection={() => setActiveSection(null)}
        onStart={() => void startQuestionnaireProject()}
      />
    </> : <>
      <div className="page-heading-row create-step-heading"><div><h1>Что проектируем?</h1><p>Выберите раздел. Можно собрать несколько объектов из разных разделов — проект создастся автоматически.</p></div></div>

      <div className="create-section-list" role="list" aria-label="Разделы проектирования">
        {catalog.sections.map((item) => {
          const selectedCount = item.object_keys.filter((key) => selectedObjects.includes(key)).length
          return <button key={item.key} type="button" className="create-section-row" onClick={() => setActiveSection(item.key)}>
            <span><strong>{item.title}</strong><small>{selectedCount ? `Выбрано: ${selectedCount}` : `${item.object_keys.length} вариантов`}</small></span>
            <i aria-hidden="true">›</i>
          </button>
        })}
      </div>

      {selectedObjects.length > 0 && <CreateSelectionDock
        selectedTitles={selectedTitles}
        starting={starting}
        error={startError}
        onStart={() => void startQuestionnaireProject()}
      />}
    </>}
  </section>
}

function CreateSelectionDock({ selectedTitles, starting, error, onAddSection, onStart }: {
  selectedTitles: string[]
  starting: boolean
  error: string | null
  onAddSection?: () => void
  onStart: () => void
}) {
  if (!selectedTitles.length) return null
  return <div className="create-selection-dock" aria-live="polite">
    <div className="create-selection-copy"><strong>Выбрано: {selectedTitles.length}</strong><span>{selectedTitles.join(' · ')}</span></div>
    {error && <div className="banner-error">{error}</div>}
    <div className="create-selection-actions">
      {onAddSection && <button type="button" className="secondary-button" disabled={starting} onClick={onAddSection}>Добавить из другого раздела</button>}
      <button type="button" className="primary-button" disabled={starting} onClick={onStart}>{starting ? 'Создаём проект…' : 'Начать проект'}</button>
    </div>
  </div>
}

function ProjectPicker({ projects, loading, error, onPick, title = 'Выберите проект' }: { projects:Project[]; loading:boolean; error:string|null; onPick:(project:Project)=>void; title?:string }) {
  return <div className="create-project-section"><div className="section-title-row"><div><span className="eyebrow">ПРОЕКТ</span><h2>{title}</h2></div><span>{projects.length} активных</span></div>{error && <div className="banner-error">{error}</div>}{loading ? <div className="create-project-list"><div className="project-pick skeleton-card"/></div> : projects.length ? <div className="create-project-list">{projects.map((project) => <button className="project-pick" key={project.id} onClick={() => onPick(project)}><div><strong>{project.name}</strong><span>Открыть проект</span></div><ArrowIcon /></button>)}</div> : error ? <div className="empty-inline"><p>Не удалось загрузить проекты.</p></div> : <div className="empty-inline"><p>Пока нет активных проектов.</p></div>}</div>
}
