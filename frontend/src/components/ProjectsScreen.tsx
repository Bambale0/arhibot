import { useEffect, useMemo, useState } from 'react'
import * as api from '../api'
import type { Idea, Project } from '../types'
import { ArrowIcon, HomeIcon, ImageIcon, PlusIcon, SparkIcon } from './Icons'

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(new Date(value))
}

function projectDetail(project: Project) {
  const floors = project.context.floors
  const parts = [
    project.context.house_area_m2 ? `${project.context.house_area_m2} м²` : null,
    floors ? `${floors} ${floors === 1 ? 'этаж' : floors < 5 ? 'этажа' : 'этажей'}` : null,
    project.context.architecture_style || null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : `Обновлён ${formatDate(project.updated_at)}`
}

function projectCountLabel(count: number, hasMore: boolean) {
  if (hasMore) return `${count}+ проектов`
  const mod100 = count % 100
  const mod10 = count % 10
  const word = mod100 >= 11 && mod100 <= 14 ? 'проектов' : mod10 === 1 ? 'проект' : mod10 >= 2 && mod10 <= 4 ? 'проекта' : 'проектов'
  return `${count} ${word}`
}

function InspirationCard({ idea, onOpen }: { idea: Idea; onOpen: () => void }) {
  const imageUrl = idea.preview_url || idea.image_url
  return (
    <button type="button" className="home-inspiration-card" onClick={onOpen} aria-label={`Открыть ленту: ${idea.title}`}>
      {imageUrl ? (
        <img src={imageUrl} alt={idea.title} loading="lazy" decoding="async" />
      ) : (
        <span className="home-inspiration-placeholder"><HomeIcon /></span>
      )}
      <span className="home-inspiration-caption"><strong>{idea.title}</strong><small>{idea.category}</small></span>
    </button>
  )
}

export function ProjectsScreen({
  onOpenProject,
  onCreate,
  onOpenIdeas,
}: {
  onOpenProject: (project: Project) => void
  onCreate: () => void
  onOpenIdeas: () => void
}) {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsHasMore, setProjectsHasMore] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showProjects, setShowProjects] = useState(false)
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [ideasLoading, setIdeasLoading] = useState(true)
  const [ideasError, setIdeasError] = useState<string | null>(null)

  async function loadProjects() {
    setLoading(true)
    setError(null)
    setPreviewUrl(null)
    try {
      const page = await api.listProjects(null, 50, 'updated')
      setProjects(page.items)
      setProjectsHasMore(Boolean(page.has_more))

      const sceneAssetId = page.items[0]?.context.design_session?.scene_asset_id
      if (sceneAssetId) {
        try {
          const asset = await api.getAsset(sceneAssetId)
          setPreviewUrl(asset.preview_url || null)
        } catch {
          // The project remains usable even when an old preview asset was deleted.
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить проекты')
    } finally {
      setLoading(false)
    }
  }

  async function loadIdeas() {
    setIdeasLoading(true)
    setIdeasError(null)
    try {
      setIdeas((await api.listIdeas(3, 0)).slice(0, 3))
    } catch (err) {
      setIdeasError(err instanceof Error ? err.message : 'Не удалось загрузить примеры')
    } finally {
      setIdeasLoading(false)
    }
  }

  useEffect(() => {
    void loadProjects()
    void loadIdeas()
  }, [])

  const latestProject = projects[0] || null
  const countLabel = useMemo(
    () => projectCountLabel(projects.length, projectsHasMore),
    [projects.length, projectsHasMore],
  )

  return (
    <section className="page-content projects-page home-dashboard-page">
      <header className="home-dashboard-heading">
        <span className="eyebrow">ВАША СТУДИЯ</span>
        <h1>{latestProject ? 'Ваш последний проект' : 'Начните первый проект'}</h1>
      </header>

      {error && <div className="banner-error">Не удалось загрузить проекты<button onClick={() => void loadProjects()}>Повторить</button></div>}

      {loading ? (
        <div className="home-last-card home-last-card-skeleton" aria-label="Загрузка последнего проекта">
          <div className="home-last-preview skeleton-card" />
          <div className="home-last-copy"><span className="home-skeleton-line wide" /><span className="home-skeleton-line" /></div>
        </div>
      ) : latestProject ? (
        <article className="home-last-card">
          <div className="home-last-preview">
            {previewUrl ? (
              <img src={previewUrl} alt={`Последний кадр проекта «${latestProject.name}»`} decoding="async" />
            ) : (
              <span className="home-last-placeholder"><HomeIcon /></span>
            )}
            <span className="home-last-date">{formatDate(latestProject.updated_at)}</span>
          </div>
          <div className="home-last-copy">
            <div>
              <span className="home-card-kicker">Последняя работа</span>
              <h2>{latestProject.name}</h2>
              <p>{projectDetail(latestProject)}</p>
            </div>
            <button type="button" className="primary-button" onClick={() => onOpenProject(latestProject)}>
              Продолжить <ArrowIcon />
            </button>
          </div>
        </article>
      ) : (
        <div className="home-first-project">
          <span className="home-last-placeholder"><HomeIcon /></span>
          <div><h2>Проектов пока нет</h2><p>Выберите объекты, ответьте на вопросы и получите первую визуализацию.</p></div>
          <button type="button" className="primary-button" onClick={onCreate}><PlusIcon /> Создать проект</button>
        </div>
      )}

      <section className="home-dashboard-section" aria-labelledby="home-actions-title">
        <div className="home-section-heading">
          <div><h2 id="home-actions-title">Что хотите сделать?</h2><p>Три быстрых пути без лишних экранов.</p></div>
        </div>
        <div className="home-action-grid">
          <button type="button" className="home-action-card" onClick={onCreate}>
            <span className="home-action-icon"><PlusIcon /></span>
            <span><strong>Новый проект</strong><small>Начать с выбора объектов</small></span>
            <ArrowIcon className="home-action-arrow" />
          </button>
          <button type="button" className="home-action-card" onClick={onCreate}>
            <span className="home-action-icon"><ImageIcon /></span>
            <span><strong>Проект по фото участка</strong><small>Фото добавите в начале проекта</small></span>
            <ArrowIcon className="home-action-arrow" />
          </button>
          <button type="button" className="home-action-card" disabled={!latestProject} onClick={() => latestProject && onOpenProject(latestProject)}>
            <span className="home-action-icon"><SparkIcon /></span>
            <span><strong>Новый вариант</strong><small>{latestProject ? 'Продолжить последний проект' : 'Сначала создайте проект'}</small></span>
            <ArrowIcon className="home-action-arrow" />
          </button>
        </div>
      </section>

      <section className="home-dashboard-section" aria-labelledby="home-projects-title">
        <button
          type="button"
          className="home-section-link"
          onClick={() => setShowProjects((value) => !value)}
          aria-expanded={showProjects}
          aria-controls="home-project-list"
          disabled={loading || Boolean(error)}
        >
          <span><strong id="home-projects-title">Мои проекты</strong><small>{loading ? 'Загрузка…' : countLabel}</small></span>
          <ArrowIcon className={showProjects ? 'expanded' : ''} />
        </button>

        {showProjects && projects.length > 0 && (
          <div className="home-project-list" id="home-project-list">
            {projects.map((project) => (
              <button type="button" className="home-project-row" key={project.id} onClick={() => onOpenProject(project)}>
                <span className="home-project-row-icon"><HomeIcon /></span>
                <span className="home-project-row-copy"><strong>{project.name}</strong><small>{projectDetail(project)}</small></span>
                <span className="home-project-row-date">{formatDate(project.updated_at)}</span>
                <ArrowIcon />
              </button>
            ))}
            {projectsHasMore && <p className="home-project-more">Показаны последние 50 проектов.</p>}
          </div>
        )}
      </section>

      <section className="home-dashboard-section home-inspiration-section" aria-labelledby="home-inspiration-title">
        <div className="home-section-heading home-section-heading-inline">
          <div><h2 id="home-inspiration-title">Вдохновение</h2><p>Три свежие работы — полная лента отдельно.</p></div>
          <button type="button" className="home-text-link" onClick={onOpenIdeas}>Посмотреть ленту <ArrowIcon /></button>
        </div>

        {ideasLoading ? (
          <div className="home-inspiration-grid" aria-label="Загрузка вдохновения">
            <span className="home-inspiration-skeleton skeleton-card" />
            <span className="home-inspiration-skeleton skeleton-card" />
            <span className="home-inspiration-skeleton skeleton-card" />
          </div>
        ) : ideas.length > 0 ? (
          <div className="home-inspiration-grid">
            {ideas.map((idea) => <InspirationCard key={idea.id} idea={idea} onOpen={onOpenIdeas} />)}
          </div>
        ) : ideasError ? (
          <div className="home-inline-state"><span>Не удалось загрузить вдохновение.</span><button type="button" onClick={() => void loadIdeas()}>Повторить</button></div>
        ) : (
          <div className="home-inline-state"><span>В ленте пока нет опубликованных работ.</span><button type="button" onClick={onOpenIdeas}>Открыть Идеи</button></div>
        )}
      </section>
    </section>
  )
}