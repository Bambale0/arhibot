import { useEffect, useMemo, useState } from 'react'
import { getQuestionnaireCatalog, startQuestionnaireProject as startQuestionnaireProjectApi } from '../questionnaireApi'
import type { QuestionnaireCatalog } from '../questionnaireTypes'
import type { Project } from '../types'
import { BackIcon } from './Icons'

export function CreateScreen({ onOpenQuestionnaire }: {
  onOpenQuestionnaire: (project: Project, selectedObjects: string[]) => void
}) {
  const [catalog, setCatalog] = useState<QuestionnaireCatalog | null>(null)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [selectedObjects, setSelectedObjects] = useState<string[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void getQuestionnaireCatalog()
      .then((loadedCatalog) => { if (!cancelled) setCatalog(loadedCatalog) })
      .catch((err) => { if (!cancelled) setCatalogError(err instanceof Error ? err.message : 'Не удалось загрузить опросники') })
      .finally(() => { if (!cancelled) setCatalogLoading(false) })
    return () => { cancelled = true }
  }, [])

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
