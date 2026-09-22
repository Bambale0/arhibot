import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import * as api from './api'
import { useAuth } from './auth'
import { discardQuestionnaireDraft } from './questionnaireApi'
import type { Generation, Project } from './types'
import { AppFrame, type AppSection } from './components/AppFrame'
import { AuthScreen } from './components/AuthScreen'
import { ProjectsScreen } from './components/ProjectsScreen'
import { TelegramFullscreenButton } from './components/TelegramFullscreenButton'

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

function TelegramAuthError({ message, onRetry }: { message?: string | null; onRetry: () => void }) {
  return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />AuRoom</div><div className="empty-state"><h2>Не удалось войти через Telegram</h2><p>{message || 'Telegram-сессия не была подтверждена. Повторите вход.'}</p><button className="primary-button" onClick={onRetry}>Повторить вход</button></div></div>
}
function initialSection(): AppSection {
  const params = new URLSearchParams(window.location.search)
  if (params.get('billing') === 'return') return 'profile'
  const direct = params.get('section')
  if (direct === 'home' || direct === 'ideas' || direct === 'create' || direct === 'history' || direct === 'profile') return direct
  if (params.get('idea')) return 'ideas'
  if (params.get('generation')) return 'history'
  return 'home'
}
function initialAdmin() { return new URLSearchParams(window.location.search).get('admin') === '1' }

type HistoryResult = { project: Project; generation: Generation }

