import { useCallback, useEffect, useMemo, useState, type SVGProps } from 'react'
import * as api from '../api'
import type { Idea, Project } from '../types'

type IconProps = SVGProps<SVGSVGElement>
const iconProps = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const SearchIcon = (props: IconProps) => <svg {...iconProps} {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const BookmarkIcon = ({ filled, ...props }: IconProps & { filled?: boolean }) => <svg {...iconProps} {...props} fill={filled ? 'currentColor' : 'none'}><path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-3.8L6 21V4.8Z"/></svg>
const ShareIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M12 4v11M8 8l4-4 4 4"/><path d="M5 12v7h14v-7"/></svg>

const SAVED_KEY = 'auroom.saved_ideas'
function readSaved() {
  try {
    const value = JSON.parse(localStorage.getItem(SAVED_KEY) || '[]')
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
  } catch {
    return new Set<string>()
  }
}

function searchableText(idea: Idea) {
  return [
    idea.title,
    idea.category,
    ...idea.objects.flatMap((object) => [object.title, ...object.answers.flatMap((item) => [item.question, item.answer])]),
  ].join(' ').toLowerCase()
}

function WorkCard({
  idea,
  index,
  total,
  saved,
  starting,
  onSave,
  onShare,
  onStart,
}: {
  idea: Idea
  index: number
  total: number
  saved: boolean
  starting: boolean
  onSave: () => void
  onShare: () => void
  onStart: () => void
}) {
  const summary = idea.objects.flatMap((object) => object.answers.map((item) => ({ ...item, objectTitle: object.title })))
  return <article className="idea-feed-card idea-work-card">
    <div className="idea-feed-copy">
      <div className="idea-feed-kicker"><span>РАБОТЫ AUROOM</span><b>{index + 1} / {total}</b></div>
      <h1>{idea.title}</h1>
      <p>{idea.category}</p>
    </div>

    <div className="idea-work-stage">
      {idea.image_url ? <img src={idea.image_url} alt={idea.title} loading={index === 0 ? 'eager' : 'lazy'} /> : <div className="idea-work-empty">Работа временно недоступна</div>}
      <div className="idea-work-actions">
        <button type="button" className={saved ? 'active' : ''} aria-label={saved ? 'Убрать из сохранённых' : 'Сохранить'} onClick={onSave}><BookmarkIcon filled={saved}/></button>
        <button type="button" aria-label="Поделиться" onClick={onShare}><ShareIcon /></button>
      </div>
    </div>

    <div className="idea-feed-meta idea-work-meta">
      <div className="idea-author-row">
        <span className="idea-author-avatar">A</span>
        <strong>AuRoom</strong>
        <button type="button" className="idea-use-button" disabled={starting} onClick={onStart}>{starting ? 'Создаём проект…' : 'Создать с такими объектами'}</button>
      </div>
      {summary.length > 0 && <details className="idea-work-summary">
        <summary>Параметры работы · {summary.length}</summary>
        <div>
          {summary.map((item, itemIndex) => <section key={`${item.objectTitle}-${item.question}-${itemIndex}`}>
            <strong>{item.question}</strong>
            <span>{item.answer}</span>
          </section>)}
        </div>
      </details>}
    </div>
  </article>
}

export function IdeasScreen({ onOpenQuestionnaire }: { onOpenQuestionnaire: (project: Project, selectedObjects: string[]) => void }) {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [saved, setSaved] = useState<Set<string>>(new Set())
  const [startingId, setStartingId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [items, savedIds] = await Promise.all([api.listIdeas(), api.listSavedIdeas()])
        if (cancelled) return
        setIdeas(items)
        const availableIds = new Set(items.map((item) => item.id))
        const legacy = readSaved()
        const merged = new Set(savedIds)
        const legacyToSync = [...legacy].filter((id) => availableIds.has(id) && !merged.has(id))
        legacyToSync.forEach((id) => merged.add(id))
        setSaved(merged)
        if (legacyToSync.length) {
          await Promise.allSettled(legacyToSync.map((id) => api.saveIdea(id)))
        }
        localStorage.removeItem(SAVED_KEY)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось загрузить работы')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const deepLinkIdeaId = new URLSearchParams(window.location.search).get('idea')
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    const visible = normalized
      ? ideas.filter((idea) => searchableText(idea).includes(normalized))
      : [...ideas]
    if (!normalized && deepLinkIdeaId) {
      visible.sort((left, right) => Number(right.id === deepLinkIdeaId) - Number(left.id === deepLinkIdeaId))
    }
    return visible
  }, [ideas, query, deepLinkIdeaId])

  const toggleSaved = useCallback(async (ideaId: string) => {
    const wasSaved = saved.has(ideaId)
    setSaved((current) => {
      const next = new Set(current)
      if (wasSaved) next.delete(ideaId); else next.add(ideaId)
      return next
    })
    try {
      if (wasSaved) await api.unsaveIdea(ideaId)
      else await api.saveIdea(ideaId)
    } catch (err) {
      setSaved((current) => {
        const next = new Set(current)
        if (wasSaved) next.add(ideaId); else next.delete(ideaId)
        return next
      })
      setError(err instanceof Error ? err.message : 'Не удалось обновить сохранённые работы')
    }
  }, [saved])

  const shareIdea = useCallback(async (idea: Idea) => {
    const deepLink = new URL(window.location.href)
    deepLink.search = ''
    deepLink.searchParams.set('idea', idea.id)
    const shareData = { title: idea.title, text: `${idea.title} · ${idea.category}`, url: deepLink.toString() }
    try {
      if (navigator.share) await navigator.share(shareData)
      else if (navigator.clipboard) await navigator.clipboard.writeText(`${shareData.text}\n${shareData.url}`)
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

  return <section className="ideas-page-concept">
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
            saved={saved.has(idea.id)}
            starting={startingId === idea.id}
            onSave={() => { void toggleSaved(idea.id) }}
            onShare={() => void shareIdea(idea)}
            onStart={() => void startFromIdea(idea)}
          />
        </div>)}
      </div>
    ) : <div className="ideas-feed-status"><div className="empty-inline"><p>{query ? 'По этому запросу ничего не найдено.' : 'Пока нет опубликованных работ.'}</p></div></div>}
  </section>
}
