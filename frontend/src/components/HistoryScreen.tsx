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

export function HistoryScreen() {
  const [items, setItems] = useState<Generation[]>([])
  const [projectNames, setProjectNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [history, projects] = await Promise.all([
          api.listGenerations(undefined, 100),
          api.listProjects(null, 100),
        ])
        if (cancelled) return
        setItems(history.items)
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

  return (
    <section className="page-content history-page">
      <div className="page-heading-row"><div><span className="eyebrow">ВАШИ РЕЗУЛЬТАТЫ</span><h1>История</h1><p>Все генерации AuRoom, сохранённые на сервере.</p></div></div>
      {error && <div className="banner-error">{error}</div>}
      {loading ? <div className="empty-state"><p>Загружаем историю…</p></div> : items.length ? <div className="history-grid">{items.map((item) => <article className="history-card" key={item.id}>{item.output_asset ? <img src={item.output_asset.url} alt="Результат генерации"/> : <div className="history-placeholder"><SparkIcon/><span>{statusLabels[item.status]}</span></div>}<div><span className="history-mode">{labels[item.type]} · {statusLabels[item.status]}</span><h3>{projectNames[item.project_id] || 'Проект AuRoom'}</h3><p>{item.status === 'failed' ? (item.error || 'Генерация завершилась с ошибкой') : (item.prompt || 'Без дополнительных пожеланий')}</p><small>{new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}{item.fallback_used ? ' · резервная модель' : ''}</small></div></article>)}</div> : <div className="empty-state"><h2>Пока пусто</h2><p>После первой генерации результат появится здесь и будет доступен на любом устройстве.</p></div>}
    </section>
  )
}
