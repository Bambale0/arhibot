import { useState } from 'react'
import { useAuth } from './auth'
import type { GenerationMode, Project } from './types'
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

export default function App() {
  const { user, loading } = useAuth()
  const [section, setSection] = useState<AppSection>('home')
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [workspaceMode, setWorkspaceMode] = useState<GenerationMode>('floor_plan')
  const [createMode, setCreateMode] = useState<GenerationMode | null>(null)

  if (loading) return <Loader />
  if (!user) return <AuthScreen />
  if (activeProject) return <WorkspaceScreen project={activeProject} initialMode={workspaceMode} onBack={() => setActiveProject(null)} onProjectChange={setActiveProject} />

  function openWorkspace(project: Project, mode: GenerationMode = 'floor_plan') {
    setWorkspaceMode(mode)
    setActiveProject(project)
  }

  function navigate(next: AppSection) {
    setSection(next)
    if (next !== 'create') setCreateMode(null)
  }

  return (
    <AppFrame active={section} onNavigate={navigate}>
      {section === 'home' && <ProjectsScreen onOpenProject={(project) => openWorkspace(project, 'floor_plan')} />}
      {section === 'ideas' && <IdeasScreen onUseIdea={(mode) => { setCreateMode(mode); setSection('create') }} />}
      {section === 'create' && <CreateScreen initialMode={createMode} onOpenProject={openWorkspace} />}
      {section === 'history' && <HistoryScreen />}
      {section === 'profile' && <ProfileScreen />}
    </AppFrame>
  )
}
