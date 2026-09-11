import { useCallback, useEffect, useMemo, useState, type SVGProps } from 'react'
import * as api from '../api'
import type { Idea, Project } from '../types'

type IconProps = SVGProps<SVGSVGElement>
const iconProps = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const SearchIcon = (props: IconProps) => <svg {...iconProps} {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const BookmarkIcon = ({ filled, ...props }: IconProps & { filled?: boolean }) => <svg {...iconProps} {...props} fill={filled ? 'currentColor' : 'none'}><path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-3.8L6 21V4.8Z"/></svg>
const ShareIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M12 4v11M8 8l4-4 4 4"/><path d="M5 12v7h14v-7"/></svg>

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

function WorkCard({
  idea,
  index,
  total,
  saving,
  starting,
  onSave,
  onShare,
  onStart,
}: {
  idea: Idea
  index: number
  total: number
  saving: boolean
  starting: boolean
  onSave: () => void
  onShare: () => void
  onStart: () => void
}) {
  const summary = idea.objects.flatMap((object) => object.answers.map((item) => ({ ...item, objectTitle: object.title })))
  return <article id={`idea-${idea.id}`} className="idea-feed-card idea-work-card" data-idea-id={idea.id}>
    <div className="idea-feed-copy">
      <div className="idea-feed-kicker"><span>РАБОТЫ AUROOM</span><b>{index + 1} / {total}</b></div>
      <h1>{idea.title}</h1>
      <p>{idea.category}</p>
    </div>

    <div className="idea-work-stage">
      {idea.image_url ? <img src={idea.image_url} alt={idea.title} loading={index === 0 ? 'eager' : 'lazy'} /> : <div className="idea-work-empty">Работа временно недоступна</div>}
      <div className="idea-work-actions">
        <button type="button" disabled={saving} className={idea.is_saved ? 'active' : ''} aria-label={idea.is_saved ? 'Убрать из сохранённых' : 'Сохранить'} onClick={onSave}><BookmarkIcon filled={idea.is_saved}/></button>
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
  const [savingIds, setSavingIds] = useState<Set<string>>(() => new Set())
  const [startingId, setStartingId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.listIdeas()
      .then((items) => { if (!cancelled) setIdeas(items) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : 'Не удалось загрузить работы') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (loading || !ideas.length) return
    const ideaId = new URLSearchParams(window.location.search).get('idea')
    if (!ideaId) return
    const target = document.getElementById(`idea-${ideaId}`)
    if (target) target.scrollIntoView({ block:'start' })
    else setError('Эта работа больше не опубликована в Идеях.')
  }, [loading, ideas])

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
            saving={savingIds.has(idea.id)}
            starting={startingId === idea.id}
            onSave={() => void toggleSaved(idea)}
            onShare={() => void shareIdea(idea)}
            onStart={() => void startFromIdea(idea)}
          />
        </div>)}
      </div>
    ) : <div className="ideas-feed-status"><div className="empty-inline"><p>{query ? 'По этому запросу ничего не найдено.' : 'Пока нет опубликованных работ.'}</p></div></div>}
  </section>
}
