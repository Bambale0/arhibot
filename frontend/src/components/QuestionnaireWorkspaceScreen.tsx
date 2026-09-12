import { useEffect, useMemo, useRef, useState, type ChangeEvent, type PointerEvent as ReactPointerEvent } from 'react'
import * as api from '../api'
import {
  acceptQuestionnaireInitialConcept,
  addQuestionnaireObject,
  createQuestionnaireGeneration,
  getQuestionnaireCatalog,
  getQuestionnaireGeneration,
  getQuestionnaireGenerationCost,
  getQuestionnaireSession,
  saveQuestionnaireSession,
  submitQuestionnaireApplication,
} from '../questionnaireApi'
import type {
  DesignSession,
  QuestionnaireAnswer,
  QuestionnaireCatalog,
  QuestionnaireCondition,
  QuestionnaireDefinition,
  QuestionnaireGenerationCost,
  QuestionnaireQuestion,
  NormalizedRect,
} from '../questionnaireTypes'
import type { AdminIdea, Asset, Generation, Project } from '../types'
import { BackIcon, ImageIcon, SparkIcon, UploadIcon } from './Icons'

const delay = (ms:number) => new Promise((resolve) => setTimeout(resolve, ms))
const text = (value:QuestionnaireAnswer|undefined) => Array.isArray(value) ? value.join(', ') : value === true ? 'Согласен' : value == null ? '' : String(value)

function conditionOk(condition:QuestionnaireCondition|null, answers:Record<string,QuestionnaireAnswer>, houseAccepted:boolean):boolean {
  if (!condition) return true
  if (condition.operator === 'house_accepted') return houseAccepted
  if (condition.operator === 'all') return (condition.conditions || []).every((item) => conditionOk(item, answers, houseAccepted))
  if (condition.operator === 'any') return (condition.conditions || []).some((item) => conditionOk(item, answers, houseAccepted))
  const answer = condition.question_id ? answers[condition.question_id] : undefined
  if (condition.operator === 'eq') return answer === condition.value
  if (condition.operator === 'neq') return answer !== condition.value
  if (condition.operator === 'in') return Array.isArray(condition.value) && typeof answer === 'string' && condition.value.includes(answer)
  if (condition.operator === 'contains') return Array.isArray(answer) && typeof condition.value === 'string' && answer.includes(condition.value)
  if (condition.operator === 'starts_with') return typeof answer === 'string' && typeof condition.value === 'string' && answer.startsWith(condition.value)
  if (condition.operator === 'not_contains_any') return !Array.isArray(answer) || !Array.isArray(condition.value) || !condition.value.some((item) => answer.includes(item))
  if (condition.operator === 'floor_option') {
    if (typeof answer !== 'string' || typeof condition.value !== 'string') return false
    const floorAnswer = answer.toLowerCase()
    if (condition.value === 'Первый этаж') return true
    if (condition.value === 'Второй этаж') return !floorAnswer.startsWith('1 ')
    if (condition.value === 'Третий этаж') return floorAnswer.includes('3')
    if (condition.value === 'Мансарда') return floorAnswer.includes('мансард')
    return false
  }
  return true
}

function sanitizeObjectAnswers(definition:QuestionnaireDefinition, answers:Record<string,QuestionnaireAnswer>, houseAccepted:boolean) {
  const next = { ...answers }
  for (let pass=0; pass<definition.questions.length; pass++) {
    let changed = false
    for (const question of definition.questions) {
      const value = next[question.id]
      if (value === undefined) continue
      if (!conditionOk(question.condition, next, houseAccepted)) {
        delete next[question.id]
        changed = true
        continue
      }
      if (question.kind === 'single' && typeof value === 'string') {
        const custom = value.startsWith('Свой вариант:') && question.options.includes('Свой вариант')
        const listed = question.options.length === 0 || question.options.includes(value)
        if (!custom && (!listed || !conditionOk(question.option_rules[value] || null, next, houseAccepted))) {
          delete next[question.id]
          changed = true
        }
      }
      if (question.kind === 'multi' && Array.isArray(value)) {
        const filtered = value.filter((item) => question.options.includes(item) && conditionOk(question.option_rules[item] || null, next, houseAccepted))
        if (filtered.length !== value.length) {
          if (filtered.length) next[question.id] = filtered
          else delete next[question.id]
          changed = true
        }
      }
    }
    if (!changed) break
  }
  return next
}

function newSession(version:string, selected:string[]):DesignSession {
  return {
    session_id:crypto.randomUUID(),
    catalog_version:version,
    selected_objects:selected,
    initial_concept_mode:true,
    survey_completed_objects:[],
    initial_generation_id:null,
    initial_concept_accepted:false,
    current_object:selected.length === 1 ? selected[0] : null,
    current_question_id:null,
    source_step_completed:false,
    source_asset_id:null,
    scene_asset_id:null,
    scene_generation_id:null,
    answers:{},
    accepted_objects:[],
    generation_ids:{},
    edit_question_ids:[],
    review_comments:{},
    edit_regions:{},
    lock_regions:{},
    region_mode:null,
    region_object:null,
    application_submitted:false,
  }
}

function answerEquals(left:QuestionnaireAnswer|undefined, right:QuestionnaireAnswer|undefined):boolean {
  if (Array.isArray(left) || Array.isArray(right)) return JSON.stringify(left) === JSON.stringify(right)
  return left === right
}

