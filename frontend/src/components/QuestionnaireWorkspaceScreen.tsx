import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
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
} from '../questionnaireTypes'
import type { Asset, Generation, GenerationMode, Project } from '../types'
import { BackIcon, ImageIcon, SparkIcon, UploadIcon } from './Icons'
import '../questionnaire.css'

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
    application_submitted:false,
  }
}

export function QuestionnaireWorkspaceScreen({ project, selectedObjects, onBack, onProjectChange }:{ project:Project; selectedObjects:string[]; onBack:()=>void; onProjectChange:(project:Project)=>void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [catalog, setCatalog] = useState<QuestionnaireCatalog|null>(null)
  const [session, setSession] = useState<DesignSession|null>(null)
  const [sourceAsset, setSourceAsset] = useState<Asset|null>(null)
  const [renderOutput, setRenderOutput] = useState<Asset|null>(null)
  const [draft, setDraft] = useState<string>('')
  const [multi, setMulti] = useState<string[]>([])
  const [reviewComment, setReviewComment] = useState<string>('')
  const [busy, setBusy] = useState(false)
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
        const initial = stored
          && stored.catalog_version === loaded.version
          && stored.selected_objects.join('|') === selected.join('|')
          ? stored
          : newSession(loaded.version, selected)
        setSession(initial)
        if (initial.source_asset_id) {
          try { setSourceAsset(await api.getAsset(initial.source_asset_id)) } catch { /* deleted source */ }
        }
        const previewKey = initial.current_object || initial.accepted_objects.at(-1) || null
        const generationId = previewKey ? initial.generation_ids[previewKey] : null
        if (generationId) {
          try {
            const generation = await api.getGeneration(generationId)
            if (generation.output_asset) setRenderOutput(generation.output_asset)
          } catch { /* stale generation */ }
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

  useEffect(() => {
    if (!session || !current || session.current_question_id) return
    const first = visible.find((q) => q.phase === (current.key === 'zayavka' ? 'application' : 'pre_render'))
    if (first && session.source_step_completed) void persist({ ...session, current_question_id:first.id })
  }, [session?.source_step_completed, current?.key])

  useEffect(() => {
    if (!active || !current || !session) return
    const value = objectAnswers[active.id]
    setDraft(typeof value === 'number' || typeof value === 'string' ? String(value) : '')
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
    if (saved) setSourceAsset(asset)
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
    const scene = next.scene_asset_id || next.source_asset_id
      ? 'Используй исходное изображение как текущую сцену. Сохрани существующий дом и все уже принятые объекты, их геометрию, пропорции, положение, окружение, ракурс и свет. Добавь или измени только текущий объект.'
      : definition.key === 'eskez-doma'
        ? 'Создай внешний вид дома на участке. Камера: дрон 40–50 м, сверху угловой вид.'
        : 'Создай объект на участке. Камера: дрон сверху, угловой вид.'
    return [
      `AuRoom. Точный опросник: ${definition.title}.`,
      scene,
      definition.key === 'eskez-doma'
        ? 'Планировок, комнат и внутренних помещений не придумывать.'
        : 'Если выбран «Как у дома», наследуй стиль, материалы и кровлю принятого дома.',
      ...lines,
      next.review_comments[definition.key] ? `Комментарий к уточнению: ${next.review_comments[definition.key]}` : '',
    ].filter(Boolean).join('\n')
  }

  async function poll(generation:Generation) {
    let currentGeneration = generation
    for (let i=0; i<90 && ['queued','processing'].includes(currentGeneration.status); i++) {
      await delay(2000)
      currentGeneration = await api.getGeneration(currentGeneration.id)
    }
    if (currentGeneration.status !== 'completed' || !currentGeneration.output_asset) {
      throw new Error(currentGeneration.error || 'Генерация не завершилась')
    }
    return currentGeneration
  }

  async function generate(next:DesignSession, definition:QuestionnaireDefinition) {
    setBusy(true)
    setError(null)
    setRenderOutput(null)
    try {
      const input = next.scene_asset_id || next.source_asset_id
      const mode:GenerationMode = definition.key === 'eskez-doma' && input ? 'facade' : 'master_plan'
      const generation = await poll(await api.createGeneration({
        project_id:project.id,
        input_asset_id:input,
        type:mode,
        prompt:prompt(definition, next),
      }))
      setRenderOutput(generation.output_asset)
      const review = definition.questions.find((q) => q.phase === 'review')
      await persist({
        ...next,
        generation_ids:{ ...next.generation_ids, [definition.key]:generation.id },
        current_question_id:review?.id || null,
      })
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 409) setError('Недостаточно кредитов. Пополните баланс в Профиле.')
      else setError(err instanceof Error ? err.message : 'Не удалось создать эскиз')
    } finally {
      setBusy(false)
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
      return generate({ ...next, current_question_id:null }, current)
    }

    if (question.phase === 'pre_render') {
      const questions = preQuestions(current, next)
      const index = questions.findIndex((q) => q.id === question.id)
      if (index < questions.length - 1) return persist({ ...next, current_question_id:questions[index + 1].id })
      return generate({ ...next, current_question_id:null }, current)
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
      if (!ids.length) return generate({ ...next, current_question_id:null }, current)
      return persist({ ...next, edit_question_ids:ids, current_question_id:ids[0] })
    }

    if (question.phase === 'review') {
      if (typeof value === 'string' && value.startsWith('Да')) return accept(next, current)
      const first = preQuestions(current, next)[0]
      return persist({ ...next, current_question_id:first?.id || null })
    }
  }

  async function accept(next:DesignSession, definition:QuestionnaireDefinition) {
    if (!renderOutput) {
      setError('Нет готового эскиза для принятия.')
      return
    }
    const accepted = next.accepted_objects.includes(definition.key)
      ? next.accepted_objects
      : [...next.accepted_objects, definition.key]
    await persist({
      ...next,
      accepted_objects:accepted,
      scene_asset_id:renderOutput.id,
      current_object:null,
      current_question_id:null,
      edit_question_ids:[],
    })
  }

  if (error && (!catalog || !session)) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Опросник не открылся</h1><div className="banner-error">{error}</div><button className="secondary-button" onClick={onBack}>Назад</button></section></main>
  if (!catalog || !session) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>Загружаем опросник…</h1></section></main>

  if (!session.source_step_completed) return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon /> Назад</button><strong>{project.name}</strong><span>Исходный кадр</span></header><section className="questionnaire-card"><span className="eyebrow">ОДИН РАЗ ДО ОПРОСА</span><h1>Загрузите фото участка</h1><p>Или продолжите без фотографии. Для следующих объектов будет использоваться последний принятый кадр.</p><input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload}/><button className="questionnaire-upload" disabled={busy} onClick={() => fileRef.current?.click()}><UploadIcon/><strong>Выбрать фото</strong><span>JPG, PNG или WebP</span></button><button className="secondary-button questionnaire-wide" disabled={busy} onClick={() => void setSource(null)}>Продолжить без фото</button>{error && <div className="banner-error">{error}</div>}</section></main>

  if (session.application_submitted) return <main className="questionnaire-shell"><section className="questionnaire-card finish-card"><SparkIcon/><span className="eyebrow">ГОТОВО</span><h1>Заявка отправлена</h1><p>Эскизы и ответы сохранены. Заявка отправляется администратору в Telegram.</p><button className="primary-button" onClick={onBack}>Вернуться к проектам</button></section></main>
  if (!current) {
    const remaining = session.selected_objects.filter((key) => !session.accepted_objects.includes(key))
    const hasAccepted = session.accepted_objects.length > 0
    return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{hasAccepted ? 'Что дальше?' : 'Выбор объекта'}</span></header><section className="questionnaire-card"><span className="eyebrow">{hasAccepted ? 'ЭСКИЗ ПРИНЯТ' : 'НАЧАЛО ОПРОСА'}</span><h1>{hasAccepted ? 'Что проектируем дальше?' : 'С чего начнём?'}</h1><p>{hasAccepted ? 'Принятый кадр зафиксирован. Выберите следующий объект или переходите к заявке.' : 'Вы выбрали несколько элементов. Выберите, какой опросник пройти первым.'}</p>{hasAccepted && renderOutput && <div className="questionnaire-result"><img src={renderOutput.url} alt="Последний принятый эскиз"/></div>}{remaining.length > 0 && <><div className="questionnaire-options">{remaining.map((key) => <button key={key} className="questionnaire-option" disabled={busy} onClick={() => void chooseObject(key)}><span>{definitions.get(key)?.title || key}</span><i/></button>)}</div></>}{hasAccepted && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void chooseApplication()}>Перейти к заявке</button></div>}{error && <div className="banner-error">{error}</div>}</section></main>
  }

  if (busy && !active) return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{current.title}</span></header><section className="questionnaire-card generating-card"><SparkIcon/><h1>Создаём: {current.title}</h1><p>Сохраняем текущую сцену, ракурс и уже принятые объекты.</p>{error && <div className="banner-error">{error}</div>}</section></main>

  if (!active) return <main className="questionnaire-shell"><section className="questionnaire-card"><h1>{current.title}</h1><p>Подготавливаем следующий шаг…</p>{error && <div className="banner-error">{error}</div>}</section></main>

  const options = availableOptions(active)
  const currentValue = objectAnswers[active.id]
  const canSkip = active.skip_default !== null && conditionOk(active.skip_condition, objectAnswers, houseAccepted)
  const review = active.phase === 'review'
  const refinement = current.key === 'eskez-doma' && active.id === '15б'
  const primaryReview = review && active.kind === 'single' && options[0]?.startsWith('Да') && options[1]?.startsWith('Нет')
  const multiCanContinue = multi.length > 0 || (refinement && Boolean(reviewComment.trim()))

  return <main className="questionnaire-shell"><header className="questionnaire-topbar"><button className="back-button" onClick={onBack}><BackIcon/> Назад</button><strong>{project.name}</strong><span>{current.title}</span></header><div className="questionnaire-layout"><aside className="questionnaire-progress"><span className="eyebrow">ВЫБРАНО</span>{session.selected_objects.map((key, index) => <div key={key} className={`questionnaire-progress-item ${session.accepted_objects.includes(key) ? 'done' : key === current.key ? 'current' : ''}`}><b>{session.accepted_objects.includes(key) ? '✓' : index + 1}</b><span>{definitions.get(key)?.title || key}</span></div>)}<div className={`questionnaire-progress-item ${current.key === 'zayavka' ? 'current' : ''}`}><b>✓</b><span>Заявка</span></div>{sourceAsset && <div className="questionnaire-source-mini"><ImageIcon/><span>Фото участка загружено</span></div>}</aside><section className="questionnaire-card question-card"><div className="questionnaire-question-head"><div><span className="eyebrow">{active.phase === 'application' ? 'ЗАЯВКА' : review ? 'ОЦЕНКА ЭСКИЗА' : current.title.toUpperCase()}</span><h1>{active.id}. {active.text}</h1></div>{canSkip && <span className="optional-badge">можно пропустить</span>}</div>{active.help && <p className="questionnaire-help">{active.help}</p>}{review && renderOutput && <div className="questionnaire-result"><img src={renderOutput.url} alt={`Эскиз ${current.title}`}/></div>}

  {!primaryReview && (active.kind === 'single' || (active.kind === 'number' && options.length > 0)) && <div className="questionnaire-options">{options.map((option) => <button key={option} className={`questionnaire-option ${String(currentValue) === option || draft === option ? 'selected' : ''}`} onClick={() => active.kind === 'number' ? setDraft(option) : void answer(active, option)}><span>{option}</span><i/></button>)}</div>}
  {primaryReview && <div className="questionnaire-actions"><button className="primary-button" disabled={busy} onClick={() => void answer(active, options[0])}>Подходит</button><button className="secondary-button" disabled={busy} onClick={() => void answer(active, options[1])}>Уточнить</button></div>}
  {active.kind === 'multi' && <div className="questionnaire-options">{options.map((option) => <button key={option} className={`questionnaire-option ${multi.includes(option) ? 'selected' : ''}`} onClick={() => setMulti((items) => items.includes(option) ? items.filter((item) => item !== option) : active.max_selections && items.length >= active.max_selections ? items : [...items, option])}><span>{option}</span><i/></button>)}</div>}
  {refinement && <div className="questionnaire-field"><label>{active.field_hint || 'Свой комментарий'}<input value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="Опишите, что ещё нужно изменить"/></label></div>}
  {active.kind === 'number' && <div className="questionnaire-field"><label>{active.field_hint || 'Введите значение'}<input type="number" inputMode="decimal" min={active.min_value ?? undefined} max={active.max_value ?? undefined} value={draft} onChange={(event) => setDraft(event.target.value)}/></label></div>}
  {active.kind === 'text' && <div className="questionnaire-field"><label>{active.field_hint || active.text}<input value={draft} onChange={(event) => setDraft(event.target.value)}/></label></div>}
  {active.kind === 'consent' && <label className="consent-row"><input type="checkbox" checked={currentValue === true} onChange={(event) => event.target.checked && void answer(active, true)}/><span>Согласен на обработку персональных данных</span></label>}
  {error && <div className="banner-error">{error}</div>}
  <div className="questionnaire-actions">{active.kind === 'multi' && <button className="primary-button" disabled={!multiCanContinue || busy} onClick={() => void answer(active, multi)}>Продолжить</button>}{active.kind === 'number' && <button className="primary-button" disabled={!draft || Number.isNaN(Number(draft)) || busy} onClick={() => void answer(active, Number(draft))}>Продолжить</button>}{active.kind === 'text' && <button className="primary-button" disabled={!draft.trim() || busy} onClick={() => void answer(active, draft.trim())}>Продолжить</button>}{canSkip && active.kind !== 'consent' && <button className="secondary-button" disabled={busy} onClick={() => void answer(active, active.skip_default ?? (active.kind === 'multi' ? [] : ''))}>Пропустить</button>}</div></section></div></main>
}
