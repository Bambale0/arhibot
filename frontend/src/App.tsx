import { useState } from 'react'
import { useAuth } from './auth'
import type { Project } from './types'
import { AuthScreen } from './components/AuthScreen'
import { ProjectsScreen } from './components/ProjectsScreen'
import { WorkspaceScreen } from './components/WorkspaceScreen'

function Loader() {
  return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />{import.meta.env.VITE_APP_NAME || 'ArchiAI'}</div><div className="loader-line"><span /></div></div>
}

export default function App() {
  const { user, loading } = useAuth()
  const [activeProject, setActiveProject] = useState<Project | null>(null)

  if (loading) return <Loader />
  if (!user) return <AuthScreen />
  if (activeProject) return <WorkspaceScreen project={activeProject} onBack={() => setActiveProject(null)} onProjectChange={setActiveProject} />
  return <ProjectsScreen onOpenProject={setActiveProject} />
}