export default function App() {
  const { user, loading, error, retrySession } = useAuth()
  const [section, setSection] = useState<AppSection>(initialSection)
  const [questionnaireProject, setQuestionnaireProject] = useState<Project | null>(null)
  const [questionnaireObjects, setQuestionnaireObjects] = useState<string[]>([])
  const [historyResult, setHistoryResult] = useState<HistoryResult | null>(null)
  const [adminOpen, setAdminOpen] = useState(initialAdmin)
  const [routeRevision, setRouteRevision] = useState(0)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const deepLinkHandled = useRef(false)
  const routeRequest = useRef(0)
  const questionnaireProjectRef = useRef<Project | null>(null)

  useEffect(() => {
    const handlePopState = () => {
      const abandonedProject = questionnaireProjectRef.current
      questionnaireProjectRef.current = null
      if (abandonedProject?.context.questionnaire_draft && !abandonedProject.context.design_session?.source_step_completed) {
        void discardQuestionnaireDraft(abandonedProject.id).catch(() => { /* maintenance removes abandoned drafts later */ })
      }
      routeRequest.current += 1
      setSection(initialSection())
      setAdminOpen(initialAdmin())
      setQuestionnaireProject(null)
      setQuestionnaireObjects([])
      setHistoryResult(null)
      setRouteLoading(false)
      setRouteError(null)
      deepLinkHandled.current = false
      setRouteRevision((value) => value + 1)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (loading || !user || adminOpen || deepLinkHandled.current) return
    const params = new URLSearchParams(window.location.search)
    const generationId = params.get('generation')
    const projectId = params.get('project')
    if (!generationId && !projectId) {
      setRouteLoading(false)
      setRouteError(null)
      return
    }

    deepLinkHandled.current = true
    const request = ++routeRequest.current
    let cancelled = false
    setRouteLoading(true)
    setRouteError(null)
    void (async () => {
      try {
        if (generationId) {
          const generation = await api.getGeneration(generationId)
          const project = await api.getProject(generation.project_id)
          if (cancelled || request !== routeRequest.current) return
          setHistoryResult({ project, generation })
          setSection('history')
          return
        }
        if (projectId) {
          const project = await api.getProject(projectId)
          if (cancelled || request !== routeRequest.current) return
          openProject(project, false)
        }
      } catch (routeFailure) {
        if (!cancelled && request === routeRequest.current) {
          setRouteError(routeFailure instanceof Error ? routeFailure.message : 'Не удалось открыть ссылку')
        }
      } finally {
        if (!cancelled && request === routeRequest.current) setRouteLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [adminOpen, loading, routeRevision, user])

  if (loading) return <Loader />
  if (!user) { if (window.Telegram?.WebApp?.initData) return <TelegramAuthError message={error} onRetry={retrySession} />; return <AuthScreen /> }
  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  if (routeLoading) return <Loader />
  if (routeError) return <div className="boot-loader"><div className="wordmark"><span className="wordmark-dot" />AuRoom</div><div className="empty-state"><h2>Не удалось открыть ссылку</h2><p>{routeError}</p><div className="questionnaire-actions"><button className="primary-button" onClick={() => { deepLinkHandled.current = false; setRouteRevision((value) => value + 1) }}>Повторить</button><button className="secondary-button" onClick={() => navigate('home')}>На главную</button></div></div></div>
  if (adminOpen && isAdmin) return <><TelegramFullscreenButton/><Suspense fallback={<Loader />}><AdminScreen onClose={closeAdmin} /></Suspense></>
  if (questionnaireProject) return <><TelegramFullscreenButton/><Suspense fallback={<Loader />}><QuestionnaireWorkspaceScreen project={questionnaireProject} selectedObjects={questionnaireObjects} onBack={() => { void closeQuestionnaire() }} onProjectChange={updateQuestionnaireProject} /></Suspense></>
  if (historyResult) return <><TelegramFullscreenButton/><Suspense fallback={<Loader />}><HistoryGenerationScreen project={historyResult.project} generation={historyResult.generation} onBack={closeHistoryResult} /></Suspense></>

  function routeUrl(params: URLSearchParams) {
    const query = params.toString()
    return `${window.location.pathname}${query ? `?${query}` : ''}`
  }
  function pushLayer(param: 'project'|'generation'|'admin', value: string, layer: string) {
    const params = new URLSearchParams(window.location.search)
    for (const key of ['admin', 'application', 'user', 'idea', 'generation', 'project', 'billing', 'payment_id']) params.delete(key)
    params.set(param, value)
    window.history.pushState({ auroomLayer:layer }, '', routeUrl(params))
    deepLinkHandled.current = true
  }
  function closeLayer(param: 'project'|'generation'|'admin', fallback: AppSection) {
    if (window.history.state?.auroomLayer) {
      window.history.back()
      return
    }
    const params = new URLSearchParams(window.location.search)
    params.delete(param)
    params.set('section', fallback)
    window.history.replaceState({}, '', routeUrl(params))
    deepLinkHandled.current = false
  }
  function openQuestionnaire(project: Project, selectedObjects: string[], syncUrl = true) {
    questionnaireProjectRef.current = project
    setQuestionnaireObjects(selectedObjects)
    setQuestionnaireProject(project)
    if (syncUrl) pushLayer('project', project.id, 'questionnaire')
  }
  function updateQuestionnaireProject(project: Project) {
    questionnaireProjectRef.current = project
    setQuestionnaireProject(project)
  }
  function openQuestionnaireProject(project: Project, syncUrl = true): boolean {
    const selectedObjects = project.context.design_session?.selected_objects || []
    if (!selectedObjects.length) return false
    openQuestionnaire(project, selectedObjects, syncUrl)
    return true
  }
  function openProject(project: Project, syncUrl = true) {
    if (!openQuestionnaireProject(project, syncUrl)) setSection('history')
  }
  async function closeQuestionnaire() {
    const project = questionnaireProject
    questionnaireProjectRef.current = null
    setQuestionnaireProject(null)
    setQuestionnaireObjects([])
    closeLayer('project', 'home')
    if (project?.context.questionnaire_draft && !project.context.design_session?.source_step_completed) {
      try { await discardQuestionnaireDraft(project.id) } catch { /* maintenance removes abandoned drafts later */ }
    }
  }
  async function openHistoryGeneration(generation: Generation) {
    const project = await api.getProject(generation.project_id)
    if (openQuestionnaireProject(project)) return
    setHistoryResult({ project, generation })
    pushLayer('generation', generation.id, 'history-result')
  }
  function closeHistoryResult() {
    setHistoryResult(null)
    closeLayer('generation', 'history')
  }
  function openAdmin() {
    setAdminOpen(true)
    pushLayer('admin', '1', 'admin')
  }
  function closeAdmin() {
    setAdminOpen(false)
    closeLayer('admin', 'profile')
  }
  function navigate(next: AppSection) {
    const params = new URLSearchParams(window.location.search)
    const hasLayer = ['admin', 'application', 'user', 'idea', 'generation', 'project', 'billing', 'payment_id'].some((key) => params.has(key))
    if (section === next && !hasLayer) return
    routeRequest.current += 1
    setRouteLoading(false)
    setRouteError(null)
    setSection(next)
    params.set('section', next)
    for (const key of ['admin', 'application', 'user', 'idea', 'generation', 'project', 'billing', 'payment_id']) params.delete(key)
    deepLinkHandled.current = false
    window.history.pushState({}, '', routeUrl(params))
  }

  return <>
    <TelegramFullscreenButton/>
    <AppFrame active={section} onNavigate={navigate}>
        {section === 'home' && <ProjectsScreen onOpenProject={openProject} onCreate={() => setSection('create')} onOpenIdeas={() => setSection('ideas')} />}
      {section !== 'home' && <Suspense fallback={<Loader />}>
        {section === 'ideas' && <IdeasScreen onOpenQuestionnaire={openQuestionnaire} />}
        {section === 'create' && <CreateScreen onOpenQuestionnaire={openQuestionnaire} />}
        {section === 'history' && <HistoryScreen onOpenGeneration={openHistoryGeneration} />}
        {section === 'profile' && <ProfileScreen onOpenAdmin={isAdmin ? openAdmin : undefined} />}
      </Suspense>}
    </AppFrame>
  </>
}