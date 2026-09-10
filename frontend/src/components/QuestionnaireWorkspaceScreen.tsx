import { useEffect, useMemo, useRef, useState, type ChangeEvent, type PointerEvent as ReactPointerEvent } from 'react'
import * as api from '../api'
import {
  getQuestionnaireCatalog,
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
  QuestionnaireQuestion,
  NormalizedRect,
} from '../questionnaireTypes'
import type { Asset, Generation, GenerationMode, Project } from '../types'
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
  return true
}

function newSession(version:string, selected:string[]):DesignSession {
  return {
    session_id:crypto.randomUUID(),
    catalog_version:version,
    selected_objects:selected,
    current_object:selected.length === 1 ? selected[0] : null,
    current_question_id:null,
    source_step_completed:false,
    source_asset_id:null,
    scene_asset_id:null,
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
  const [sourceAsset, setSourceAsset] = useState<Asset|null>(null)
  const [sceneAsset, setSceneAsset] = useState<Asset|null>(null)
  const [renderOutput, setRenderOutput] = useState<Asset|null>(null)
  const [draft, setDraft] = useState<string>('')
  const [multi, setMulti] = useState<string[]>([])
  const [reviewComment, setReviewComment] = useState<string>('')
  const [customOption, setCustomOption] = useState(false)
  const [busy, setBusy] = useState(false)
  const [generationInFlight, setGenerationInFlight] = useState(false)
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

  const definitions = useMemo(() => new Map((catalog?.questionnaires || []).map((item) => [item.key, item])), [catalog])
  const current = session?.current_object ? definitions.get(session.current_object) || null : null
  const houseAccepted = session?.accepted_objects.includes('eskez-doma') || false
  const objectAnswers = current && session ? session.answers[current.key] || {} : {}
  const visible = current ? current.questions.filter((q) => conditionOk(q.condition, objectAnswers, houseAccepted)) : []
  const active = current && session ? visible.find((q) => q.id === session.current_question_id) || null : null
  const currentGenerationId = current && session ? session.generation_ids[current.key] || null : null

  useEffect(() => {
    if (!session || !current || session.current_question_id || session.region_mode || generationInFlight) return
    if (current.key !== 'zayavka' && currentGenerationId) return
    const first = visible.find((q) => q.phase === (current.key === 'zayavka' ? 'application' : 'pre_render'))
    if (first && session.source_step_completed) void persist({ ...session, current_question_id:first.id })
  }, [session?.source_step_completed, current?.key, currentGenerationId, generationInFlight])

  useEffect(() => {
    if (!session || !current || current.key === 'zayavka' || !currentGenerationId || generationInFlight) return
    let stopped = false
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        const generation = await api.getGeneration(currentGenerationId)
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

  async function chooseObject(key:string) {
    if (!session || session.accepted_objects.includes(key) || !session.selected_objects.includes(key)) return
    const definition = definitions.get(key)
    if (!definition) return
    const next = { ...session, current_object:key, current_question_id:null, edit_question_ids:[] }
    const first = preQuestions(definition, next)[0]
    await persist({ ...next, current_question_id:first?.id || null })
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

  function prompt(definition:QuestionnaireDefinition, next:DesignSession) {
    const answers = next.answers[definition.key] || {}
    const lines = preQuestions(definition, next)
      .map((q) => answers[q.id] == null || text(answers[q.id]) === '' ? null : `${q.id}. ${q.text} — ${text(answers[q.id])}`)
      .filter(Boolean)
    const scene = next.accepted_objects.length > 0 && next.scene_asset_id
      ? 'Используй исходное изображение как текущую принятую сцену. Сохрани существующий дом и все уже принятые объекты, их геометрию, пропорции, положение, окружение, ракурс и свет. Добавь или измени только текущий объект.'
      : next.source_asset_id
        ? 'Используй фотографию участка как исходный контекст. Сохрани геометрию участка, перспективу, ракурс и существующее окружение. Создай или добавь только текущий проектируемый объект.'
        : definition.key === 'eskez-doma'
          ? 'Создай внешний вид дома на участке. Камера: дрон 40–50 м, сверху угловой вид.'
          : 'Создай объект на участке. Камера: дрон сверху, угловой вид.'
    const region = next.edit_regions[definition.key]
    const regionInstruction = region
      ? `Новый объект и все новые пиксели должны находиться внутри разрешённой области кадра: слева ${Math.round(region.x*100)}%, сверху ${Math.round(region.y*100)}%, ширина ${Math.round(region.width*100)}%, высота ${Math.round(region.height*100)}%. За пределами этой области ничего не менять.`
      : ''
    return [
      `AuRoom. Точный опросник: ${definition.title}.`,
      scene,
      regionInstruction,
      definition.key === 'eskez-doma'
        ? 'Планировок, комнат и внутренних помещений не придумывать.'
        : 'Если выбран «Как у дома», наследуй стиль, материалы и кровлю принятого дома.',
      ...lines,
      next.review_comments[definition.key] ? `Комментарий к уточнению: ${next.review_comments[definition.key]}` : '',
    ].filter(Boolean).join('\n')
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
      return persist({ ...next, current_question_id:null, region_mode:'edit', region_object:definition.key })
    }
    setGenerationInFlight(true)
    const staged = await persist({ ...next, current_question_id:null, region_mode:null, region_object:null })
    if (!staged) {
      setGenerationInFlight(false)
      return null
    }
    return generate(staged, definition)
  }

  async function poll(generation:Generation) {
    let currentGeneration = generation
    const deadline = Date.now() + 6 * 60 * 1000
    let transientErrors = 0
    while (['queued','processing'].includes(currentGeneration.status) && Date.now() < deadline) {
      await delay(2000)
      try {
        currentGeneration = await api.getGeneration(currentGeneration.id)
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

  async function generate(next:DesignSession, definition:QuestionnaireDefinition) {
    setGenerationInFlight(true)
    setBusy(true)
    setError(null)
    setRenderOutput(null)
    try {
      const input = next.scene_asset_id || next.source_asset_id
      const mode:GenerationMode = definition.key === 'eskez-doma' && input ? 'facade' : 'master_plan'
      const editRegion = next.edit_regions[definition.key] || null
      const masked = Boolean(input && next.accepted_objects.length > 0 && editRegion)
      const protectedRegions = next.accepted_objects
        .map((key) => next.lock_regions[key])
        .filter((region):region is NormalizedRect => Boolean(region))
      const queued = await api.createGeneration({
        project_id:project.id,
        input_asset_id:input,
        type:mode,
        prompt:prompt(definition, next),
        composition_mode:masked ? 'masked_edit' : 'replace',
        edit_region:masked ? editRegion : null,
        protected_regions:masked ? protectedRegions : [],
      })
      const queuedState = {
        ...next,
        generation_ids:{ ...next.generation_ids, [definition.key]:queued.id },
      }
      let saved = await persist(queuedState)
      if (!saved) {
        await delay(750)
        saved = await persist(queuedState)
      }
      if (!saved) throw new Error('Задача создана, но не удалось сохранить её номер. Откройте проект повторно.')

      const generation = await poll(queued)
      setRenderOutput(generation.output_asset)
      const review = definition.questions.find((q) => q.phase === 'review')
      await persist({
        ...saved,
        current_question_id:review?.id || null,
      })
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 409) setError('Недостаточно кредитов. Пополните баланс в Профиле.')
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
      const existing = await api.getGeneration(generationId)
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

  async function answer(question:QuestionnaireQuestion, value:QuestionnaireAnswer) {
    if (!session || !current) return
    const base = current.key === 'eskez-doma' && question.id === '15б'
      ? { ...session, review_comments:{ ...session.review_comments, [current.key]:reviewComment.trim() } }
      : session
    const nextAnswers = {
      ...base.answers,
      [current.key]:{ ...(base.answers[current.key] || {}), [question.id]:value },
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
      return startGenerationOrRegion({ ...next, current_question_id:null }, current)
    }

    if (current.key === 'eskez-doma' && question.id === '15') {
      if (typeof value === 'string' && value.startsWith('Да')) return accept(next, current)
      const q = current.questions.find((item) => item.id === '15а')
      return persist({ ...next, current_question_id:q?.id || null })
    }
    if (current.key === 'eskez-doma' && question.id === '15а') {
      if (typeof value === 'string' && value.startsWith('Всё')) {
        const first = preQuestions(current, next)[0]
        return persist({ ...next, current_question_id:first?.id || null, edit_question_ids:[] })
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
      const first = preQuestions(current, next)[0]
      return persist({ ...next, current_question_id:first?.id || null })
    }
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
    const lockRegion = next.lock_regions[definition.key] || next.edit_regions[definition.key]
    if (!lockRegion) {
      return persist({ ...next, current_question_id:null, region_mode:'lock', region_object:definition.key })
    }
    return finalizeAccept(next, definition, lockRegion)
  }

  async function confirmRegion(region:NormalizedRect) {
    if (!session || !session.region_mode || !session.region_object) return
    const objectKey = session.region_object
    const definition = definitions.get(objectKey)
    if (!definition) return
    if (session.region_mode === 'edit') {
      const staged:DesignSession = {
        ...session,
        edit_regions:{ ...session.edit_regions, [objectKey]:region },
        region_mode:'edit',
        region_object:objectKey,
      }
      const saved = await persist(staged)
      if (saved) await startGenerationOrRegion({ ...saved, region_mode:null, region_object:null }, definition)
      return
    }
    const next:DesignSession = {
      ...session,
      lock_regions:{ ...session.lock_regions, [objectKey]:region },
      region_mode:null,
      region_object:null,
    }
    await finalizeAccept(next, definition, region)
  }

  async function confirmLegacyLock(objectKey:string, region:NormalizedRect) {
    if (!session) return
    await persist({ ...session, lock_regions:{ ...session.lock_regions, [objectKey]:region } })
  }

  if (error && (!catalog || !session)) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Опросник не открылся</h1><div className="banner-error">{error}</div><button className="secondary-button" onClick={onBack}>Назад</button></section></main>
  if (!catalog || !session) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Загружаем опросник…</h1></section></main>

  if (!session.source_step_completed) return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon /> Назад</button><strong>{project.name}</strong><span>Исходный кадр</span></header><section className="questionnaire-card"><span className="eyebrow">ОДИН РАЗ ДО ОПРОСА</span><h1>Загрузите фото участка</h1><p>Или продолжите без фотографии. Для следующих объектов будет использоваться последний принятый кадр.</p><input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload}/><button className="questionnaire-upload" disabled={busy} onClick={() => fileRef.current?.click()}><UploadIcon/><strong>Выбрать фото</strong><span>JPG, PNG или WebP</span></button><button className="secondary-button questionnaire-wide" disabled={busy} onClick={() => void setSource(null)}>Продолжить без фото</button>{error && <div className="banner-error">{error}</div>}</section></main>

  if (session.application_submitted) return <main className="questionnaire-shell"><section className="questionnaire-card finish-card"><SparkIcon/><span className="eyebrow">ГОТОВО</span><h1>Заявка отправлена</h1><p>Эскизы и ответы сохранены. Заявка отправляется администратору в Telegram.</p><button className="primary-button" onClick={onBack}>Вернуться к проектам</button></section></main>

  if (session.region_mode && session.region_object) {
    const regionDefinition = definitions.get(session.region_object)
    const regionImage = session.region_mode === 'edit' ? sceneAsset : renderOutput
    if (regionDefinition && regionImage) {
      const initial = session.region_mode === 'edit'
        ? session.edit_regions[regionDefinition.key] || suggestedRegion(session, regionDefinition)
        : session.lock_regions[regionDefinition.key] || { x:0.12, y:0.10, width:0.76, height:0.78 }
      const protectedRegions = session.region_mode === 'edit'
        ? session.accepted_objects.map((key) => session.lock_regions[key]).filter((region):region is NormalizedRect => Boolean(region))
        : []
      return <RegionPicker
        projectName={project.name}
        image={regionImage}
        title={regionDefinition.title}
        mode={session.region_mode}
        initial={initial}
        protectedRegions={protectedRegions}
        busy={busy}
        error={error}
        onBack={onBack}
        onConfirm={(region) => void confirmRegion(region)}
      />
    }
  }

  if (!current) {
    const remaining = session.selected_objects.filter((key) => !session.accepted_objects.includes(key))
    const hasAccepted = session.accepted_objects.length > 0
    const missingLock = session.accepted_objects.find((key) => !session.lock_regions[key]) || null
    if (missingLock && sceneAsset) {
      return <RegionPicker
        projectName={project.name}
        image={sceneAsset}
        title={definitions.get(missingLock)?.title || missingLock}
        mode="lock"
        initial={{ x:0.12, y:0.10, width:0.76, height:0.78 }}
        protectedRegions={[]}
        busy={busy}
        error={error}
        onBack={onBack}
        onConfirm={(region) => void confirmLegacyLock(missingLock, region)}
      />
    }
    return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{hasAccepted ? 'Что дальше?' : 'Выбор объекта'}</span></header><section className="questionnaire-card"><span className="eyebrow">{hasAccepted ? 'ЭСКИЗ ПРИНЯТ' : 'НАЧАЛО ОПРОСА'}</span><h1>{hasAccepted ? 'Что проектируем дальше?' : 'С чего начнём?'}</h1><p>{hasAccepted ? 'Принятый кадр зафиксирован. Выберите следующий объект или переходите к заявке.' : 'Вы выбрали несколько элементов. Выберите, какой опросник пройти первым.'}</p>{hasAccepted && sceneAsset && <div className="questionnaire-result"><img src={sceneAsset.url} alt="Последний принятый эскиз"/></div>}{remaining.length > 0 && <div className="questionnaire-options">{remaining.map((key) => <button key={key} className="questionnaire-option" disabled={busy} onClick={() => void chooseObject(key)}><span>{definitions.get(key)?.title || key}</span><i/></button>)}</div>}{hasAccepted && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void chooseApplication()}>Перейти к заявке</button></div>}{error && <div className="banner-error">{error}</div>}</section></main>
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

  return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{current.title}</span></header><div className="questionnaire-layout"><aside className="questionnaire-progress"><span className="eyebrow">ВЫБРАНО</span>{session.selected_objects.map((key, index) => <div key={key} className={`questionnaire-progress-item ${session.accepted_objects.includes(key) ? 'done' : key === current.key ? 'current' : ''}`}><b>{session.accepted_objects.includes(key) ? '✓' : index + 1}</b><span>{definitions.get(key)?.title || key}</span></div>)}<div className={`questionnaire-progress-item ${current.key === 'zayavka' ? 'current' : ''}`}><b>✓</b><span>Заявка</span></div>{sourceAsset && <div className="questionnaire-source-mini"><ImageIcon/><span>Фото участка загружено</span></div>}</aside><section className="questionnaire-card question-card"><div className="questionnaire-question-head"><div><span className="eyebrow">{active.phase === 'application' ? 'ЗАЯВКА' : review ? 'ОЦЕНКА ЭСКИЗА' : current.title.toUpperCase()}</span><h1>{active.id}. {active.text}</h1></div>{canSkip && <span className="optional-badge">можно пропустить</span>}</div>{active.help && <p className="questionnaire-help">{active.help}</p>}{review && renderOutput && <div className="questionnaire-result"><img src={renderOutput.url} alt={`Эскиз ${current.title}`}/></div>}

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
  {active.kind === 'text' && <div className="questionnaire-field"><label>{active.field_hint || active.text}<input value={draft} onChange={(event) => setDraft(event.target.value)}/></label></div>}
  {active.kind === 'consent' && <label className="consent-row"><input type="checkbox" checked={currentValue === true} onChange={(event) => event.target.checked && void answer(active, true)}/><span>Согласен на обработку персональных данных</span></label>}
  {error && <div className="banner-error">{error}</div>}
  <div className="questionnaire-actions">{active.kind === 'multi' && <button className="primary-button" disabled={!multiCanContinue || busy} onClick={() => void answer(active, multi)}>Продолжить</button>}{active.kind === 'single' && hasCustomOption && customOption && <button className="primary-button" disabled={!customDraftValid || busy} onClick={() => void answer(active, `Свой вариант: ${draft.trim()}`)}>Продолжить</button>}{active.kind === 'number' && <button className="primary-button" disabled={!numericDraftValid || busy} onClick={() => void answer(active, numericDraft)}>Продолжить</button>}{active.kind === 'text' && <button className="primary-button" disabled={!draft.trim() || busy} onClick={() => void answer(active, draft.trim())}>Продолжить</button>}{canSkip && active.kind !== 'consent' && <button className="secondary-button" disabled={busy} onClick={() => void answer(active, active.skip_default ?? (active.kind === 'multi' ? [] : ''))}>Пропустить</button>}</div></section></div></main>
}


function RegionPicker({ projectName, image, title, mode, initial, protectedRegions, busy, error, onBack, onConfirm }:{
  projectName:string
  image:Asset
  title:string
  mode:'edit'|'lock'
  initial:NormalizedRect
  protectedRegions:NormalizedRect[]
  busy:boolean
  error:string|null
  onBack:()=>void
  onConfirm:(region:NormalizedRect)=>void
}) {
  const [region, setRegion] = useState<NormalizedRect>(initial)
  const dragStart = useRef<{x:number;y:number}|null>(null)

  function point(event:ReactPointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      x:Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y:Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    }
  }

  function updateRegion(start:{x:number;y:number}, end:{x:number;y:number}) {
    const x = Math.min(start.x, end.x)
    const y = Math.min(start.y, end.y)
    const width = Math.max(0.01, Math.abs(end.x - start.x))
    const height = Math.max(0.01, Math.abs(end.y - start.y))
    setRegion({ x, y, width:Math.min(width, 1-x), height:Math.min(height, 1-y) })
  }

  function pointerDown(event:ReactPointerEvent<HTMLDivElement>) {
    const start = point(event)
    dragStart.current = start
    event.currentTarget.setPointerCapture(event.pointerId)
    setRegion({ x:start.x, y:start.y, width:0.01, height:0.01 })
  }

  function pointerMove(event:ReactPointerEvent<HTMLDivElement>) {
    if (!dragStart.current) return
    updateRegion(dragStart.current, point(event))
  }

  function pointerUp(event:ReactPointerEvent<HTMLDivElement>) {
    if (dragStart.current) updateRegion(dragStart.current, point(event))
    dragStart.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }

  const valid = region.width >= 0.04 && region.height >= 0.04
  return <main className="questionnaire-shell">
    <header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{projectName}</strong><span>Защита кадра</span></header>
    <section className="questionnaire-card region-picker-card">
      <span className="eyebrow">ПИКСЕЛЬНАЯ ФИКСАЦИЯ</span>
      <h1>{mode === 'edit' ? `Где добавить: ${title}?` : `Зафиксируйте: ${title}`}</h1>
      <p>{mode === 'edit'
        ? 'Проведите пальцем по кадру и выделите прямоугольник, внутри которого ИИ имеет право менять изображение. Всё снаружи останется пиксель-в-пиксель как в принятом кадре.'
        : 'Обведите принятый объект целиком, включая важные тени и примыкания. Эта область станет защищённой и не сможет быть перерисована следующими генерациями.'}</p>
      <div className="region-canvas" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp}>
        <img src={image.url} alt={title}/>
        {protectedRegions.map((item, index) => <div key={index} className="region-protected" style={{ left:`${item.x*100}%`, top:`${item.y*100}%`, width:`${item.width*100}%`, height:`${item.height*100}%` }}/>) }
        <div className={`region-selection ${mode}`} style={{ left:`${region.x*100}%`, top:`${region.y*100}%`, width:`${region.width*100}%`, height:`${region.height*100}%` }}><span>{mode === 'edit' ? 'МОЖНО МЕНЯТЬ' : 'ЗАЩИТИТЬ'}</span></div>
      </div>
      <p className="region-hint">Можно провести по изображению ещё раз, чтобы изменить область. Защищённые зоны отмечены штриховкой и всегда имеют приоритет.</p>
      {error && <div className="banner-error">{error}</div>}
      <div className="questionnaire-actions"><button className="primary-button" disabled={!valid || busy} onClick={() => onConfirm(region)}>{mode === 'edit' ? 'Использовать эту область' : 'Зафиксировать область'}</button></div>
    </section>
  </main>
}
