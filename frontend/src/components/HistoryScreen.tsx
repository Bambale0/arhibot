import { useMemo, useState } from 'react'
import { clearDemoHistory, loadDemoHistory } from '../history'
import type { GenerationMode } from '../types'

const labels: Record<GenerationMode, string> = {
  floor_plan: 'Планировка дома',
  facade: 'Фасад',
  master_plan: 'Мастер-план участка',
  interior: 'Дизайн помещения',
}

export function HistoryScreen() {
  const [version, setVersion] = useState(0)
  const items = useMemo(() => loadDemoHistory(), [version])
  return (
    <section className="page-content history-page">
      <div className="page-heading-row"><div><span className="eyebrow">ВАШИ РЕЗУЛЬТАТЫ</span><h1>История</h1><p>Последние генерации в текущей песочнице AuRoom.</p></div>{items.length > 0 && <button className="secondary-button" onClick={() => { clearDemoHistory(); setVersion((v) => v + 1) }}>Очистить</button>}</div>
      {items.length ? <div className="history-grid">{items.map((item) => <article className="history-card" key={item.id}><img src={item.sourceUrl} alt="Результат генерации"/><div><span className="history-mode">{labels[item.mode]}</span><h3>{item.projectName}</h3><p>{item.prompt || 'Без дополнительных пожеланий'}</p><small>{new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.createdAt))}</small></div></article>)}</div> : <div className="empty-state"><h2>Пока пусто</h2><p>После тестовой генерации результат появится здесь и сохранится на этом устройстве.</p></div>}
    </section>
  )
}
