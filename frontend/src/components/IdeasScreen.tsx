import type { GenerationMode } from '../types'
import { HomeIcon, PlanIcon, RoomIcon, SiteIcon, SparkIcon } from './Icons'

const ideas: { title: string; category: string; text: string; mode: GenerationMode; icon: typeof HomeIcon }[] = [
  { title: 'Семейный дом 140 м²', category: 'ПЛАНИРОВКА', text: '3 спальни, кухня-гостиная, мастер-блок и компактная постирочная.', mode: 'floor_plan', icon: PlanIcon },
  { title: 'Тёплый минимализм', category: 'ФАСАД', text: 'Штукатурка, дерево, графитовые рамы и мягкая архитектурная подсветка.', mode: 'facade', icon: HomeIcon },
  { title: 'Участок 12 соток', category: 'МАСТЕР-ПЛАН', text: 'Дом, баня, парковка, терраса и приватная зона сада.', mode: 'master_plan', icon: SiteIcon },
  { title: 'Гостиная с кухней', category: 'ИНТЕРЬЕР', text: 'Натуральный камень, дуб, спокойный свет и чистая геометрия.', mode: 'interior', icon: RoomIcon },
  { title: 'Дом с плоской кровлей', category: 'ФАСАД', text: 'Контраст светлого объёма и тёмного цоколя с крупным остеклением.', mode: 'facade', icon: HomeIcon },
  { title: 'Спальня в спокойной палитре', category: 'ИНТЕРЬЕР', text: 'Мягкие фактуры, скрытый свет и акцентное изголовье.', mode: 'interior', icon: SparkIcon },
]

export function IdeasScreen({ onUseIdea }: { onUseIdea: (mode: GenerationMode) => void }) {
  return (
    <section className="page-content ideas-page">
      <div className="page-heading-row"><div><span className="eyebrow">AUROOM COLLECTION</span><h1>Идеи</h1><p>Готовые направления, которые можно взять за основу нового проекта.</p></div></div>
      <div className="ideas-grid">
        {ideas.map((idea, index) => { const Icon = idea.icon; return (
          <article className="idea-card" key={`${idea.title}-${index}`}>
            <div className={`idea-visual idea-tone-${(index % 4) + 1}`}><Icon /><span>{idea.category}</span></div>
            <div className="idea-body"><div><h3>{idea.title}</h3><p>{idea.text}</p></div><button className="secondary-button" onClick={() => onUseIdea(idea.mode)}>Использовать идею</button></div>
          </article>
        )})}
      </div>
    </section>
  )
}
