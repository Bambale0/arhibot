import { useEffect, useMemo, useState } from 'react'
import type { ArchitecturePackage, IdeaMediaKind } from '../types'

type LegacyIdea = {
  id: string
  title: string
  category: string
  image_url: string | null
  media: Array<{ asset_id: string; kind: IdeaMediaKind; label: string; url: string }>
  architecture: ArchitecturePackage | null
}

export type FeedMediaItem = {
  id: string
  kind: IdeaMediaKind
  label: string
  url?: string
  derived?: 'plan'
  levelIndex?: number
}

export function ideaFeedMedia(idea: LegacyIdea): FeedMediaItem[] {
  const items: FeedMediaItem[] = []
  if (idea.image_url) items.push({ id: `hero-${idea.id}`, kind: 'photo', label: 'Визуализация', url: idea.image_url })
  for (const item of idea.media) {
    if (items.some((existing) => existing.url === item.url)) continue
    items.push({ id: item.asset_id, kind: item.kind, label: item.label, url: item.url })
  }
  idea.architecture?.geometry.levels.forEach((level, levelIndex) => {
    items.push({
      id: `plan-${idea.id}-${level.id}`,
      kind: 'scheme',
      label: `План · ${level.label}`,
      derived: 'plan',
      levelIndex,
    })
  })
  return items
}

function planGeometry(architecture: ArchitecturePackage | null, levelIndex = 0) {
  const level = architecture?.geometry.levels[levelIndex]
  if (!level) return null
  const allPoints = [
    ...level.footprint.points,
    ...level.rooms.flatMap((room) => room.polygon.points),
  ]
  if (!allPoints.length) return null
  const xs = allPoints.map((point) => point.x)
  const ys = allPoints.map((point) => point.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const width = Math.max(maxX - minX, 1)
  const height = Math.max(maxY - minY, 1)
  const pad = Math.max(width, height) * 0.08
  return { level, viewBox: `${minX - pad} ${minY - pad} ${width + pad * 2} ${height + pad * 2}` }
}

export function ArchitecturePlanArt({ architecture, levelIndex = 0, compact = false }: { architecture: ArchitecturePackage | null; levelIndex?: number; compact?: boolean }) {
  const geometry = useMemo(() => planGeometry(architecture, levelIndex), [architecture, levelIndex])
  if (!geometry) return <div className="idea-plan-empty">Схема недоступна</div>
  const { level, viewBox } = geometry
  const points = (list: { x: number; y: number }[]) => list.map((point) => `${point.x},${point.y}`).join(' ')
  return (
    <svg className={`idea-plan-art ${compact ? 'compact' : ''}`} viewBox={viewBox} role="img" aria-label={`План: ${level.label}`}>
      <rect x="-10000" y="-10000" width="20000" height="20000" fill="#f7f4ee" />
      <polygon points={points(level.footprint.points)} fill="#ebe5da" stroke="#14232d" strokeWidth="0.12" vectorEffect="non-scaling-stroke" />
      {level.rooms.map((room, index) => (
        <g key={room.id}>
          <polygon
            points={points(room.polygon.points)}
            fill={index % 2 ? '#f7f2e9' : '#efe7db'}
            stroke="#586068"
            strokeWidth="0.07"
            vectorEffect="non-scaling-stroke"
          />
          {!compact && room.polygon.points[0] && <text x={room.polygon.points[0].x + 0.18} y={room.polygon.points[0].y + 0.32} fontSize="0.34" fill="#48515a">{room.name}</text>}
        </g>
      ))}
    </svg>
  )
}

function MediaArtwork({ item, architecture, compact = false }: { item: FeedMediaItem; architecture: ArchitecturePackage | null; compact?: boolean }) {
  if (item.derived === 'plan') return <ArchitecturePlanArt architecture={architecture} levelIndex={item.levelIndex} compact={compact} />
  if (item.url) return <img src={item.url} alt={item.label} loading="lazy" />
  return <div className="idea-plan-empty">Материал недоступен</div>
}

export function IdeaMediaStrip({ idea, onOpen }: { idea: LegacyIdea; onOpen: (itemId?: string) => void }) {
  const items = useMemo(() => ideaFeedMedia(idea), [idea])
  if (!items.length) return null
  return (
    <section className="idea-media-strip" aria-label="Референсы и схемы">
      <div className="idea-media-strip-head">
        <strong>Референсы и схемы</strong>
        <button type="button" onClick={() => onOpen()}>Открыть карусель <span aria-hidden>→</span></button>
      </div>
      <div className="idea-media-strip-track">
        {items.slice(0, 7).map((item, index) => (
          <button type="button" className={`idea-media-tile ${index === 0 ? 'selected' : ''}`} key={item.id} onClick={() => onOpen(item.id)}>
            <span className="idea-media-thumb"><MediaArtwork item={item} architecture={idea.architecture} compact /></span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

export function IdeaMediaModal({ idea, open, initialItemId, filter, onClose }: { idea: LegacyIdea; open: boolean; initialItemId?: string | null; filter?: IdeaMediaKind | null; onClose: () => void }) {
  const allItems = useMemo(() => ideaFeedMedia(idea), [idea])
  const items = useMemo(() => filter ? allItems.filter((item) => item.kind === filter) : allItems, [allItems, filter])
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (!open) return
    const requested = initialItemId ? items.findIndex((item) => item.id === initialItemId) : -1
    setIndex(requested >= 0 ? requested : 0)
  }, [initialItemId, items, open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight') setIndex((value) => (value + 1) % Math.max(items.length, 1))
      if (event.key === 'ArrowLeft') setIndex((value) => (value - 1 + Math.max(items.length, 1)) % Math.max(items.length, 1))
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [items.length, onClose, open])

  if (!open) return null
  const current = items[index]
  return (
    <div className="idea-media-modal" role="dialog" aria-modal="true" aria-label="Материалы идеи" onClick={onClose}>
      <div className="idea-media-dialog" onClick={(event) => event.stopPropagation()}>
        <header>
          <div><span>{idea.category}</span><strong>{idea.title}</strong></div>
          <button type="button" aria-label="Закрыть" onClick={onClose}>×</button>
        </header>
        {current ? (
          <>
            <div className="idea-media-stage"><MediaArtwork item={current} architecture={idea.architecture} /></div>
            <div className="idea-media-stage-caption"><strong>{current.label}</strong><span>{index + 1} / {items.length}</span></div>
            {items.length > 1 && <div className="idea-media-modal-nav">
              <button type="button" aria-label="Предыдущий" onClick={() => setIndex((index - 1 + items.length) % items.length)}>←</button>
              <div>{items.map((item, itemIndex) => <button type="button" key={item.id} className={itemIndex === index ? 'active' : ''} onClick={() => setIndex(itemIndex)}><span className="idea-media-thumb"><MediaArtwork item={item} architecture={idea.architecture} compact /></span></button>)}</div>
              <button type="button" aria-label="Следующий" onClick={() => setIndex((index + 1) % items.length)}>→</button>
            </div>}
          </>
        ) : <div className="idea-media-no-items">Материалы этой категории пока не добавлены.</div>}
      </div>
    </div>
  )
}
