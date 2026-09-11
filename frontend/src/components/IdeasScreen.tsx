import { useCallback, useEffect, useMemo, useRef, useState, type SVGProps } from 'react'
import * as api from '../api'
import type { Idea, Project } from '../types'

type IconProps = SVGProps<SVGSVGElement>
const iconProps = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const SearchIcon = (props: IconProps) => <svg {...iconProps} {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const BookmarkIcon = ({ filled, ...props }: IconProps & { filled?: boolean }) => <svg {...iconProps} {...props} fill={filled ? 'currentColor' : 'none'}><path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-3.8L6 21V4.8Z"/></svg>
const ShareIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M12 4v11M8 8l4-4 4 4"/><path d="M5 12v7h14v-7"/></svg>
const LayersIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></svg>
const ArrowIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M5 12h14M14 7l5 5-5 5"/></svg>
const CloseIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="m6 6 12 12M18 6 6 18"/></svg>

const LEGACY_SAVED_KEY = 'auroom.saved_ideas'

function legacySavedIds(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(LEGACY_SAVED_KEY) || '[]')
    return Array.isArray(value)
      ? [...new Set(value.filter((item): item is string => typeof item === 'string' && Boolean(item)))]
      : []
  } catch {
    return []
  }
}

function searchableText(idea: Idea) {
  return [
    idea.title,
    idea.category,
    ...idea.objects.flatMap((object) => [object.title, ...object.answers.flatMap((item) => [item.question, item.answer])]),
  ].join(' ').toLowerCase()
}

function ideaShareUrl(ideaId:string) {
  const url = new URL(window.location.href)
  url.searchParams.delete('billing')
  url.searchParams.delete('admin')
  url.searchParams.set('idea', ideaId)
  return url.toString()
}

function WorkDetails({ idea, onClose }: { idea: Idea; onClose: () => void }) {
  return <div className="idea-details-backdrop" role="dialog" aria-modal="true" aria-label={`Параметры работы ${idea.title}`} onClick={onClose}>
    <section className="idea-details-sheet" onClick={(event) => event.stopPropagation()}>
      <header>
        <div>
          <span>{idea.category}</span>
          <h2>{idea.title}</h2>
        </div>
        <button type="button" aria-label="Закрыть параметры" onClick={onClose}><CloseIcon /></button>
      </header>
      <div className="idea-details-body">
        {idea.objects.length ? idea.objects.map((object) => <section className="idea-details-object" key={object.key}>
          <h3>{object.title}</h3>
          {object.answers.length ? object.answers.map((item, index) => <div className="idea-details-row" key={`${object.key}-${index}`}>
            <span>{item.question}</span>
            <strong>{item.answer}</strong>
          </div>) : <p>Параметры для этого объекта не указаны.</p>}
        </section>) : <p className="idea-details-empty">Параметры этой работы пока недоступны.</p>}
      </div>
    </section>
  </div>
}

function WorkCard({
  idea,
  index,
  total,
  saving,
  starting,
  onSave,
  onShare,
  onStart,
  onDetails,
}: {
  idea: Idea
  index: number
  total: number
  saving: boolean
  starting: boolean
  onSave: () => void
  onShare: () => void
  onStart: () => void
  onDetails: () => void
}) {
  const answerCount = idea.objects.reduce((totalAnswers, object) => totalAnswers + object.answers.length, 0)
  const objectLabels = idea.objects.map((object) => object.title).filter(Boolean)

  return <article id={`idea-${idea.id}`} className="idea-feed-card idea-modern-card" data-idea-id={idea.id}>
    <div className="idea-feed-copy">
      <div className="idea-feed-kicker"><span>РАБОТЫ AUROOM</span><b>{index + 1} / {total}</b></div>
      <h1>{idea.title}</h1>
      <p>{idea.category}</p>
    </div>

    <div className="idea-modern-stage">
      {idea.image_url
        ? <img src={idea.image_url} alt={idea.title} loading={index === 0 ? 'eager' : 'lazy'} />
        : <div className="idea-modern-empty">Работа временно недоступна</div>}
      <div className="idea-modern-shade" aria-hidden />
      <div className="idea-modern-badge"><span />Принятая работа</div>

      <aside className="idea-modern-rail" aria-label="Действия с работой">
        <button type="button" className="idea-modern-rail-button" aria-label="Открыть параметры работы" onClick={onDetails}>
          <LayersIcon />
          <small>{answerCount || idea.selected_objects.length}</small>
        </button>
        <button type="button" disabled={saving} className={`idea-modern-rail-button ${idea.is_saved ? 'active' : ''}`} aria-label={idea.is_saved ? 'Убрать из сохранённых' : 'Сохранить'} onClick={onSave}>
          <BookmarkIcon filled={idea.is_saved} />
        </button>
        <button type="button" className="idea-modern-rail-button" aria-label="Поделиться" onClick={onShare}><ShareIcon /></button>
      </aside>

      <div className="idea-modern-overlay">
        <div className="idea-modern-tags">
          {(objectLabels.length ? objectLabels : idea.selected_objects).slice(0, 3).map((label) => <span key={label}>{label}</span>)}
          {(objectLabels.length ? objectLabels : idea.selected_objects).length > 3 && <span>+{(objectLabels.length ? objectLabels : idea.selected_objects).length - 3}</span>}
        </div>
        <button type="button" className="idea-modern-use" disabled={starting} onClick={onStart}>
          <span>{starting ? 'Создаём проект…' : 'Создать с такими объектами'}</span>
          {!starting && <ArrowIcon />}
        </button>
      </div>
    </div>

    <div className="idea-modern-meta">
      <div><span className="idea-author-avatar">A</span><strong>AuRoom</strong></div>
      <button type="button" onClick={onDetails}>Параметры · {answerCount}</button>
    </div>
  </article>
}