function normalizeStartedSession(stored:DesignSession, catalog:QuestionnaireCatalog):DesignSession {
  if (stored.catalog_version === catalog.version) return stored

  const definitions = new Map(catalog.questionnaires.map((item) => [item.key, item]))
  const houseAccepted = stored.accepted_objects.includes('eskez-doma')
  const nextAnswers:DesignSession['answers'] = Object.fromEntries(
    Object.entries(stored.answers).map(([key, answers]) => [key, { ...answers }]),
  )
  let currentQuestionId = stored.current_question_id

  for (const [objectKey, answers] of Object.entries(nextAnswers)) {
    if (stored.accepted_objects.includes(objectKey) || objectKey === 'zayavka') continue
    const definition = definitions.get(objectKey)
    if (!definition) continue

    // Re-evaluate old, unfinished answers against the current catalog. Accepted
    // objects are intentionally untouched because they are immutable snapshots.
    for (let pass=0; pass<definition.questions.length; pass++) {
      let changed = false
      for (const question of definition.questions) {
        const value = answers[question.id]
        if (value === undefined) continue
        if (!conditionOk(question.condition, answers, houseAccepted)) {
          delete answers[question.id]
          changed = true
          continue
        }
        if (question.skip_default !== null && answerEquals(value, question.skip_default) && !conditionOk(question.skip_condition, answers, houseAccepted)) {
          delete answers[question.id]
          changed = true
          continue
        }
        if (question.kind === 'single' && typeof value === 'string') {
          const custom = value.startsWith('Свой вариант:') && question.options.includes('Свой вариант')
          const placeholder = value === 'Свой вариант' && question.options.includes('Свой вариант')
          const listed = question.options.length === 0 || question.options.includes(value)
          const allowed = custom || (listed && conditionOk(question.option_rules[value] || null, answers, houseAccepted))
          if (placeholder || !allowed) {
            delete answers[question.id]
            changed = true
          }
        }
        if (question.kind === 'multi' && Array.isArray(value)) {
          const filtered = value.filter((item) => question.options.includes(item) && conditionOk(question.option_rules[item] || null, answers, houseAccepted))
          if (filtered.length !== value.length) {
            if (filtered.length) answers[question.id] = filtered
            else delete answers[question.id]
            changed = true
          }
        }
      }
      if (!changed) break
    }

    if (stored.current_object === objectKey) {
      const firstMissing = definition.questions.find((question) =>
        question.phase === 'pre_render'
        && conditionOk(question.condition, answers, houseAccepted)
        && answers[question.id] === undefined,
      )
      if (firstMissing) currentQuestionId = firstMissing.id
      else if (currentQuestionId && !definition.questions.some((question) => question.id === currentQuestionId && conditionOk(question.condition, answers, houseAccepted))) currentQuestionId = null
    }
  }

  return {
    ...stored,
    catalog_version:catalog.version,
    answers:nextAnswers,
    current_question_id:currentQuestionId,
  }
}

