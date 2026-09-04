import { useEffect, useMemo, useState } from 'react'
import * as api from '../api'
import type { Project } from '../types'
import { ArrowIcon, HomeIcon, PlusIcon } from './Icons'
import { ProjectModal, type NewProjectPayload } from './ProjectModal'

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(new Date(value))
}

function ProjectCard({ project, onOpen }: { project: Project; onOpen: () => void }) {
  const detail = [project.context.house_area_m2 ? `${project.context.house_area_m2} м²` : null, project.context.floors ? `${project.context.floors} эт.` : null, project.context.architecture_style || null].filter(Boolean).join(' · ')
  return (
    <button className="project-card" onClick={onOpen}>
      <div className="project-visual">
        <div className="blueprint-line one"/><div className="blueprint-line two"/><div className="blueprint-line three"/>
        <HomeIcon className="project-home-icon" />
        <span className="project-date">{formatDate(project.updated_at)}</span>
      </div>
      <div className="project-card-body">
        <div><h3>{project.name}</h3><p>{detail || 'Добавьте параметры проекта'}</p></div>
        <span className="round-arrow"><ArrowIcon /></span>
      </div>
    </button>
  )
}

export function ProjectsScreen({ onOpenProject }: { onOpenProject: (project: Project) => void }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const page = await api.listProjects(null, 50)
      setProjects(page.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить проекты')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const subtitle = useMemo(() => projects.length === 0 ? 'Создайте первый проект и начните проектирование в AuRoom.' : `${projects.length} ${projects.length === 1 ? 'проект' : projects.length < 5 ? 'проекта' : 'проектов'} в работе`, [projects.length])

  async function handleCreate(payload: NewProjectPayload) {
    const created = await api.createProject(payload)
    setProjects((prev) => [created, ...prev])
    setShowCreate(false)
    onOpenProject(created)
  }

  return (
    <section className="page-content projects-page">
      <div className="page-heading-row">
        <div><span className="eyebrow">ВАША СТУДИЯ</span><h1>Главная</h1><p>{subtitle}</p></div>
        <button className="primary-button" onClick={() => setShowCreate(true)}><PlusIcon /> Новый проект</button>
      </div>

      {error && <div className="banner-error">{error}<button onClick={() => void load()}>Повторить</button></div>}
      {loading ? (
        <div className="project-grid"><div className="project-card skeleton-card"/><div className="project-card skeleton-card"/></div>
      ) : projects.length ? (
        <div className="project-grid">{projects.map((p) => <ProjectCard key={p.id} project={p} onOpen={() => onOpenProject(p)} />)}<button className="new-project-tile" onClick={() => setShowCreate(true)}><PlusIcon /><strong>Новый проект</strong><span>Создать пространство в AuRoom</span></button></div>
      ) : (
        <div className="empty-state"><div className="empty-icon"><HomeIcon /></div><h2>Первый проект — за минуту</h2><p>Название, пара параметров и можно переходить к планировке, фасаду, участку или интерьеру.</p><button className="primary-button" onClick={() => setShowCreate(true)}><PlusIcon /> Создать проект</button></div>
      )}
      {showCreate && <ProjectModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
    </section>
  )
}