export function IdeasScreen({ onOpenQuestionnaire }: { onOpenQuestionnaire: (project: Project, selectedObjects: string[]) => void }) {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [savingIds, setSavingIds] = useState<Set<string>>(() => new Set())
  const [startingId, setStartingId] = useState<string | null>(null)
  const [detailsIdea, setDetailsIdea] = useState<Idea | null>(null)
  const sharedIdeaId = new URLSearchParams(window.location.search).get('idea')
  const sharedScrollDone = useRef(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [items, shared] = await Promise.all([
          api.listIdeas(),
          sharedIdeaId
            ? api.getIdea(sharedIdeaId).catch((err) => {
                if (err instanceof api.ApiError && err.status === 404) return null
                throw err
              })
            : Promise.resolve(null),
        ])
        if (cancelled) return
        let nextItems = shared && !items.some((item) => item.id === shared.id) ? [shared, ...items] : items

        const legacyIds = legacySavedIds()
        if (legacyIds.length) {
          const migrated = await Promise.allSettled(legacyIds.map((ideaId) => api.saveIdea(ideaId)))
          if (cancelled) return
          const savedIds = new Set(
            migrated.flatMap((result, index) => result.status === 'fulfilled' ? [legacyIds[index]] : []),
          )
          nextItems = nextItems.map((item) => savedIds.has(item.id) ? { ...item, is_saved:true } : item)
          const remaining = legacyIds.filter((ideaId) => !savedIds.has(ideaId))
          if (remaining.length) localStorage.setItem(LEGACY_SAVED_KEY, JSON.stringify(remaining))
          else localStorage.removeItem(LEGACY_SAVED_KEY)
        }

        setIdeas(nextItems)
        if (sharedIdeaId && !shared) setError('Эта работа больше не опубликована в Идеях.')
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось загрузить работы')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [sharedIdeaId])

  useEffect(() => {
    if (loading || !sharedIdeaId || sharedScrollDone.current) return
    const target = document.getElementById(`idea-${sharedIdeaId}`)
    if (!target) return
    target.scrollIntoView({ block:'start' })
    sharedScrollDone.current = true
  }, [loading, sharedIdeaId])

  useEffect(() => {
    if (!detailsIdea) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setDetailsIdea(null) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [detailsIdea])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return ideas
    return ideas.filter((idea) => searchableText(idea).includes(normalized))
  }, [ideas, query])

  const toggleSaved = useCallback(async (idea: Idea) => {
    if (savingIds.has(idea.id)) return
    setSavingIds((current) => new Set(current).add(idea.id))
    setError(null)
    try {
      const result = idea.is_saved ? await api.unsaveIdea(idea.id) : await api.saveIdea(idea.id)
      setIdeas((current) => current.map((item) => item.id === idea.id ? { ...item, is_saved:result.is_saved } : item))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось изменить сохранённые работы')
    } finally {
      setSavingIds((current) => {
        const next = new Set(current)
        next.delete(idea.id)
        return next
      })
    }
  }, [savingIds])

  const shareIdea = useCallback(async (idea: Idea) => {
    const url = ideaShareUrl(idea.id)
    const shareData = { title: idea.title, text: `${idea.title} · ${idea.category}`, url }
    try {
      if (navigator.share) await navigator.share(shareData)
      else if (navigator.clipboard) await navigator.clipboard.writeText(`${shareData.text}\n${url}`)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError('Не удалось поделиться работой.')
    }
  }, [])

  async function startFromIdea(idea: Idea) {
    if (startingId) return
    setStartingId(idea.id)
    setError(null)
    try {
      const project = await api.startProjectFromIdea(idea.id)
      onOpenQuestionnaire(project, idea.selected_objects)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать проект по этой работе')
    } finally {
      setStartingId(null)
    }
  }

  return <section className="ideas-page-concept ideas-modern-page">
    <header className="ideas-concept-topbar">
      <span className="wordmark"><span className="wordmark-dot" />AuRoom</span>
      <div className={`ideas-search ${searchOpen ? 'open' : ''}`}>
        {searchOpen && <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск работ" aria-label="Поиск работ" />}
        <button type="button" aria-label={searchOpen ? 'Закрыть поиск' : 'Открыть поиск'} onClick={() => { setSearchOpen((value) => !value); if (searchOpen) setQuery('') }}><SearchIcon /></button>
      </div>
    </header>

    {error && <div className="ideas-floating-error banner-error">{error}<button type="button" onClick={() => setError(null)}>Закрыть</button></div>}
    {loading ? <div className="ideas-feed-status"><div className="idea-feed-skeleton" /></div> : filtered.length ? (
      <div className="ideas-feed">
        {filtered.map((idea, index) => <div className="idea-feed-snap" key={idea.id}>
          <WorkCard
            idea={idea}
            index={index}
            total={filtered.length}
            saving={savingIds.has(idea.id)}
            starting={startingId === idea.id}
            onSave={() => void toggleSaved(idea)}
            onShare={() => void shareIdea(idea)}
            onStart={() => void startFromIdea(idea)}
            onDetails={() => setDetailsIdea(idea)}
          />
        </div>)}
      </div>
    ) : <div className="ideas-feed-status"><div className="empty-inline"><p>{query ? 'По этому запросу ничего не найдено.' : 'Пока нет опубликованных работ.'}</p></div></div>}

    {detailsIdea && <WorkDetails idea={detailsIdea} onClose={() => setDetailsIdea(null)} />}
  </section>
}
