import { useEffect, useState } from 'react'
import * as api from '../api'
import type { GenerationMode, Idea } from '../types'
import { HomeIcon, PlanIcon, RoomIcon, SiteIcon } from './Icons'

const iconByMode: Record<GenerationMode, typeof HomeIcon> = {
  floor_plan: PlanIcon,
  facade: HomeIcon,
  master_plan: SiteIcon,
  interior: RoomIcon,
}

export function IdeasScreen({ onUseIdea }: { onUseIdea: (mode: GenerationMode, prompt: string) => void }) {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listIdeas()
      .then(setIdeas)
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить идеи'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <section className="page-content ideas-page">
      <div className="page-heading-row"><div><span className="eyebrow">AUROOM COLLECTION</span><h1>Идеи</h1><p>Готовые направления, которые можно взять за основу нового проекта.</p></div></div>
      {error && <div className="banner-error">{error}</div>}
      {loading ? <div className="ideas-grid"><div className="idea-card skeleton-card" /></div> : ideas.length ? (
        <div className="ideas-grid">
          {ideas.map((idea, index) => { const Icon = iconByMode[idea.generation_type]; return (
            <article className="idea-card" key={idea.id}>
              <div className={`idea-visual idea-tone-${(index % 4) + 1} ${idea.image_url ? 'has-image' : ''}`}>
                {idea.image_url ? <img src={idea.image_url} alt={idea.title} loading="lazy" /> : <Icon />}
                <span>{idea.category}</span>
              </div>
              <div className="idea-body"><div><h3>{idea.title}</h3><p>{idea.text}</p></div><button className="secondary-button" onClick={() => onUseIdea(idea.generation_type, idea.prompt)}>Использовать идею</button></div>
            </article>
          )})}
        </div>
      ) : <div className="empty-inline"><p>Идеи пока не опубликованы. Администратор может добавить их в веб-админке.</p></div>}
    </section>
  )
}
