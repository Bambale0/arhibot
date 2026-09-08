import { useCallback, useEffect, useMemo, useRef, useState, type SVGProps } from 'react'
import * as api from '../api'
import type { GenerationMode, Idea, IdeaMediaKind } from '../types'
import { Idea3DViewer } from './Idea3DViewer'
import { ideaFeedMedia, IdeaMediaModal, IdeaMediaStrip } from './IdeaMediaViewer'

type IconProps = SVGProps<SVGSVGElement>
const iconProps = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const SearchIcon = (props: IconProps) => <svg {...iconProps} {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const CubeIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/></svg>
const BookmarkIcon = ({ filled, ...props }: IconProps & { filled?: boolean }) => <svg {...iconProps} {...props} fill={filled ? 'currentColor' : 'none'}><path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-3.8L6 21V4.8Z"/></svg>
const ShareIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M12 4v11M8 8l4-4 4 4"/><path d="M5 12v7h14v-7"/></svg>
const PhotoIcon = (props: IconProps) => <svg {...iconProps} {...props}><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 15-5-5L5 20"/></svg>
const RefIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M5 3h11l3 3v15H5z"/><path d="M14 3v5h5M8 12h8M8 16h6"/></svg>
const PlanIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M4 4h16v16H4zM9 4v7h11M4 15h8v5M12 11v9"/></svg>
const HandIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="M8.8 11V6.8a1.2 1.2 0 0 1 2.4 0V10M11.2 10V5.8a1.2 1.2 0 0 1 2.4 0V10M13.6 10V7a1.2 1.2 0 0 1 2.4 0v4M16 11V9.4a1.2 1.2 0 0 1 2.4 0v4.1c0 4.4-2.3 7.5-6.5 7.5-2.3 0-3.8-.8-5-2.4L4 14.8a1.3 1.3 0 0 1 2-1.6L8.8 16"/></svg>
const ChevronIcon = (props: IconProps) => <svg {...iconProps} {...props}><path d="m8 10 4 4 4-4"/></svg>

const mediaLabel: Record<IdeaMediaKind, string> = { photo: 'Фото', reference: 'Референсы', scheme: 'Схемы' }
const mediaIcon: Record<IdeaMediaKind, typeof PhotoIcon> = { photo: PhotoIcon, reference: RefIcon, scheme: PlanIcon }

const SAVED_KEY = 'auroom.saved_ideas'
function readSaved() {
  try {
    const value = JSON.parse(localStorage.getItem(SAVED_KEY) || '[]')
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
  } catch {
    return new Set<string>()
  }
}

function tagsForIdea(idea: Idea) {
  const raw = [idea.category, idea.generation_type === 'interior' ? 'интерьер' : 'архитектура']
  return raw.map((value) => `#${value.toLowerCase().replace(/[^а-яёa-z0-9]+/gi, '')}`).filter((value) => value.length > 1)
}

function IdeaRail({ idea, saved, onMedia, onSave, onShare }: { idea: Idea; saved: boolean; onMedia: (kind: IdeaMediaKind) => void; onSave: () => void; onShare: () => void }) {
  const items = ideaFeedMedia(idea)
  return <aside className="idea-action-rail" aria-label="Материалы и действия">
    {(['photo', 'reference', 'scheme'] as IdeaMediaKind[]).map((kind) => {
      const grouped = items.filter((item) => item.kind === kind)
      const Icon = mediaIcon[kind]
      const preview = grouped[0]
      return <button type="button" className="idea-rail-media" key={kind} disabled={!grouped.length} onClick={() => onMedia(kind)}>
        <span className="idea-rail-thumb">
          {preview?.url ? <img src={preview.url} alt="" loading="lazy" /> : <Icon />}
          {grouped.length > 0 && <b>{grouped.length}</b>}
        </span>
        <span>{mediaLabel[kind]}</span>
      </button>
    })}
    <button type="button" className={`idea-rail-icon ${saved ? 'active' : ''}`} aria-label={saved ? 'Убрать из сохранённых' : 'Сохранить'} onClick={onSave}><BookmarkIcon filled={saved}/></button>
    <button type="button" className="idea-rail-icon" aria-label="Поделиться" onClick={onShare}><ShareIcon /></button>
  </aside>
}

function IdeaFeedCard({ idea, index, total, active, saved, onUseIdea, onSave, onShare, onOpenMedia }: {
  idea: Idea
  index: number
  total: number
  active: boolean
  saved: boolean
  onUseIdea: (mode: GenerationMode, prompt: string) => void
  onSave: () => void
  onShare: () => void
  onOpenMedia: (idea: Idea, filter?: IdeaMediaKind | null, itemId?: string | null) => void
}) {
  const textureUrls = idea.media.filter((item) => item.kind !== 'scheme').map((item) => item.url)
  return <article className="idea-feed-card" data-active={active ? 'true' : 'false'}>
    <div className="idea-feed-copy">
      <div className="idea-feed-kicker"><span>ИДЕЯ ДНЯ</span><b>{index + 1} / {total}</b></div>
      <h1>{idea.title}</h1>
      <p>{idea.text}</p>
    </div>

    <div className="idea-stage-shell">
      <button type="button" className="idea-3d-pill" aria-label="Интерактивный 3D-обзор"><CubeIcon /><span>3D-обзор</span><ChevronIcon /></button>
      <Idea3DViewer active={active} imageUrl={idea.image_url} textureUrls={textureUrls} architecture={idea.architecture} title={idea.title} />
      <IdeaRail
        idea={idea}
        saved={saved}
        onMedia={(kind) => onOpenMedia(idea, kind)}
        onSave={onSave}
        onShare={onShare}
      />
      <div className="idea-orbit-hint" aria-hidden>
        <span>←</span><HandIcon/><span>→</span>
        <b>360°</b>
      </div>
      <div className="idea-rotate-caption">Поворачивайте, чтобы рассмотреть со всех сторон</div>
    </div>

    <IdeaMediaStrip idea={idea} onOpen={(itemId) => onOpenMedia(idea, null, itemId || null)} />

    <div className="idea-feed-meta">
      <div className="idea-author-row">
        <span className="idea-author-avatar">A</span>
        <strong>AuRoom AI</strong>
        <button type="button" className="idea-use-button" onClick={() => onUseIdea(idea.generation_type, idea.prompt)}>Использовать идею</button>
        <span className="idea-meta-more" aria-hidden>•••</span>
      </div>
      <p>{idea.text}</p>
      <div className="idea-tags">{tagsForIdea(idea).map((tag) => <span key={tag}>{tag}</span>)}</div>
    </div>
  </article>
}

export function IdeasScreen({ onUseIdea }: { onUseIdea: (mode: GenerationMode, prompt: string) => void }) {
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [saved, setSaved] = useState<Set<string>>(() => readSaved())
  const [modalIdea, setModalIdea] = useState<Idea | null>(null)
  const [modalFilter, setModalFilter] = useState<IdeaMediaKind | null>(null)
  const [modalItemId, setModalItemId] = useState<string | null>(null)
  const feedRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    api.listIdeas()
      .then((items) => { setIdeas(items); setActiveId(items[0]?.id || null) })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить идеи'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return ideas
    return ideas.filter((idea) => [idea.title, idea.category, idea.text].some((value) => value.toLowerCase().includes(normalized)))
  }, [ideas, query])

  useEffect(() => {
    const root = feedRef.current
    if (!root || !filtered.length) return
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (visible?.target instanceof HTMLElement) setActiveId(visible.target.dataset.ideaId || null)
    }, { root, threshold: [0.45, 0.65, 0.8] })
    root.querySelectorAll<HTMLElement>('[data-idea-id]').forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [filtered])

  useEffect(() => {
    if (filtered.length && !filtered.some((idea) => idea.id === activeId)) setActiveId(filtered[0].id)
  }, [activeId, filtered])

  const toggleSaved = useCallback((ideaId: string) => {
    setSaved((current) => {
      const next = new Set(current)
      if (next.has(ideaId)) next.delete(ideaId); else next.add(ideaId)
      localStorage.setItem(SAVED_KEY, JSON.stringify([...next]))
      return next
    })
  }, [])

  const shareIdea = useCallback(async (idea: Idea) => {
    const shareData = { title: idea.title, text: idea.text, url: window.location.href }
    try {
      if (navigator.share) await navigator.share(shareData)
      else if (navigator.clipboard) await navigator.clipboard.writeText(`${idea.title}\n${idea.text}\n${window.location.href}`)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
    }
  }, [])

  const openMedia = useCallback((idea: Idea, filter: IdeaMediaKind | null = null, itemId: string | null = null) => {
    setModalIdea(idea); setModalFilter(filter); setModalItemId(itemId)
  }, [])

  return <section className="ideas-page-concept">
    <header className="ideas-concept-topbar">
      <span className="wordmark"><span className="wordmark-dot" />AuRoom</span>
      <div className={`ideas-search ${searchOpen ? 'open' : ''}`}>
        {searchOpen && <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск идей" aria-label="Поиск идей" />}
        <button type="button" aria-label={searchOpen ? 'Закрыть поиск' : 'Открыть поиск'} onClick={() => { setSearchOpen((value) => !value); if (searchOpen) setQuery('') }}><SearchIcon /></button>
      </div>
    </header>

    {error && <div className="ideas-feed-status"><div className="banner-error">{error}</div></div>}
    {loading ? <div className="ideas-feed-status"><div className="idea-feed-skeleton" /></div> : filtered.length ? (
      <div className="ideas-feed" ref={feedRef}>
        {filtered.map((idea, index) => <div className="idea-feed-snap" key={idea.id} data-idea-id={idea.id}>
          <IdeaFeedCard
            idea={idea}
            index={index}
            total={filtered.length}
            active={activeId === idea.id}
            saved={saved.has(idea.id)}
            onUseIdea={onUseIdea}
            onSave={() => toggleSaved(idea.id)}
            onShare={() => void shareIdea(idea)}
            onOpenMedia={openMedia}
          />
        </div>)}
      </div>
    ) : <div className="ideas-feed-status"><div className="empty-inline"><p>{query ? 'По этому запросу ничего не найдено.' : 'Идеи пока не опубликованы. Администратор может добавить их в веб-админке.'}</p></div></div>}

    {modalIdea && <IdeaMediaModal idea={modalIdea} open initialItemId={modalItemId} filter={modalFilter} onClose={() => setModalIdea(null)} />}
  </section>
}
