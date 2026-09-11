import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import * as api from './api'
import { useAuth } from './auth'
import { discardQuestionnaireDraft } from './questionnaireApi'
import type { Generation, Project } from './types'
import { AppFrame, type AppSection } from './components/AppFrame'
import { AuthScreen } from './components/AuthScreen'
import { ProjectsScreen } from './components/ProjectsScreen'

const AdminScreen = lazy(() => import('./components/AdminScreen').then((module) => ({ default: module.AdminScreen })))
const CreateScreen = lazy(() => import('./components/CreateScreen').then((module) => ({ default: module.CreateScreen })))
const HistoryScreen = lazy(() => import('./components/HistoryScreen').then((module) => ({ default: module.HistoryScreen })))
const HistoryGenerationScreen = lazy(() => import('./components/HistoryGenerationScreen').then((module) => ({ default: module.HistoryGenerationScreen })))
const IdeasScreen = lazy(() => import('./components/IdeasScreen').then((module) => ({ default: module.IdeasScreen })))
const ProfileScreen = lazy(() => import('./components/ProfileScreen').then((module) => ({ default: module.ProfileScreen })))
const QuestionnaireWorkspaceScreen = lazy(() => import('./components/QuestionnaireWorkspaceScreen').then((module) => ({ default: module.QuestionnaireWorkspaceScreen })))

function Loader() {
  return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />AuRoom</div><div className="loader-line"><span /></div></div>
}

function TelegramAuthError({ message }: { message?: string | null }) {
  return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />AuRoom</div><div className="empty-state"><h2>Не удалось войти через Telegram</h2><p>{message || 'Telegram-сессия не была подтверждена. Повторите вход.'}</p><button className="primary-button" onClick={() => window.location.reload()}>Повторить вход</button></div></div>
}
function initialSection(): AppSection {
  const params = new URLSearchParams(window.location.search)
  if (params.get('billing') === 'return') return 'profile'
  if (params.get('idea')) return 'ideas'
  if (params.get('generation')) return 'history'
  return 'home'
}
function initialAdmin() { return new URLSearchParams(window.location.search).get('admin') === '1' }

type HistoryResult = { project: Project; generation: Generation }

export default function App() {
  const { user, loading, error } = useAuth()
  const [section, setSection] = useState<AppSection>(initialSection)
  const [questionnaireProject, setQuestionnaireProject] = useState<Project | null>(null)
  const [questionnaireObjects, setQuestionnaireObjects] = useState<string[]>([])
  const [historyResult, setHistoryResult] = useState<HistoryResult | null>(null)
  const [adminOpen, setAdminOpen] = useState(initialAdmin)
  const deepLinkHandled = useRef(false)

  useEffect(() => {
    if (loading || !user || deepLinkHandled.current) return
    const params = new URLSearchParams(window.location.search)
    const generationId = params.get('generation')
    const projectId = params.get('project')
    if (!generationId && !projectId) return

    deepLinkHandled.current = true
    void (async () => {
      try {
        if (generationId) {
          const generation = await api.getGeneration(generationId)
          const project = await api.getProject(generation.project_id)
          setHistoryResult({ project, generation })
          setSection('history')
          return
        }
        if (projectId) {
          const project = await api.getProject(projectId)
          openProject(project)
        }
      } catch {
        setSection(generationId ? 'history' : 'home')
      }
    })()
  }, [loading, user])

  if (loading) return <Loader />
  if (!user) { if (window.Telegram?.WebApp?.initData) return <TelegramAuthError message={error} />; return <AuthScreen /> }
  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  if (adminOpen && isAdmin) return <Suspense fallback={<Loader />}><AdminScreen onClose={() => setAdminOpen(false)} /></Suspense>
  if (questionnaireProject) return <Suspense fallback={<Loader />}><QuestionnaireWorkspaceScreen project={questionnaireProject} selectedObjects={questionnaireObjects} onBack={() => { void closeQuestionnaire() }} onProjectChange={setQuestionnaireProject} /></Suspense>
  if (historyResult) return <Suspense fallback={<Loader />}><HistoryGenerationScreen project={historyResult.project} generation={historyResult.generation} onBack={() => setHistoryResult(null)} /></Suspense>

  function openQuestionnaire(project: Project, selectedObjects: string[]) { setQuestionnaireObjects(selectedObjects); setQuestionnaireProject(project) }
  function openQuestionnaireProject(project: Project): boolean {
    const selectedObjects = project.context.design_session?.selected_objects || []
    if (!selectedObjects.length) return false
    openQuestionnaire(project, selectedObjects)
    return true
  }
  function openProject(project: Project) {
    if (!openQuestionnaireProject(project)) setSection('history')
  }
  async function closeQuestionnaire() {
    const project = questionnaireProject
    setQuestionnaireProject(null)
    setQuestionnaireObjects([])
    if (project?.context.questionnaire_draft && !project.context.design_session?.source_step_completed) {
      try { await discardQuestionnaireDraft(project.id) } catch { /* maintenance removes abandoned drafts later */ }
    }
  }
  async function openHistoryGeneration(generation: Generation) {
    const project = await api.getProject(generation.project_id)
    if (openQuestionnaireProject(project)) return
    setHistoryResult({ project, generation })
  }
  function navigate(next: AppSection) { setSection(next) }

  return <AppFrame active={section} onNavigate={navigate}>
    {section === 'home' && <ProjectsScreen onOpenProject={openProject} onCreate={() => setSection('create')} />}
    {section !== 'home' && <Suspense fallback={<Loader />}>
      {section === 'ideas' && <IdeasScreen onOpenQuestionnaire={openQuestionnaire} />}
      {section === 'create' && <CreateScreen onOpenQuestionnaire={openQuestionnaire} />}
      {section === 'history' && <HistoryScreen onOpenGeneration={(generation) => { void openHistoryGeneration(generation) }} />}
      {section === 'profile' && <ProfileScreen onOpenAdmin={isAdmin ? () => setAdminOpen(true) : undefined} />}
    </Suspense>}
  </AppFrame>
}