export function QuestionnaireWorkspaceScreen({ project, selectedObjects, onBack, onProjectChange }:{ project:Project; selectedObjects:string[]; onBack:()=>void; onProjectChange:(project:Project)=>void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [catalog, setCatalog] = useState<QuestionnaireCatalog|null>(null)
  const [session, setSession] = useState<DesignSession|null>(null)
  const [generationCost, setGenerationCost] = useState<QuestionnaireGenerationCost|null>(null)
  const [sourceAsset, setSourceAsset] = useState<Asset|null>(null)
  const [sceneAsset, setSceneAsset] = useState<Asset|null>(null)
  const [renderOutput, setRenderOutput] = useState<Asset|null>(null)
  const [draft, setDraft] = useState<string>('')
  const [multi, setMulti] = useState<string[]>([])
  const [reviewComment, setReviewComment] = useState<string>('')
  const [regionDraft, setRegionDraft] = useState<NormalizedRect|null>(null)
  const regionStartRef = useRef<{x:number;y:number}|null>(null)
  const [customOption, setCustomOption] = useState(false)
  const [busy, setBusy] = useState(false)
  const [generationInFlight, setGenerationInFlight] = useState(false)
  const [ideaPublication, setIdeaPublication] = useState<AdminIdea|null|undefined>(undefined)
  const [ideaPublishing, setIdeaPublishing] = useState(false)
  const [error, setError] = useState<string|null>(null)

  useEffect(() => {
    let stop=false
    void (async () => {
      try {
        const loaded = await getQuestionnaireCatalog()
        if (stop) return
        setCatalog(loaded)
        const order = loaded.sections.flatMap((section) => section.object_keys)
        const selected = order.filter((key) => selectedObjects.includes(key))
        const stored = await getQuestionnaireSession(project.id)
        if (stop) return
        const storedStarted = Boolean(stored && (
          stored.source_step_completed
          || stored.survey_completed_objects.length
          || Boolean(stored.initial_generation_id)
          || stored.initial_concept_accepted
          || stored.accepted_objects.length
          || Object.keys(stored.answers).length
          || Object.keys(stored.generation_ids).length
          || stored.application_submitted
        ))
        const initial = storedStarted && stored
          ? normalizeStartedSession(stored, loaded)
          : stored
            && stored.catalog_version === loaded.version
            && JSON.stringify(stored.selected_objects) === JSON.stringify(selected)
            ? stored
            : newSession(loaded.version, selected)
        setSession(initial)
        if (initial.source_asset_id) {
          try { setSourceAsset(await api.getAsset(initial.source_asset_id)) } catch { /* deleted source */ }
        }
        if (initial.scene_asset_id) {
          try { setSceneAsset(await api.getAsset(initial.scene_asset_id)) } catch { /* deleted scene */ }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Не удалось открыть опросник')
      }
    })()
    return () => { stop=true }
  }, [project.id])

  useEffect(() => {
    let stopped = false
    getQuestionnaireGenerationCost()
      .then((cost) => { if (!stopped) setGenerationCost(cost) })
      .catch(() => { if (!stopped) setGenerationCost(null) })
    return () => { stopped = true }
  }, [])

  const definitions = useMemo(() => new Map((catalog?.questionnaires || []).map((item) => [item.key, item])), [catalog])
  const current = session?.current_object ? definitions.get(session.current_object) || null : null
  const houseAccepted = session?.accepted_objects.includes('eskez-doma')
    || Boolean(session?.initial_concept_mode && session.selected_objects.includes('eskez-doma'))
  const objectAnswers = current && session ? session.answers[current.key] || {} : {}
  const visible = current ? current.questions.filter((q) => conditionOk(q.condition, objectAnswers, houseAccepted)) : []
  const active = current && session ? visible.find((q) => q.id === session.current_question_id) || null : null
  const currentGenerationId = current && session && session.region_mode == null ? session.generation_ids[current.key] || null : null
  const initialGenerationId = session?.initial_generation_id || null
  const latestAcceptedKey = session?.accepted_objects.at(-1) || null
  const latestAcceptedGenerationId = session?.scene_generation_id
    || (latestAcceptedKey ? session?.generation_ids[latestAcceptedKey] || null : null)

  useEffect(() => {
    setIdeaPublication(undefined)
    if (!latestAcceptedGenerationId) return
    let stopped = false
    api.getOwnIdeaPublication(latestAcceptedGenerationId)
      .then((publication) => { if (!stopped) setIdeaPublication(publication) })
      .catch(() => { if (!stopped) setIdeaPublication(null) })
    return () => { stopped = true }
  }, [latestAcceptedGenerationId])

  useEffect(() => {
    if (!session || !current || session.current_question_id || session.region_mode || generationInFlight) return
    if (current.key !== 'zayavka' && currentGenerationId) return
    const first = visible.find((q) => q.phase === (current.key === 'zayavka' ? 'application' : 'pre_render'))
    if (first && session.source_step_completed) void persist({ ...session, current_question_id:first.id })
  }, [session?.source_step_completed, current?.key, currentGenerationId, generationInFlight])

  useEffect(() => {
    if (!session || !current || current.key === 'zayavka' || !currentGenerationId || generationInFlight || session.region_mode) return
    let stopped = false
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        const generation = await getQuestionnaireGeneration(project.id, currentGenerationId)
        const completed = await poll(generation)
        if (stopped) return
        setRenderOutput(completed.output_asset)
        if (!session.current_question_id) {
          const review = current.questions.find((q) => q.phase === 'review')
          const next = { ...session, current_question_id:review?.id || null }
          const saved = await saveQuestionnaireSession(project.id, next)
          if (stopped) return
          setSession(saved)
          syncProject(saved)
        }
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : 'Не удалось восстановить генерацию')
      } finally {
        if (!stopped) {
          setBusy(false)
          setGenerationInFlight(false)
        }
      }
    })()
    return () => { stopped = true }
  }, [project.id, current?.key, currentGenerationId])

  useEffect(() => {
    if (!session?.initial_concept_mode || session.initial_concept_accepted || !initialGenerationId || current || generationInFlight) return
    let stopped = false
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        const existing = await getQuestionnaireGeneration(project.id, initialGenerationId)
        const completed = await poll(existing)
        if (!stopped) setRenderOutput(completed.output_asset)
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : 'Не удалось восстановить общую концепцию')
      } finally {
        if (!stopped) {
          setBusy(false)
          setGenerationInFlight(false)
        }
      }
    })()
    return () => { stopped = true }
  }, [project.id, initialGenerationId, session?.initial_concept_accepted, current?.key])

  useEffect(() => {
    if (!session || busy || generationInFlight || session.current_object || !sceneAsset) return
    // Backfill only legacy accepted sessions that predate explicit placement.
    // New masked edits always require the user-selected edit region below.
    const missingLock = session.accepted_objects.find((key) => !session.lock_regions[key])
    if (!missingLock) return
    const definition = definitions.get(missingLock)
    if (!definition) return
    const region = session.edit_regions[missingLock]
      || (missingLock === 'eskez-doma'
        ? { x:0.12, y:0.10, width:0.76, height:0.78 }
        : suggestedRegion(session, definition))
    void persist({ ...session, lock_regions:{ ...session.lock_regions, [missingLock]:region } })
  }, [session?.current_object, sceneAsset?.id])

  useEffect(() => {
    regionStartRef.current = null
    if (session?.region_mode === 'edit' && session.region_object) {
      setRegionDraft(session.edit_regions[session.region_object] || null)
      return
    }
    setRegionDraft(null)
  }, [session?.region_mode, session?.region_object])

  useEffect(() => {
    if (!active || !current || !session) return
    const value = objectAnswers[active.id]
    const customPrefix = 'Свой вариант:'
    const storedText = typeof value === 'string' ? value : ''
    const isCustom = storedText.startsWith(customPrefix)
    setCustomOption(isCustom)
    setDraft(isCustom ? storedText.slice(customPrefix.length).trim() : typeof value === 'number' || typeof value === 'string' ? String(value) : '')
    setMulti(Array.isArray(value) ? value : [])
    setReviewComment(current.key === 'eskez-doma' && active.id === '15б' ? session.review_comments[current.key] || '' : '')
  }, [active?.id, current?.key])

  function syncProject(next:DesignSession) {
    onProjectChange({ ...project, context:{ ...project.context, design_session:next } })
  }

  async function persist(next:DesignSession) {
    setBusy(true)
    setError(null)
    try {
      const saved = await saveQuestionnaireSession(project.id, next)
      setSession(saved)
      syncProject(saved)
      return saved
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить ответы')
      return null
    } finally {
      setBusy(false)
    }
  }

  async function submitApplication(next:DesignSession) {
    setBusy(true)
    setError(null)
    try {
      const result = await submitQuestionnaireApplication(project.id, next)
      setSession(result.session)
      syncProject(result.session)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отправить заявку')
    } finally {
      setBusy(false)
    }
  }

  function availableOptions(question:QuestionnaireQuestion) {
    return question.options.filter((option) => conditionOk(question.option_rules[option] || null, objectAnswers, houseAccepted))
  }

  function generationCostLabel() {
    if (!generationCost) return 'Стоимость уточняется'
    if (!generationCost.is_available || generationCost.credits == null) return 'Генерация временно недоступна'
    return generationCost.credits === 0 ? 'Бесплатно' : `${generationCost.credits} кр.`
  }

  async function addObject(key:string) {
    if (!session || busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await addQuestionnaireObject(project.id, key)
      setSession(result.session)
      syncProject(result.session)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить объект')
    } finally {
      setBusy(false)
    }
  }

  async function editInitialQuestion(key:string, questionId:string) {
    if (!session || session.initial_concept_accepted || session.initial_generation_id) return
    await persist({ ...session, current_object:key, current_question_id:questionId })
  }

  async function chooseObject(key:string) {
    if (!session || !session.selected_objects.includes(key)) return
    if (session.accepted_objects.includes(key) && !(session.initial_concept_mode && !session.initial_concept_accepted)) return
    const definition = definitions.get(key)
    if (!definition) return
    const next = { ...session, current_object:key, current_question_id:null, edit_question_ids:[] }
    const first = preQuestions(definition, next)[0]
    await persist({ ...next, current_question_id:first?.id || null })
  }

  async function startRefinement(key:string) {
    if (!session?.initial_concept_accepted || !session.accepted_objects.includes(key)) return
    setReviewComment('')
    await persist({
      ...session,
      current_object:key,
      current_question_id:null,
      region_mode:'edit',
      region_object:key,
    })
  }

  async function chooseApplication() {
    if (!session || !session.accepted_objects.length) return
    const definition = definitions.get('zayavka')
    const first = definition?.questions.find((q) => q.phase === 'application')
    await persist({ ...session, current_object:'zayavka', current_question_id:first?.id || null, edit_question_ids:[] })
  }

  async function setSource(asset:Asset|null) {
    if (!session) return
    const saved = await persist({ ...session, source_step_completed:true, source_asset_id:asset?.id || null, scene_asset_id:asset?.id || null })
    if (saved) { setSourceAsset(asset); setSceneAsset(asset) }
  }

  async function upload(event:ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    if (!['image/jpeg','image/png','image/webp'].includes(file.type)) {
      setError('Поддерживаются JPG, PNG и WebP.')
      return
    }
    setBusy(true)
    setError(null)
    try { await setSource(await api.uploadAsset(project.id, file, 'generation_input')) }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось загрузить фото') }
    finally { setBusy(false); event.target.value='' }
  }

  function preQuestions(definition:QuestionnaireDefinition, next:DesignSession) {
    const answers = next.answers[definition.key] || {}
    return definition.questions.filter((q) => q.phase === 'pre_render' && conditionOk(q.condition, answers, next.accepted_objects.includes('eskez-doma')))
  }

  function suggestedRegion(next:DesignSession, definition:QuestionnaireDefinition):NormalizedRect {
    const values = Object.values(next.answers[definition.key] || {}).flatMap((value) => Array.isArray(value) ? value : [value]).map(String).join(' ').toLowerCase()
    if (values.includes('слева')) return { x:0.03, y:0.18, width:0.42, height:0.66 }
    if (values.includes('справа')) return { x:0.55, y:0.18, width:0.42, height:0.66 }
    if (values.includes('сзади') || values.includes('во дворе')) return { x:0.18, y:0.03, width:0.64, height:0.43 }
    if (values.includes('улиц') || values.includes('въезд')) return { x:0.18, y:0.57, width:0.64, height:0.40 }
    return { x:0.55, y:0.40, width:0.42, height:0.55 }
  }

  async function startGenerationOrRegion(next:DesignSession, definition:QuestionnaireDefinition) {
    if (next.accepted_objects.length > 0 && next.scene_asset_id && !next.edit_regions[definition.key]) {
      return persist({
        ...next,
        current_question_id:null,
        region_mode:'edit',
        region_object:definition.key,
      })
    }
    setGenerationInFlight(true)
    const staged = await persist({ ...next, current_question_id:null, region_mode:null, region_object:null })
    if (!staged) {
      setGenerationInFlight(false)
      return null
    }
    return generate(staged, definition)
  }

  function clampRegionCoordinate(value:number) {
    return Math.max(0, Math.min(1, value))
  }

  function regionPoint(event:ReactPointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x:clampRegionCoordinate((event.clientX - bounds.left) / bounds.width),
      y:clampRegionCoordinate((event.clientY - bounds.top) / bounds.height),
    }
  }

  function beginRegionSelection(event:ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const point = regionPoint(event)
    regionStartRef.current = point
    setRegionDraft({ x:point.x, y:point.y, width:0, height:0 })
  }

  function moveRegionSelection(event:ReactPointerEvent<HTMLDivElement>) {
    const start = regionStartRef.current
    if (!start) return
    event.preventDefault()
    const point = regionPoint(event)
    setRegionDraft({
      x:Math.min(start.x, point.x),
      y:Math.min(start.y, point.y),
      width:Math.abs(point.x - start.x),
      height:Math.abs(point.y - start.y),
    })
  }

  function endRegionSelection(event:ReactPointerEvent<HTMLDivElement>) {
    if (!regionStartRef.current) return
    event.preventDefault()
    regionStartRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  async function confirmEditRegion() {
    if (!session || session.region_mode !== 'edit' || !session.region_object || !regionDraft) return
    if (regionDraft.width < 0.03 || regionDraft.height < 0.03) {
      setError('Выделите область крупнее: она должна точно покрывать место будущего объекта.')
      return
    }
    const definition = definitions.get(session.region_object)
    if (!definition) return
    const refinement = session.initial_concept_mode && session.initial_concept_accepted && session.accepted_objects.includes(definition.key)
    if (refinement && !reviewComment.trim()) {
      setError('Опишите, что именно нужно изменить в выделенной области.')
      return
    }
    const saved = await persist({
      ...session,
      edit_regions:{ ...session.edit_regions, [definition.key]:regionDraft },
      review_comments:refinement ? { ...session.review_comments, [definition.key]:reviewComment.trim() } : session.review_comments,
      region_mode:null,
      region_object:null,
    })
    if (saved) await generate(saved, definition)
  }

  async function cancelEditRegion() {
    if (!session || session.region_mode !== 'edit' || !session.region_object) return
    const definition = definitions.get(session.region_object)
    if (!definition) return
    const lastQuestion = preQuestions(definition, session).at(-1)
    await persist({
      ...session,
      current_question_id:lastQuestion?.id || null,
      region_mode:null,
      region_object:null,
    })
  }

  async function poll(generation:Generation) {
    let currentGeneration = generation
    const deadline = Date.now() + 6 * 60 * 1000
    let transientErrors = 0
    while (['queued','processing'].includes(currentGeneration.status) && Date.now() < deadline) {
      await delay(2000)
      try {
        currentGeneration = await getQuestionnaireGeneration(project.id, currentGeneration.id)
        transientErrors = 0
      } catch (err) {
        transientErrors += 1
        if (transientErrors >= 5) throw err
      }
    }
    if (['queued','processing'].includes(currentGeneration.status)) {
      throw new Error('Генерация всё ещё выполняется. Результат сохранён — откройте проект чуть позже.')
    }
    if (currentGeneration.status !== 'completed' || !currentGeneration.output_asset) {
      throw new Error(currentGeneration.error || 'Генерация не завершилась')
    }
    return currentGeneration
  }

  async function generateInitial(next:DesignSession) {
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    setRenderOutput(null)
    try {
      const queued = await createQuestionnaireGeneration(project.id)
      const queuedState = { ...next, initial_generation_id:queued.id }
      setSession(queuedState)
      syncProject(queuedState)
      const completed = await poll(queued)
      setRenderOutput(completed.output_asset)
    } catch (err) {
      if (err instanceof api.ApiError && err.errorType === 'insufficient_credits') setError('Недостаточно кредитов. Пополните баланс в Профиле.')
      else setError(err instanceof Error ? err.message : 'Не удалось создать общую концепцию')
    } finally {
      setBusy(false)
      setGenerationInFlight(false)
    }
  }

  async function reopenInitialAnswers() {
    if (!session) return
    const saved = await persist({ ...session, initial_generation_id:null })
    if (saved) setRenderOutput(null)
  }

  async function acceptInitial() {
    setBusy(true)
    setError(null)
    try {
      const result = await acceptQuestionnaireInitialConcept(project.id)
      setSession(result.session)
      syncProject(result.session)
      if (renderOutput) setSceneAsset(renderOutput)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось принять общую концепцию')
    } finally {
      setBusy(false)
    }
  }

  async function generate(next:DesignSession, definition:QuestionnaireDefinition) {
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    setRenderOutput(null)
    try {
      const queued = await createQuestionnaireGeneration(project.id)
      const queuedState = {
        ...next,
        generation_ids:{ ...next.generation_ids, [definition.key]:queued.id },
      }
      // The backend stores this generation ID atomically with generation creation.
      // Mirror it locally only; a second PUT here would reopen the race this endpoint removes.
      setSession(queuedState)
      syncProject(queuedState)

      const generation = await poll(queued)
      setRenderOutput(generation.output_asset)
      const review = definition.questions.find((q) => q.phase === 'review')
      await persist({
        ...queuedState,
        current_question_id:review?.id || null,
      })
    } catch (err) {
      if (err instanceof api.ApiError && err.errorType === 'insufficient_credits') setError('Недостаточно кредитов. Пополните баланс в Профиле.')
      else setError(err instanceof Error ? err.message : 'Не удалось создать эскиз')
    } finally {
      setBusy(false)
      setGenerationInFlight(false)
    }
  }

  async function resumeOrRetryGeneration() {
    if (!session || !current || current.key === 'zayavka') return
    const generationId = session.generation_ids[current.key]
    if (!generationId) return startGenerationOrRegion(session, current)
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    try {
      const existing = await getQuestionnaireGeneration(project.id, generationId)
      if (existing.status !== 'failed') {
        const generation = await poll(existing)
        setRenderOutput(generation.output_asset)
        const review = current.questions.find((q) => q.phase === 'review')
        await persist({ ...session, current_question_id:review?.id || null })
        return
      }
      const generationIds = { ...session.generation_ids }
      delete generationIds[current.key]
      const saved = await persist({ ...session, generation_ids:generationIds })
      if (saved) await generate(saved, current)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось восстановить генерацию')
    } finally {
      setBusy(false)
      setGenerationInFlight(false)
    }
  }

  function clearUnacceptedGeneration(next:DesignSession):DesignSession {
    if (!current || next.accepted_objects.includes(current.key) || !next.generation_ids[current.key]) return next
    const generationIds = { ...next.generation_ids }
    delete generationIds[current.key]
    return { ...next, generation_ids:generationIds }
  }

  async function answer(question:QuestionnaireQuestion, value:QuestionnaireAnswer) {
    if (!session || !current) return
    const base = current.key === 'eskez-doma' && question.id === '15б'
      ? { ...session, review_comments:{ ...session.review_comments, [current.key]:reviewComment.trim() } }
      : session
    const rawObjectAnswers = { ...(base.answers[current.key] || {}), [question.id]:value }
    const sanitizedObjectAnswers = sanitizeObjectAnswers(current, rawObjectAnswers, houseAccepted)
    const nextAnswers = {
      ...base.answers,
      [current.key]:sanitizedObjectAnswers,
    }
    let next:DesignSession = { ...base, answers:nextAnswers }

    if (current.key === 'zayavka') {
      const questions = current.questions.filter((q) => q.phase === 'application' && conditionOk(q.condition, nextAnswers[current.key], houseAccepted))
      const index = questions.findIndex((q) => q.id === question.id)
      if (index < questions.length - 1) return persist({ ...next, current_question_id:questions[index + 1].id })
      if (question.id === '25' && value === true) {
        return submitApplication({ ...next, application_submitted:true, current_question_id:null })
      }
      return
    }

    if (next.edit_question_ids.includes(question.id)) {
      const answers = nextAnswers[current.key]
      const rest = next.edit_question_ids
        .filter((id) => id !== question.id)
        .filter((id) => {
          const target = current.questions.find((item) => item.id === id)
          return Boolean(target && conditionOk(target.condition, answers, next.accepted_objects.includes('eskez-doma')))
        })
      next = { ...next, edit_question_ids:rest }
      if (rest.length) return persist({ ...next, current_question_id:rest[0] })
      return startGenerationOrRegion({ ...next, current_question_id:null }, current)
    }

    if (question.phase === 'pre_render') {
      const questions = preQuestions(current, next)
      const index = questions.findIndex((q) => q.id === question.id)
      if (index < questions.length - 1) return persist({ ...next, current_question_id:questions[index + 1].id })
      if (next.initial_concept_mode && !next.initial_concept_accepted) {
        const completed = next.survey_completed_objects.includes(current.key)
          ? next.survey_completed_objects
          : [...next.survey_completed_objects, current.key]
        return persist({ ...next, survey_completed_objects:completed, current_object:null, current_question_id:null })
      }
      return startGenerationOrRegion({ ...next, current_question_id:null }, current)
    }

    if (current.key === 'eskez-doma' && question.id === '15') {
      if (typeof value === 'string' && value.startsWith('Да')) return accept(next, current)
      const q = current.questions.find((item) => item.id === '15а')
      return persist({ ...clearUnacceptedGeneration(next), current_question_id:q?.id || null })
    }
    if (current.key === 'eskez-doma' && question.id === '15а') {
      if (typeof value === 'string' && value.startsWith('Всё')) {
        const first = preQuestions(current, next)[0]
        const reviewComments = { ...next.review_comments }
        delete reviewComments[current.key]
        setReviewComment('')
        const reset = clearUnacceptedGeneration({ ...next, review_comments:reviewComments })
        return persist({ ...reset, current_question_id:first?.id || null, edit_question_ids:[] })
      }
      const q = current.questions.find((item) => item.id === '15б')
      return persist({ ...next, current_question_id:q?.id || null })
    }
    if (current.key === 'eskez-doma' && question.id === '15б' && Array.isArray(value)) {
      const ids = [...new Set(value.flatMap((item) => question.edit_targets[item] || []))]
      if (!ids.length) return startGenerationOrRegion({ ...next, current_question_id:null }, current)
      return persist({ ...next, edit_question_ids:ids, current_question_id:ids[0] })
    }

    if (question.phase === 'review') {
      if (typeof value === 'string' && value.startsWith('Да')) return accept(next, current)
      if (next.initial_concept_mode && next.initial_concept_accepted && next.accepted_objects.includes(current.key)) {
        setReviewComment(next.review_comments[current.key] || '')
        return persist({ ...next, current_question_id:null, region_mode:'edit', region_object:current.key })
      }
      const cleared = clearUnacceptedGeneration(next)
      const first = preQuestions(current, cleared)[0]
      return persist({ ...cleared, current_question_id:first?.id || null })
    }
  }

  async function previousQuestion() {
    if (!session || !current || !active || busy) return
    const phaseQuestions = current.questions.filter((question) =>
      question.phase === active.phase && conditionOk(question.condition, objectAnswers, houseAccepted)
    )
    const index = phaseQuestions.findIndex((question) => question.id === active.id)
    if (index > 0) {
      await persist({ ...session, current_question_id:phaseQuestions[index - 1].id })
      return
    }
    if (session.initial_concept_mode && !session.initial_concept_accepted) {
      await persist({ ...session, current_object:null, current_question_id:null })
      return
    }
    onBack()
  }

  async function finalizeAccept(next:DesignSession, definition:QuestionnaireDefinition, lockRegion:NormalizedRect) {
    if (!renderOutput) {
      setError('Нет готового эскиза для принятия.')
      return
    }
    const accepted = next.accepted_objects.includes(definition.key)
      ? next.accepted_objects
      : [...next.accepted_objects, definition.key]
    const saved = await persist({
      ...next,
      accepted_objects:accepted,
      lock_regions:{ ...next.lock_regions, [definition.key]:lockRegion },
      scene_asset_id:renderOutput.id,
      scene_generation_id:next.generation_ids[definition.key] || next.scene_generation_id,
      current_object:null,
      current_question_id:null,
      edit_question_ids:[],
      region_mode:null,
      region_object:null,
    })
    if (saved) setSceneAsset(renderOutput)
  }

  async function accept(next:DesignSession, definition:QuestionnaireDefinition) {
    if (!renderOutput) {
      setError('Нет готового эскиза для принятия.')
      return
    }
    const lockRegion = next.lock_regions[definition.key]
      || next.edit_regions[definition.key]
      || (definition.key === 'eskez-doma'
        ? { x:0.12, y:0.10, width:0.76, height:0.78 }
        : next.accepted_objects.length === 0
          ? suggestedRegion(next, definition)
          : null)
    if (!lockRegion) {
      setError('Перед принятием следующего объекта нужно выбрать его точную область на сцене.')
      return
    }
    return finalizeAccept(next, definition, lockRegion)
  }

  async function publishLatestIdea() {
    if (!latestAcceptedGenerationId || ideaPublishing) return
    setIdeaPublishing(true)
    setError(null)
    try {
      setIdeaPublication(ideaPublication?.owner_published
        ? await api.unpublishIdea(latestAcceptedGenerationId)
        : await api.publishIdea(latestAcceptedGenerationId))
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 409) {
        try {
          setIdeaPublication(await api.getOwnIdeaPublication(latestAcceptedGenerationId))
          return
        } catch { /* show the original conflict below */ }
      }
      setError(err instanceof Error ? err.message : 'Не удалось добавить работу в Идеи')
    } finally {
      setIdeaPublishing(false)
    }
  }

  const ideaPublishControl = latestAcceptedGenerationId ? <div className="questionnaire-idea-share">
    <p>Хотите показать эту работу другим? В ленту попадут только изображение и параметры проектирования — без данных заявки.</p>
    <button
      type="button"
      className="secondary-button questionnaire-wide"
      disabled={ideaPublishing || ideaPublication === undefined}
      onClick={() => void publishLatestIdea()}
    >
      {ideaPublishing ? 'Сохраняем…' : ideaPublication?.owner_published ? 'Убрать из Идей' : ideaPublication ? 'Вернуть в Идеи' : ideaPublication === undefined ? 'Проверяем публикацию…' : 'Добавить в Идеи'}
    </button>
  </div> : null

  if (error && (!catalog || !session)) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Опросник не открылся</h1><div className="banner-error">{error}</div><button className="secondary-button" onClick={onBack}>Назад</button></section></main>
  if (!catalog || !session) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Загружаем опросник…</h1></section></main>

  if (!session.source_step_completed) return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon /> Назад</button><strong>{project.name}</strong><span>Исходный кадр</span></header><section className="questionnaire-card"><span className="eyebrow">ОДИН РАЗ ДО ОПРОСА</span><h1>Загрузите фото участка</h1><p>Или продолжите без фотографии. Для следующих объектов будет использоваться последний принятый кадр.</p><input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload}/><button className="questionnaire-upload" disabled={busy} onClick={() => fileRef.current?.click()}><UploadIcon/><strong>Выбрать фото</strong><span>JPG, PNG или WebP</span></button><button className="secondary-button questionnaire-wide" disabled={busy} onClick={() => void setSource(null)}>Продолжить без фото</button>{error && <div className="banner-error">{error}</div>}</section></main>

  if (session.application_submitted) return <main className="questionnaire-shell"><section className="questionnaire-card finish-card"><SparkIcon/><span className="eyebrow">ГОТОВО</span><h1>Заявка отправлена</h1><p>Эскизы и ответы сохранены. Заявка отправляется администратору в Telegram.</p>{ideaPublishControl}<button className="primary-button" onClick={onBack}>Вернуться к проектам</button></section></main>



  if (!current) {
    if (session.initial_concept_mode && !session.initial_concept_accepted) {
      const remaining = session.selected_objects.filter((key) => !session.survey_completed_objects.includes(key))
      const ready = remaining.length === 0
      return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{initialGenerationId ? 'Общая концепция' : 'Опрос проекта'}</span></header><section className="questionnaire-card">
        <span className="eyebrow">{initialGenerationId ? 'ОДНА ГЕНЕРАЦИЯ' : ready ? 'ПРОВЕРЬТЕ ТЗ' : 'СОБИРАЕМ ОБЩЕЕ ТЗ'}</span>
        <h1>{initialGenerationId ? 'Общая концепция участка' : ready ? 'Всё готово к одной генерации' : 'Заполните параметры всех объектов'}</h1>
        <p>{initialGenerationId ? 'В одной визуализации собраны все объекты, выбранные до старта проекта.' : 'AuRoom сначала соберёт полное ТЗ по всем выбранным объектам и только потом сделает одну общую визуализацию участка.'}</p>
        {renderOutput && <div className="questionnaire-result"><img src={renderOutput.url} alt="Общая концепция участка"/></div>}
        {!initialGenerationId && <div className="questionnaire-options">{session.selected_objects.map((key) => <button key={key} className={`questionnaire-option ${session.survey_completed_objects.includes(key) ? 'selected' : ''}`} disabled={busy} onClick={() => void chooseObject(key)}><span>{session.survey_completed_objects.includes(key) ? '✓ ' : ''}{definitions.get(key)?.title || key}</span><i/></button>)}</div>}
        {ready && !initialGenerationId && <div className="questionnaire-answer-review">{session.selected_objects.map((key) => {
          const definition = definitions.get(key)
          const answers = session.answers[key] || {}
          if (!definition) return null
          const answered = definition.questions.filter((question) =>
            question.phase === 'pre_render'
            && answers[question.id] !== undefined
            && conditionOk(question.condition, answers, houseAccepted)
          )
          return <details key={key}><summary>{definition.title}</summary>{answered.map((question) => <button type="button" key={question.id} disabled={busy} onClick={() => void editInitialQuestion(key, question.id)}><span>{question.text}</span><strong>{text(answers[question.id])}</strong></button>)}</details>
        })}</div>}
        {ready && !initialGenerationId && <><p className="region-hint">Одна общая генерация · {generationCostLabel()}</p><div className="questionnaire-actions"><button className="primary-button" disabled={busy || generationCost?.is_available === false} onClick={() => void generateInitial(session)}>Создать общую концепцию</button></div></>}
        {initialGenerationId && renderOutput && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void acceptInitial()}>Принять концепцию</button><button className="secondary-button" disabled={busy} onClick={() => void reopenInitialAnswers()}>Изменить ТЗ · новая генерация</button></div>}
        {(busy || generationInFlight) && initialGenerationId && !renderOutput && <div className="empty-inline">Создаём весь участок одной генерацией…</div>}
        {error && <div className="banner-error">{error}</div>}
      </section></main>
    }
    const hasAccepted = session.accepted_objects.length > 0
    const remainingLegacy = session.selected_objects.filter((key) => !session.accepted_objects.includes(key))
    const availableToAdd = catalog.sections
      .flatMap((section) => section.object_keys)
      .filter((key) => !session.selected_objects.includes(key))
    return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{hasAccepted ? 'Что дальше?' : 'Выбор объекта'}</span></header><section className="questionnaire-card"><span className="eyebrow">{hasAccepted ? 'КОНЦЕПЦИЯ ПРИНЯТА' : 'НАЧАЛО ОПРОСА'}</span><h1>{hasAccepted ? 'Что делаем дальше?' : 'С чего начнём?'}</h1><p>{hasAccepted ? 'Любое изменение принятой концепции создаёт новую итерацию. Перед запуском вы увидите её стоимость.' : 'Выберите объект.'}</p>{!hasAccepted && remainingLegacy.length > 0 && <div className="questionnaire-options">{remainingLegacy.map((key) => <button key={key} className="questionnaire-option" disabled={busy} onClick={() => void chooseObject(key)}><span>{definitions.get(key)?.title || key}</span><i/></button>)}</div>}{hasAccepted && sceneAsset && <div className="questionnaire-result"><img src={sceneAsset.url} alt="Последний принятый эскиз"/></div>}{hasAccepted && session.initial_concept_mode && <p className="region-hint">Следующая генерация · {generationCostLabel()}</p>}{hasAccepted && session.initial_concept_mode && <div className="questionnaire-options">{session.accepted_objects.map((key) => <button key={key} className="questionnaire-option" disabled={busy || generationCost?.is_available === false} onClick={() => void startRefinement(key)}><span>Изменить: {definitions.get(key)?.title || key}</span><i/></button>)}</div>}{hasAccepted && session.initial_concept_mode && availableToAdd.length > 0 && <details className="idea-work-summary"><summary>Добавить новый объект</summary><div className="questionnaire-options">{availableToAdd.map((key) => <button key={key} className="questionnaire-option" disabled={busy || generationCost?.is_available === false} onClick={() => void addObject(key)}><span>{definitions.get(key)?.title || key}</span><i/></button>)}</div></details>}{hasAccepted && ideaPublishControl}{hasAccepted && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void chooseApplication()}>Перейти к заявке</button></div>}{error && <div className="banner-error">{error}</div>}</section></main>
  }

  if (session.region_mode === 'edit' && session.region_object) {
    const placementDefinition = definitions.get(session.region_object)
    const protectedRegions = session.accepted_objects
      .map((key) => ({ key, region:session.lock_regions[key] }))
      .filter((item):item is { key:string; region:NormalizedRect } => Boolean(item.region))
    return <main className="questionnaire-shell">
      <header className="questionnaire-topbar"><button className="back-button" disabled={busy} onClick={() => void cancelEditRegion()}><BackIcon/> Назад</button><strong>{project.name}</strong><span>Размещение</span></header>
      <section className="questionnaire-card region-picker-card">
        <span className="eyebrow">ТОЧНОЕ МЕСТО НА СЦЕНЕ</span>
        <h1>Где разместить: {placementDefinition?.title || session.region_object}?</h1>
        <p>Проведите пальцем или мышью по последнему принятому кадру и выделите прямоугольник, внутри которого можно менять или добавлять объект. Всё за пределами этой области compositor сохранит пиксельно.</p>
        <p className="region-hint">Новая итерация · {generationCostLabel()}</p>
        {session.initial_concept_accepted && session.accepted_objects.includes(session.region_object) && <div className="questionnaire-field"><label>Что изменить?<input value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="Например: перенести левее, сделать крышу тёмной"/></label></div>}
        {sceneAsset ? <div
          className="region-canvas"
          role="img"
          aria-label="Выбор области для нового объекта"
          onPointerDown={beginRegionSelection}
          onPointerMove={moveRegionSelection}
          onPointerUp={endRegionSelection}
          onPointerCancel={endRegionSelection}
        >
          <img src={sceneAsset.url} alt="Последний принятый кадр для размещения объекта"/>
          {protectedRegions.map(({key,region}) => <div
            key={key}
            className="region-protected"
            style={{
              left:`${region.x * 100}%`,
              top:`${region.y * 100}%`,
              width:`${region.width * 100}%`,
              height:`${region.height * 100}%`,
            }}
          />)}
          {regionDraft && <div
            className="region-selection"
            style={{
              left:`${regionDraft.x * 100}%`,
              top:`${regionDraft.y * 100}%`,
              width:`${regionDraft.width * 100}%`,
              height:`${regionDraft.height * 100}%`,
            }}
          ><span>ОБЛАСТЬ НОВОГО ОБЪЕКТА</span></div>}
        </div> : <div className="banner-error">Последний принятый кадр недоступен. Вернитесь в проект и откройте его заново.</div>}
        <p className="region-hint">Пунктиром показаны уже принятые объекты — их пиксели защищены. Если выделение неточное, просто проведите по изображению ещё раз.</p>
        {error && <div className="banner-error">{error}</div>}
        <div className="questionnaire-actions">
          <button className="secondary-button" disabled={busy} onClick={() => setRegionDraft(null)}>Очистить</button>
          <button className="primary-button" disabled={busy || !sceneAsset || !regionDraft || regionDraft.width < 0.03 || regionDraft.height < 0.03 || (session.initial_concept_accepted && session.accepted_objects.includes(session.region_object) && !reviewComment.trim())} onClick={() => void confirmEditRegion()}>Подтвердить область и создать новую итерацию</button>
        </div>
      </section>
    </main>
  }

  if ((busy || generationInFlight) && !active) return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{current.title}</span></header><section className="questionnaire-card generating-card"><SparkIcon/><h1>Создаём: {current.title}</h1><p>Сохраняем текущую сцену, ракурс и уже принятые объекты.</p>{error && <div className="banner-error">{error}</div>}</section></main>

  if (!active) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>{current.title}</h1><p>{currentGenerationId ? 'Генерация не завершена. Можно безопасно проверить текущую задачу и повторить только если она действительно завершилась ошибкой.' : 'Подготавливаем следующий шаг…'}</p>{error && <div className="banner-error">{error}</div>}{currentGenerationId && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void resumeOrRetryGeneration()}>Проверить генерацию</button></div>}</section></main>

  const options = availableOptions(active)
  const currentValue = objectAnswers[active.id]
  const canSkip = active.skip_default !== null && conditionOk(active.skip_condition, objectAnswers, houseAccepted)
  const review = active.phase === 'review'
  const refinement = current.key === 'eskez-doma' && active.id === '15б'
  const primaryReview = review && active.kind === 'single' && options[0]?.startsWith('Да') && options[1]?.startsWith('Нет')
  const multiCanContinue = multi.length > 0 || (refinement && Boolean(reviewComment.trim()))
  const hasCustomOption = options.includes('Свой вариант')
  const standardOptions = hasCustomOption ? options.filter((option) => option !== 'Свой вариант') : options
  const customStored = typeof currentValue === 'string' && currentValue.startsWith('Свой вариант:')
  const customInputIsNumber = active.min_value != null || active.max_value != null
  const numericDraft = Number(draft.replace(',', '.'))
  const numericDraftValid = Boolean(draft.trim())
    && !Number.isNaN(numericDraft)
    && (active.min_value == null || numericDraft >= active.min_value)
    && (active.max_value == null || numericDraft <= active.max_value)
  const customDraftValid = Boolean(draft.trim()) && (!customInputIsNumber || numericDraftValid)
  const activeTitle = active.text
  const textPlaceholder = active.placeholder || undefined

  return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={() => void previousQuestion()}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{current.title}</span></header><div className="questionnaire-layout"><aside className="questionnaire-progress"><span className="eyebrow">ВЫБРАНО</span>{session.selected_objects.map((key, index) => <div key={key} className={`questionnaire-progress-item ${session.accepted_objects.includes(key) ? 'done' : key === current.key ? 'current' : ''}`}><b>{session.accepted_objects.includes(key) ? '✓' : index + 1}</b><span>{definitions.get(key)?.title || key}</span></div>)}<div className={`questionnaire-progress-item ${current.key === 'zayavka' ? 'current' : ''}`}><b>✓</b><span>Заявка</span></div>{sourceAsset && <div className="questionnaire-source-mini"><ImageIcon/><span>Фото участка загружено</span></div>}</aside><section className="questionnaire-card question-card"><div className="questionnaire-question-head"><div><span className="eyebrow">{active.phase === 'application' ? 'ЗАЯВКА' : review ? 'ОЦЕНКА ЭСКИЗА' : current.title.toUpperCase()}</span><h1>{activeTitle}</h1></div>{canSkip && <span className="optional-badge">можно пропустить</span>}</div>{review && renderOutput && <div className="questionnaire-result"><img src={renderOutput.url} alt={`Эскиз ${current.title}`}/></div>}

  {!primaryReview && (active.kind === 'single' || (active.kind === 'number' && options.length > 0)) && <div className="questionnaire-options">{standardOptions.map((option) => <button key={option} className={`questionnaire-option ${!customOption && (String(currentValue) === option || draft === option) ? 'selected' : ''}`} onClick={() => {
    setCustomOption(false)
    if (active.kind === 'number') setDraft(option)
    else void answer(active, option)
  }}><span>{option}</span><i/></button>)}{hasCustomOption && <button className={`questionnaire-option ${customOption || customStored ? 'selected' : ''}`} onClick={() => {
    setCustomOption(true)
    setDraft(customStored && typeof currentValue === 'string' ? currentValue.slice('Свой вариант:'.length).trim() : '')
  }}><span>Свой вариант</span><i/></button>}</div>}
  {primaryReview && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void answer(active, options[0])}>Подходит</button><button className="secondary-button" disabled={busy} onClick={() => void answer(active, options[1])}>Уточнить</button></div>}
  {active.kind === 'multi' && <div className="questionnaire-options">{options.map((option) => <button key={option} className={`questionnaire-option ${multi.includes(option) ? 'selected' : ''}`} onClick={() => setMulti((items) => items.includes(option) ? items.filter((item) => item !== option) : active.max_selections && items.length >= active.max_selections ? items : [...items, option])}><span>{option}</span><i/></button>)}</div>}
  {refinement && <div className="questionnaire-field"><label>{active.field_hint || 'Свой комментарий'}<input value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="Опишите, что ещё нужно изменить"/></label></div>}
  {active.kind === 'single' && hasCustomOption && customOption && <div className="questionnaire-field"><label>{active.field_hint || 'Укажите свой вариант'}<input type={customInputIsNumber ? 'number' : 'text'} inputMode={customInputIsNumber ? 'decimal' : undefined} min={customInputIsNumber ? active.min_value ?? undefined : undefined} max={customInputIsNumber ? active.max_value ?? undefined : undefined} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={customInputIsNumber ? 'Введите значение' : 'Введите свой вариант'}/></label></div>}
  {active.kind === 'number' && <div className="questionnaire-field"><label>{active.field_hint || 'Введите значение'}<input type="number" inputMode="decimal" min={active.min_value ?? undefined} max={active.max_value ?? undefined} value={draft} onChange={(event) => { setCustomOption(hasCustomOption); setDraft(event.target.value) }}/></label></div>}
  {active.kind === 'text' && <div className="questionnaire-field"><label>{active.field_hint || activeTitle}<input value={draft} placeholder={textPlaceholder} onChange={(event) => setDraft(event.target.value)}/></label></div>}
  {active.kind === 'consent' && <label className="consent-row"><input type="checkbox" checked={currentValue === true} onChange={(event) => event.target.checked && void answer(active, true)}/><span>Согласен на обработку персональных данных</span></label>}
  {error && <div className="banner-error">{error}</div>}
  <div className="questionnaire-actions">{active.kind === 'multi' && <button className="primary-button" disabled={!multiCanContinue || busy} onClick={() => void answer(active, multi)}>Продолжить</button>}{active.kind === 'single' && hasCustomOption && customOption && <button className="primary-button" disabled={!customDraftValid || busy} onClick={() => void answer(active, `Свой вариант: ${draft.trim()}`)}>Продолжить</button>}{active.kind === 'number' && <button className="primary-button" disabled={!numericDraftValid || busy} onClick={() => void answer(active, numericDraft)}>Продолжить</button>}{active.kind === 'text' && <button className="primary-button" disabled={!draft.trim() || busy} onClick={() => void answer(active, draft.trim())}>Продолжить</button>}{canSkip && active.kind !== 'consent' && <button className="secondary-button" disabled={busy} onClick={() => void answer(active, active.skip_default ?? (active.kind === 'multi' ? [] : ''))}>Пропустить</button>}</div></section></div></main>
}
