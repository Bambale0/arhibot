import { useState } from 'react'
import * as api from './api'
import { useAuth } from './auth'
import type { Asset, Generation, GenerationMode, Project } from './types'
import { AdminScreen } from './components/AdminScreen'
import { AppFrame, type AppSection } from './components/AppFrame'
import { AuthScreen } from './components/AuthScreen'
import { CreateScreen } from './components/CreateScreen'
import { HistoryScreen } from './components/HistoryScreen'
import { IdeasScreen } from './components/IdeasScreen'
import { ProfileScreen } from './components/ProfileScreen'
import { ProjectsScreen } from './components/ProjectsScreen'
import { WorkspaceScreen } from './components/WorkspaceScreen'

function Loader() {
  return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />AuRoom</div><div className="loader-line"><span /></div></div>
}

function TelegramAuthError({ message }: { message?: string | null }) {
  return (
    <div className="boot-loader">
      <div className="wordmark"><span className="wordmark-dot" />AuRoom</div>
      <div className="empty-state">
        <h2>Не удалось войти через Telegram</h2>
        <p>{message || 'Telegram-сессия не была подтверждена. Повторите вход.'}</p>
        <button className="primary-button" onClick={() => window.location.reload()}>Повторить вход</button>
      </div>
    </div>
  )
}

function initialSection(): AppSection {
  return new URLSearchParams(window.location.search).get('billing') === 'return' ? 'profile' : 'home'
}

function initialAdmin() {
  return new URLSearchParams(window.location.search).get('admin') === '1'
}

export default function App() {
  const { user, loading, error } = useAuth()
  const [section, setSection] = useState<AppSection>(initialSection)
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [workspaceMode, setWorkspaceMode] = useState<GenerationMode>('floor_plan')
  const [workspacePrompt, setWorkspacePrompt] = useState('')
  const [workspaceAsset, setWorkspaceAsset] = useState<Asset | null>(null)
  const [createMode, setCreateMode] = useState<GenerationMode | null>(null)
  const [createPrompt, setCreatePrompt] = useState('')
  const [adminOpen, setAdminOpen] = useState(initialAdmin)

  if (loading) return <Loader />
  if (!user) {
    if (window.Telegram?.WebApp?.initData) return <TelegramAuthError message={error} />
    return <AuthScreen />
  }

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  if (adminOpen && isAdmin) return <AdminScreen onClose={() => setAdminOpen(false)} />
  if (activeProject) return (
    <WorkspaceScreen
      project={activeProject}
      initialMode={workspaceMode}
      initialPrompt={workspacePrompt}
      initialAsset={workspaceAsset}
      onBack={() => { setActiveProject(null); setWorkspaceAsset(null) }}
      onProjectChange={setActiveProject}
    />
  )

  function openWorkspace(project: Project, mode: GenerationMode = 'floor_plan', prompt = '', asset: Asset | null = null) {
    setWorkspaceMode(mode)
    setWorkspacePrompt(prompt)
    setWorkspaceAsset(asset)
    setActiveProject(project)
  }

  async function openHistoryGeneration(generation: Generation, useOutput: boolean) {
    const project = await api.getProject(generation.project_id)
    let asset: Asset | null = useOutput ? generation.output_asset : null
    if (!useOutput && generation.input_asset_id) {
      try { asset = await api.getAsset(generation.input_asset_id) } catch { asset = null }
    }
    openWorkspace(project, generation.type, generation.prompt, asset)
  }

  function navigate(next: AppSection) {
    setSection(next)
    if (next !== 'create') {
      setCreateMode(null)
      setCreatePrompt('')
    }
  }

  return (
    <AppFrame active={section} onNavigate={navigate}>
      {section === 'home' && <ProjectsScreen onOpenProject={(project) => openWorkspace(project, 'floor_plan')} />}
      {section === 'ideas' && <IdeasScreen onUseIdea={(mode, prompt) => { setCreateMode(mode); setCreatePrompt(prompt); setSection('create') }} />}
      {section === 'create' && <CreateScreen initialMode={createMode} initialPrompt={createPrompt} onOpenProject={(project, mode, prompt) => openWorkspace(project, mode, prompt)} />}
      {section === 'history' && <HistoryScreen onOpenGeneration={(generation) => { void openHistoryGeneration(generation, false) }} onUseAsSource={(generation) => { void openHistoryGeneration(generation, true) }} />}
      {section === 'profile' && <ProfileScreen onOpenAdmin={isAdmin ? () => setAdminOpen(true) : undefined} />}
    </AppFrame>
  )
}
