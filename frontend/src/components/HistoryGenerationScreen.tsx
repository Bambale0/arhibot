import { useState } from 'react'
import type { Generation, Project } from '../types'
import { BackIcon, SparkIcon } from './Icons'

const statusText: Record<Generation['status'], string> = {
  queued: 'Работа в очереди',
  processing: 'AuRoom создаёт работу…',
  completed: 'Готовая работа',
  failed: 'Работу не удалось завершить',
}

export function HistoryGenerationScreen({ project, generation, onBack }: {
  project: Project
  generation: Generation
  onBack: () => void
}) {
  const [mediaFailed, setMediaFailed] = useState(false)
  return <main className="questionnaire-shell">
    <header className="questionnaire-topbar">
      <button className="back-button" type="button" onClick={onBack}><BackIcon /> Назад</button>
      <strong>{project.name}</strong>
      <span>История</span>
    </header>
    <section className="questionnaire-card">
      <span className="eyebrow">РЕЗУЛЬТАТ AUROOM</span>
      <h1>{statusText[generation.status]}</h1>
      {generation.output_asset && !mediaFailed ? (
        <div className="questionnaire-result">
          {generation.output_asset.type === 'video'
            ? <video controls playsInline preload="metadata" src={generation.output_asset.url} onError={() => setMediaFailed(true)}>Ваш браузер не поддерживает видео.</video>
            : <img src={generation.output_asset.url} alt="Сгенерированная работа AuRoom" onError={() => setMediaFailed(true)} />}
        </div>
      ) : (
        <div className="empty-state">
          <SparkIcon />
          <p>{mediaFailed ? 'Медиа временно недоступно. Попробуйте открыть работу позже.' : generation.status === 'failed' ? 'Готового результата для этой генерации нет.' : 'Готовый результат появится после завершения генерации.'}</p>
        </div>
      )}
      <button className="secondary-button questionnaire-wide" type="button" onClick={onBack}>Вернуться в историю</button>
    </section>
  </main>
}
