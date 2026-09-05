import { useEffect, useState } from 'react'
import * as api from '../api'
import type { Generation, GenerationMode } from '../types'
import { SparkIcon } from './Icons'

const labels: Record<GenerationMode, string> = {
  floor_plan: 'Планировка дома',
  facade: 'Фасад',
  master_plan: 'Мастер-план участка',
  interior: 'Дизайн помещения',
}

const statusLabels: Record<Generation['status'], string> = {
  queued: 'В очереди',
  processing: 'Генерируется',
  completed: 'Готово',
  failed: 'Ошибка',
}

type Props = {
  onOpenGeneration: (generation: Generation) => void
  onUseAsSource: (generation: Generation) => void
}

export function HistoryScreen({ onOpenGeneration, onUseAsSource }: Props) {
  const [items, setItems] = useState<Generation[]>([])
  const [projectNames, setProjectNames] = useState<Record<string, string>>({})
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [history, projects] = await Promise.all([
          api.listGenerations(undefined, 24),
          api.listProjects(null, 100),
        ])
        if (cancelled) return
        setItems(history.items)
        setCursor(history.next_cursor)
        setHasMore(history.has_more)
        setProjectNames(Object.fromEntries(projects.items.map((project) => [project.id, project.name])))
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось загрузить историю')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  async function loadMore() {
    if (!cursor || loadingMore) return
    setLoadingMore(true)
    setError(null)
    try {
      const page = await api.listGenerations(undefined, 24, cursor)
      setItems((current) => [...current, ...page.items])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить следующую страницу')
    } finally {
      setLoadingMore(false)
    }
  }

  async function repeat(item: Generation) {
    if (busyId) return
    setBusyId(item.id)
    setError(null)
    try {
      const created = await api.repeatGeneration(item.id)
      setItems((current) => [created, ...current])
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 409) {
        setError('Недостаточно кредитов для повторной генерации.')
      } else {
        setError(err instanceof Error ? err.message : 'Не удалось повторить генерацию')
      }
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="page-content history-page">
      <div className="page-heading-row"><div><span className="eyebrow">ВАШИ РЕЗУЛЬТАТЫ</span><h1>История</h1><p>Все генерации AuRoom, сохранённые на сервере.</p></div></div>
      {error && <div className="banner-error">{error}<button onClick={() => setError(null)}>Закрыть</button></div>}
      {loading ? (
        <div className="empty-state"><p>Загружаем историю…</p></div>
      ) : items.length ? (
        <>
          <div className="history-grid">
            {items.map((item) => (
              <article className="history-card" key={item.id}>
                {item.output_asset ? <img src={item.output_asset.url} alt="Результат генерации"/> : <div className="history-placeholder"><SparkIcon/><span>{statusLabels[item.status]}</span></div>}
                <div>
                  <span className="history-mode">{labels[item.type]} · {statusLabels[item.status]} · {item.credits_charged} кр.</span>
                  <h3>{projectNames[item.project_id] || 'Проект AuRoom'}</h3>
                  <p>{item.status === 'failed' ? (item.error || 'Генерация завершилась с ошибкой') : (item.prompt || 'Без дополнительных пожеланий')}</p>
                  <small>{new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}{item.fallback_used ? ' · резервная модель' : ''}</small>
                  <div className="history-actions">
                    <button className="secondary-button" onClick={() => onOpenGeneration(item)}>Открыть</button>
                    <button className="secondary-button" disabled={busyId !== null} onClick={() => void repeat(item)}>{busyId === item.id ? 'Повторяем…' : 'Повторить'}</button>
                    {item.output_asset && <button className="secondary-button" onClick={() => onUseAsSource(item)}>Использовать как исходник</button>}
                  </div>
                </div>
              </article>
            ))}
          </div>
          {hasMore && <div className="history-more"><button className="secondary-button" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? 'Загружаем…' : 'Показать ещё'}</button></div>}
        </>
      ) : (
        <div className="empty-state"><h2>Пока пусто</h2><p>После первой генерации результат появится здесь и будет доступен на любом устройстве.</p></div>
      )}
    </section>
  )
}
