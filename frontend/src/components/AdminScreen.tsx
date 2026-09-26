import { useEffect, useMemo, useState, type FormEvent } from 'react'
import * as api from '../api'
import type { AdminQuestionnaireCatalog, QuestionnaireApplication, QuestionnaireCatalog, QuestionnaireSourceText } from '../questionnaireTypes'
import type {
  AdminAiHistoryItem,
  AdminAudit,
  AdminBillingSettings,
  AdminBroadcast,
  AdminCreditTransaction,
  AdminGenerationPrice,
  AdminGenerationSettings,
  AdminIdea,
  AdminOverview,
  AdminOperationalSettings,
  AdminPayment,
  AdminPrompt,
  AdminTariff,
  AdminTelegramContent,
  AdminUser,
  BroadcastSegment,
  Generation,
  GenerationMode,
  UserRole,
} from '../types'

const modes: { id: GenerationMode; label: string }[] = [
  { id: 'floor_plan', label: 'Планировка' },
  { id: 'facade', label: 'Фасад' },
  { id: 'master_plan', label: 'Мастер-план' },
  { id: 'interior', label: 'Интерьер' },
]

type Tab = 'tariffs' | 'ideas' | 'applications' | 'questionnaires' | 'generation' | 'users' | 'payments' | 'broadcasts' | 'telegram' | 'system' | 'audit'

function initialAdminTab(): Tab {
  const params = new URLSearchParams(window.location.search)
  if (params.get('application')) return 'applications'
  if (params.get('user')) return 'users'
  return 'tariffs'
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Не удалось выполнить операцию'
}

function formatMoney(amount: string, currency: string) {
  return `${Number(amount).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${currency}`
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`admin-provider-status ${ok ? 'ok' : 'off'}`}><i />{label}: {ok ? 'настроен' : 'не настроен'}</span>
}

export function AdminScreen({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>(initialAdminTab)
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [tariffs, setTariffs] = useState<AdminTariff[]>([])
  const [billingSettings, setBillingSettings] = useState<AdminBillingSettings | null>(null)
  const [ideas, setIdeas] = useState<AdminIdea[]>([])
  const [applications, setApplications] = useState<QuestionnaireApplication[]>([])
  const [questionnaireCatalog, setQuestionnaireCatalog] = useState<AdminQuestionnaireCatalog | null>(null)
  const [generation, setGeneration] = useState<AdminGenerationSettings | null>(null)
  const [prices, setPrices] = useState<AdminGenerationPrice[]>([])
  const [prompts, setPrompts] = useState<AdminPrompt[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [transactions, setTransactions] = useState<AdminCreditTransaction[]>([])
  const [payments, setPayments] = useState<AdminPayment[]>([])
  const [broadcasts, setBroadcasts] = useState<AdminBroadcast[]>([])
  const [operations, setOperations] = useState<AdminOperationalSettings | null>(null)
  const [telegramContent, setTelegramContent] = useState<AdminTelegramContent | null>(null)
  const [audit, setAudit] = useState<AdminAudit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    setLoading(true)
    setError(null)
    try {
      const [o, t, bs, i, apps, qc, g, gp, p, u, tx, pay, b, tg, ops, a] = await Promise.all([
        api.adminOverview(),
        api.adminListTariffs(),
        api.adminGetBillingSettings(),
        api.adminListIdeas(),
        api.adminListQuestionnaireApplications(),
        api.adminGetQuestionnaireCatalog(),
        api.adminGetGenerationSettings(),
        api.adminListGenerationPrices(),
        api.adminListPrompts(),
        api.adminListUsers(),
        api.adminListCreditTransactions(),
        api.adminListPayments(),
        api.adminListBroadcasts(),
        api.adminGetTelegramContent(),
        api.adminGetOperationalSettings(),
        api.adminListAudit(),
      ])
      setOverview(o)
      setTariffs(t)
      setBillingSettings(bs)
      setIdeas(i)
      setApplications(apps)
      setQuestionnaireCatalog(qc)
      setGeneration(g)
      setPrices(gp)
      setPrompts(p)
      setUsers(u)
      setTransactions(tx)
      setPayments(pay)
      setBroadcasts(b)
      setTelegramContent(tg)
      setOperations(ops)
      setAudit(a)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void reload() }, [])

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div><span className="eyebrow">AUROOM CONTROL PLANE</span><h1>Веб-админка</h1><p>Тарифы, экономика, AI, контент и операционные действия — без правок кода.</p></div>
        <div className="admin-header-actions"><button className="secondary-button" disabled={loading} onClick={() => void reload()}>{loading ? 'Обновляем…' : 'Обновить'}</button><button className="secondary-button" onClick={onClose}>← В приложение</button></div>
      </header>
      {overview && <div className="admin-provider-row"><StatusDot ok={overview.yookassa_configured} label="YooKassa"/><StatusDot ok={overview.nexus_configured} label="Nexus"/><StatusDot ok={overview.telegram_configured} label="Telegram"/></div>}
      {error && <div className="banner-error" role="alert"><span>{error}</span><span className="banner-actions"><button type="button" onClick={() => void reload()}>Повторить</button><button type="button" onClick={() => setError(null)}>Закрыть</button></span></div>}
      <nav className="admin-tabs">
        {([
          ['tariffs','Тарифы и касса'], ['ideas','Идеи'], ['applications','Заявки'], ['questionnaires','Опросники'], ['generation','AI и стоимость'], ['users','Пользователи и кредиты'],
          ['payments','Платежи'], ['broadcasts','Рассылки'], ['telegram','Telegram'], ['system','Система'], ['audit','Аудит'],
        ] as [Tab,string][]).map(([id,label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      {loading ? <div className="admin-loading">Загружаем настройки…</div> : (
        <div className="admin-content">
          {tab === 'tariffs' && billingSettings && <TariffsPanel items={tariffs} onItems={setTariffs} billingSettings={billingSettings} onBillingSettings={setBillingSettings} onError={setError} />}
          {tab === 'ideas' && <IdeasPanel items={ideas} onItems={setIdeas} onError={setError} />}
          {tab === 'applications' && <ApplicationsPanel items={applications} focusId={new URLSearchParams(window.location.search).get('application')} onItems={setApplications} onError={setError} />}
          {tab === 'questionnaires' && questionnaireCatalog && <QuestionnaireCatalogPanel settings={questionnaireCatalog} onSaved={setQuestionnaireCatalog} onError={setError} />}
          {tab === 'generation' && generation && <GenerationPanel settings={generation} prices={prices} prompts={prompts} onSettings={setGeneration} onPrices={setPrices} onPrompts={setPrompts} onError={setError} />}
          {tab === 'users' && <UsersPanel items={users} transactions={transactions} onItems={setUsers} onTransactions={setTransactions} onError={setError} focusUserId={new URLSearchParams(window.location.search).get('user')} />}
          {tab === 'payments' && <PaymentsPanel items={payments} onItems={setPayments} onError={setError} />}
          {tab === 'broadcasts' && <BroadcastsPanel items={broadcasts} onItems={setBroadcasts} onError={setError} />}
          {tab === 'telegram' && telegramContent && <TelegramContentPanel settings={telegramContent} onSaved={setTelegramContent} onError={setError} />}
          {tab === 'system' && operations && <OperationsPanel settings={operations} onSaved={setOperations} onError={setError} />}
          {tab === 'audit' && <AuditPanel items={audit} />}
        </div>
      )}
    </main>
  )
}

function applicationAnswer(value: unknown) {
  if (Array.isArray(value)) return value.join(', ')
  if (value === true) return 'Да'
  if (value === false) return 'Нет'
  if (value == null || value === '') return '—'
  return String(value)
}

function QuestionnaireCatalogPanel({ settings, onSaved, onError }: { settings: AdminQuestionnaireCatalog; onSaved:(value:AdminQuestionnaireCatalog)=>void; onError:(value:string|null)=>void }) {
  const [version,setVersion]=useState(settings.catalog.version)
  const [catalogJson,setCatalogJson]=useState(JSON.stringify(settings.catalog,null,2))
  const [sourcesJson,setSourcesJson]=useState(JSON.stringify(settings.source_texts,null,2))
  const [busy,setBusy]=useState(false)

  useEffect(()=>{
    setVersion(settings.catalog.version)
    setCatalogJson(JSON.stringify(settings.catalog,null,2))
    setSourcesJson(JSON.stringify(settings.source_texts,null,2))
  },[settings.updated_at])

  async function save(){
    const nextVersion=version.trim()
    if(!nextVersion){onError('Укажите новую версию каталога');return}
    setBusy(true);onError(null)
    try{
      const parsedCatalog=JSON.parse(catalogJson) as QuestionnaireCatalog
      const parsedSources=JSON.parse(sourcesJson) as Record<string,QuestionnaireSourceText>
      if(!parsedCatalog||Array.isArray(parsedCatalog)||typeof parsedCatalog!=='object') throw new Error('Catalog должен быть JSON-объектом')
      if(!parsedSources||Array.isArray(parsedSources)||typeof parsedSources!=='object') throw new Error('Source texts должны быть JSON-объектом')
      const saved=await api.adminUpdateQuestionnaireCatalog({
        catalog:{...parsedCatalog,version:nextVersion},
        source_texts:parsedSources,
      })
      onSaved(saved)
    }catch(err){onError(errorText(err))}
    finally{setBusy(false)}
  }

  return <section className="admin-panel">
    <div className="admin-panel-title"><div><h2>Опросники</h2><p>Текущий каталог хранится в PostgreSQL. Каждое изменение публикуется только с новой версией; уже начатые проекты продолжают использовать свою неизменяемую revision.</p></div><span className="status-pill">{settings.catalog.questionnaires.length} опросников · {settings.catalog.sections.length} разделов</span></div>
    <div className="admin-form-grid">
      <label className="admin-span-2">Новая версия каталога<input value={version} onChange={e=>setVersion(e.target.value)} placeholder="2026-09-14.1"/><small>Нельзя повторно использовать уже существовавшую версию.</small></label>
      <label className="admin-span-2">Catalog JSON<textarea className="admin-code" value={catalogJson} onChange={e=>setCatalogJson(e.target.value)} /><small>Разделы, порядок объектов, вопросы, варианты, условия, зависимости, scene policy и правила редактирования.</small></label>
      <label className="admin-span-2">Исходные тексты опросников JSON<textarea className="admin-code" value={sourcesJson} onChange={e=>setSourcesJson(e.target.value)} /><small>Ключи должны точно совпадать с questionnaire key, а filename — с source_file соответствующего опросника.</small></label>
      <div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy||!version.trim()} onClick={()=>void save()}>{busy?'Публикуем…':'Опубликовать новую версию'}</button></div>
    </div>
    <div className="admin-subpanel"><p><strong>Важно:</strong> сервер валидирует структуру и сохраняет предыдущую версию в истории. Изменения применяются только к новым/незавершённым сессиям согласно version contract.</p><small>Последнее изменение: {formatDate(settings.updated_at)}</small></div>
  </section>
}

function ApplicationsPanel({ items, focusId, onItems, onError }: { items: QuestionnaireApplication[]; focusId:string|null; onItems:(items:QuestionnaireApplication[])=>void; onError:(value:string|null)=>void }) {
  const [expanded, setExpanded] = useState<string | null>(focusId || items[0]?.id || null)
  const [retrying, setRetrying] = useState<string | null>(null)

  function deliveryLabel(status:string) {
    if (status === 'sent') return 'Telegram: отправлено'
    if (status === 'partial') return 'Telegram: частично'
    if (status === 'failed') return 'Telegram: ошибка'
    return 'Telegram: ожидает'
  }

  async function retryTelegram(applicationId:string) {
    setRetrying(applicationId)
    onError(null)
    try {
      await api.adminRetryQuestionnaireApplicationTelegram(applicationId)
      onItems(items.map((item) => item.id === applicationId
        ? { ...item, telegram_delivery_status:'pending', telegram_notified_at:null }
        : item))
    } catch (err) {
      onError(errorText(err))
    } finally {
      setRetrying(null)
    }
  }

  useEffect(() => {
    if (!focusId) return
    setExpanded(focusId)
    requestAnimationFrame(() => document.getElementById(`admin-application-${focusId}`)?.scrollIntoView({ block:'start' }))
  }, [focusId])
  return <section className="admin-panel">
    <div className="admin-panel-title"><div><h2>Заявки</h2><p>Полный проектный brief, контакт клиента, статус доставки в Telegram и финальный принятый эскиз.</p></div></div>
    <div className="admin-card-list">
      {items.length ? items.map((item) => {
        const lead = item.answers.zayavka || {}
        const isOpen = expanded === item.id
        return <article id={`admin-application-${item.id}`} className="admin-list-card admin-application-card" key={item.id}>
          <div className="admin-panel-title">
            <div>
              <h3>{item.project_name || 'Проект без названия'}</h3>
              <p>{applicationAnswer(lead['23'])} · {applicationAnswer(lead['24'])} · {formatDate(item.created_at)}</p>
            </div>
            <span>{deliveryLabel(item.telegram_delivery_status)}</span>
          </div>
          {item.scene_asset_url && <img className="admin-application-image" src={item.scene_asset_url} alt="Финальный эскиз заявки"/>}
          <div className="admin-table-wrap"><table className="admin-table"><tbody>
            <tr><th>Участок</th><td>{applicationAnswer(lead['20'])}</td></tr>
            <tr><th>Бюджет</th><td>{applicationAnswer(lead['21'])}</td></tr>
            <tr><th>Срок</th><td>{applicationAnswer(lead['22'])}</td></tr>
            <tr><th>Контакт из заявки</th><td>{applicationAnswer(item.application_contact)}</td></tr>
            <tr><th>E-mail аккаунта</th><td>{applicationAnswer(item.user_email)}</td></tr>
            <tr><th>Telegram ID</th><td>{applicationAnswer(item.telegram_user_id)}</td></tr>
            <tr><th>User ID</th><td><small>{item.user_id}</small></td></tr>
            <tr><th>Project ID</th><td><small>{item.project_id}</small></td></tr>
            <tr><th>Generation ID</th><td><small>{item.final_generation_id || '—'}</small></td></tr>
            <tr><th>ID заявки</th><td><small>{item.id}</small></td></tr>
          </tbody></table></div>
          <div className="admin-form-actions">
            {item.scene_asset_url && <a className="secondary-button" href={item.scene_asset_url} target="_blank" rel="noreferrer">Открыть работу</a>}
            <a className="secondary-button" href={`/?admin=1&application=${item.id}`}>Ссылка на заявку</a>
            <a className="secondary-button" href={`/?admin=1&user=${item.user_id}`}>Профиль клиента</a>
            {item.telegram_user_id && /^\d+$/.test(item.telegram_user_id) && <a className="secondary-button" href={`tg://user?id=${item.telegram_user_id}`}>Telegram профиль</a>}
            {['partial','failed'].includes(item.telegram_delivery_status) && <button type="button" className="secondary-button" disabled={retrying !== null} onClick={() => void retryTelegram(item.id)}>{retrying === item.id ? 'Повторяем…' : 'Повторить Telegram'}</button>}
            <button type="button" className="secondary-button" onClick={() => setExpanded(isOpen ? null : item.id)}>{isOpen ? 'Скрыть подробный brief' : 'Открыть подробный brief'}</button>
          </div>
          {isOpen && <div className="admin-subpanel">
            {item.brief.length ? item.brief.map((object) => <div key={object.key} className="admin-application-brief">
              <h3>{object.title} <small>{object.accepted ? '· принят' : '· не принят'}</small></h3>
              {object.answers.length ? <div className="admin-table-wrap"><table className="admin-table"><tbody>
                {object.answers.map((answer) => <tr key={answer.question_id}><th>{answer.question}</th><td>{applicationAnswer(answer.answer)}</td></tr>)}
              </tbody></table></div> : <p>Ответов по объекту нет.</p>}
            </div>) : <p>Подробный brief недоступен для этой исторической заявки.</p>}
          </div>}
        </article>
      }) : <p>Заявок пока нет.</p>}
    </div>
  </section>
}

function TariffsPanel({ items, onItems, billingSettings, onBillingSettings, onError }: {
  items: AdminTariff[]
  onItems: (v: AdminTariff[]) => void
  billingSettings: AdminBillingSettings
  onBillingSettings: (v: AdminBillingSettings) => void
  onError: (v: string | null) => void
}) {
  const [editing, setEditing] = useState<AdminTariff | null>(null)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [credits, setCredits] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('RUB')
  const [sortOrder, setSortOrder] = useState('0')
  const [active, setActive] = useState(true)
  const [busy, setBusy] = useState(false)

  function reset() { setEditing(null); setCode(''); setName(''); setDescription(''); setCredits(''); setAmount(''); setCurrency('RUB'); setSortOrder('0'); setActive(true) }
  function edit(item: AdminTariff) { setEditing(item); setCode(item.code); setName(item.name); setDescription(item.description || ''); setCredits(String(item.credits)); setAmount(item.amount); setCurrency(item.currency); setSortOrder(String(item.sort_order)); setActive(item.is_active) }
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); onError(null)
    try {
      const payload = { name: name.trim(), description: description.trim() || null, credits: Number(credits), amount, currency: currency.trim().toUpperCase(), is_active: active, sort_order: Number(sortOrder) }
      const saved = editing ? await api.adminUpdateTariff(editing.id, payload) : await api.adminCreateTariff({ code: code.trim(), ...payload })
      onItems(editing ? items.map((x) => x.id === saved.id ? saved : x) : [...items, saved])
      reset()
    } catch (err) { onError(errorText(err)) }
    finally { setBusy(false) }
  }
  async function toggle(item: AdminTariff) {
    try { const saved = await api.adminUpdateTariff(item.id, { is_active: !item.is_active }); onItems(items.map((x) => x.id === saved.id ? saved : x)) }
    catch (err) { onError(errorText(err)) }
  }
  return <section className="admin-panel">
    <div className="admin-panel-title"><div><h2>Тарифы</h2><p>Цена и количество кредитов хранятся в БД.</p></div></div>
    <form className="admin-form-grid" onSubmit={(e) => void submit(e)}>
      <label>Код<input disabled={Boolean(editing)} required value={code} onChange={(e) => setCode(e.target.value)} placeholder="start"/></label>
      <label>Название<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Старт"/></label>
      <label>Кредиты<input type="number" min="1" required value={credits} onChange={(e) => setCredits(e.target.value)}/></label>
      <label>Цена<input type="number" min="0.01" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)}/></label>
      <label>Валюта<input required maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value)}/></label>
      <label>Порядок<input type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}/></label>
      <label className="admin-span-2">Описание<input value={description} onChange={(e) => setDescription(e.target.value)}/></label>
      <label className="admin-checkbox"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)}/> Активен</label>
      <div className="admin-form-actions"><button className="primary-button" disabled={busy}>{editing ? 'Сохранить тариф' : 'Добавить тариф'}</button>{editing && <button type="button" className="secondary-button" onClick={reset}>Отмена</button>}</div>
    </form>
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Тариф</th><th>Кредиты</th><th>Цена</th><th>Статус</th><th/></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.code}</small></td><td>{item.credits}</td><td>{formatMoney(item.amount,item.currency)}</td><td>{item.is_active ? 'Активен' : 'Выключен'}</td><td><button onClick={() => edit(item)}>Изменить</button><button onClick={() => void toggle(item)}>{item.is_active ? 'Выключить' : 'Включить'}</button></td></tr>)}</tbody></table></div>
    <BillingSettingsEditor settings={billingSettings} onSaved={onBillingSettings} onError={onError}/>
  </section>
}

function BillingSettingsEditor({ settings, onSaved, onError }: { settings: AdminBillingSettings; onSaved: (v: AdminBillingSettings) => void; onError: (v: string | null) => void }) {
  const [enabled, setEnabled] = useState(settings.receipts_enabled)
  const [vat, setVat] = useState(settings.vat_code ? String(settings.vat_code) : '')
  const [subject, setSubject] = useState(settings.payment_subject || '')
  const [mode, setMode] = useState(settings.payment_mode || '')
  const [busy, setBusy] = useState(false)
  async function save() {
    setBusy(true); onError(null)
    try {
      const saved = await api.adminUpdateBillingSettings({ receipts_enabled: enabled, vat_code: enabled ? Number(vat) : null, payment_subject: enabled ? subject.trim() : null, payment_mode: enabled ? mode.trim() : null })
      onSaved(saved)
    } catch (err) { onError(errorText(err)) }
    finally { setBusy(false) }
  }
  return <div className="admin-subpanel"><div className="admin-panel-title"><div><h3>Фискальные чеки YooKassa</h3><p>При включении клиент указывает email, а чек передаётся в платёж.</p></div></div><div className="admin-form-grid compact"><label className="admin-checkbox"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}/> Передавать receipt</label><label>Код НДС<input type="number" min="1" max="12" disabled={!enabled} value={vat} onChange={(e) => setVat(e.target.value)}/></label><label>Предмет расчёта<input disabled={!enabled} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="service"/></label><label>Способ расчёта<input disabled={!enabled} value={mode} onChange={(e) => setMode(e.target.value)} placeholder="full_payment"/></label><div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>Сохранить кассу</button></div></div></div>
}

function IdeasPanel({ items, onItems, onError }: {
  items: AdminIdea[]
  onItems: (v: AdminIdea[]) => void
  onError: (v: string | null) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)

  async function toggle(item: AdminIdea) {
    if (busy) return
    setBusy(item.id); onError(null)
    try {
      const saved = await api.adminUpdateIdea(item.id, { is_active: !item.is_active })
      onItems(items.map((current) => current.id === saved.id ? saved : current))
    } catch (err) { onError(errorText(err)) }
    finally { setBusy(null) }
  }

  async function changeOrder(item: AdminIdea, value: string) {
    const sortOrder = Number(value)
    if (!Number.isInteger(sortOrder) || sortOrder < -100000 || sortOrder > 100000 || sortOrder === item.sort_order) return
    if (busy) return
    setBusy(item.id); onError(null)
    try {
      const saved = await api.adminUpdateIdea(item.id, { sort_order: sortOrder })
      onItems(items.map((current) => current.id === saved.id ? saved : current))
    } catch (err) { onError(errorText(err)) }
    finally { setBusy(null) }
  }

  return <section className="admin-panel">
    <div className="admin-panel-title"><div><h2>Идеи</h2><p>Пользователи сами добавляют принятые работы из «Создать». Здесь остаются только модерация, видимость и порядок ленты.</p></div></div>
    <div className="admin-subpanel">
      <div className="admin-panel-title"><div><h3>Лента</h3><p>Содержание берётся из принятой работы и ответов опросника. Отдельные промпты, картинки и 3D для идеи не используются.</p></div></div>
      <div className="admin-card-list">{items.length ? items.map((item) => <article className="admin-list-card admin-idea-card" key={item.id}>
        {item.image_url && <img src={item.image_url} alt={item.title}/>}
        <div><strong>{item.title}</strong><span>{item.category} · {modes.find((mode) => mode.id === item.generation_type)?.label}</span><p>{item.objects.reduce((count, object) => count + object.answers.length, 0)} параметров · добавлено {formatDate(item.published_at)}</p></div>
        <div><span className={`status-pill ${item.owner_published && item.is_active ? '' : 'muted'}`}>{!item.owner_published ? 'Снята автором' : item.is_active ? 'В ленте' : 'Скрыта модерацией'}</span><label>Порядок<input type="number" min="-100000" max="100000" defaultValue={item.sort_order} disabled={busy !== null} onBlur={(event) => void changeOrder(item, event.target.value)}/></label><button disabled={busy !== null || !item.owner_published} onClick={() => void toggle(item)}>{!item.owner_published ? 'Автор снял' : item.is_active ? 'Скрыть' : 'Вернуть в ленту'}</button></div>
      </article>) : <div className="empty-inline"><p>Пользователи пока не добавили работы в ленту.</p></div>}</div>
    </div>
  </section>
}

function parseSandboxParams(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value || '{}') as unknown
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('Sandbox params должны быть JSON-объектом')
  }
  return parsed as Record<string, unknown>
}

function GenerationPanel({ settings, prices, prompts, onSettings, onPrices, onPrompts, onError }: { settings: AdminGenerationSettings; prices: AdminGenerationPrice[]; prompts: AdminPrompt[]; onSettings:(v:AdminGenerationSettings)=>void; onPrices:(v:AdminGenerationPrice[])=>void; onPrompts:(v:AdminPrompt[])=>void; onError:(v:string|null)=>void }) {
  const [primary,setPrimary]=useState(settings.primary_model || '')
  const [fallback,setFallback]=useState(settings.fallback_model||'')
  const [primaryTimeout,setPrimaryTimeout]=useState(String(settings.primary_timeout_seconds||90))
  const [primaryParams,setPrimaryParams]=useState(JSON.stringify(settings.primary_params,null,2))
  const [fallbackParams,setFallbackParams]=useState(JSON.stringify(settings.fallback_params,null,2))
  const [modeParams,setModeParams]=useState(JSON.stringify(settings.mode_params,null,2))
  const [providerMargin,setProviderMargin]=useState(String(settings.masked_edit_provider_context_margin_fraction))
  const [featherFraction,setFeatherFraction]=useState(String(settings.masked_edit_feather_fraction))
  const [featherMin,setFeatherMin]=useState(String(settings.masked_edit_feather_min_px))
  const [featherMax,setFeatherMax]=useState(String(settings.masked_edit_feather_max_px))
  const [recompositeMultiplier,setRecompositeMultiplier]=useState(String(settings.masked_edit_recomposite_feather_multiplier))
  const [boundaryBand,setBoundaryBand]=useState(String(settings.masked_edit_boundary_band_px))
  const [maxLuma,setMaxLuma]=useState(String(settings.masked_edit_max_luma_excess))
  const [maxColor,setMaxColor]=useState(String(settings.masked_edit_max_color_excess))
  const [maxStraightEdge,setMaxStraightEdge]=useState(String(settings.masked_edit_max_straight_edge_fraction))
  const [qualityRetries,setQualityRetries]=useState(String(settings.generation_quality_max_retries))
  const [busy,setBusy]=useState(false)
  const [sandboxModel,setSandboxModel]=useState('')
  const [sandboxPrompt,setSandboxPrompt]=useState('')
  const [sandboxParams,setSandboxParams]=useState('{}')
  const [sandboxBusy,setSandboxBusy]=useState(false)
  const [sandboxGeneration,setSandboxGeneration]=useState<Generation|null>(null)
  const [flyoverPrompt,setFlyoverPrompt]=useState('')
  const [flyoverParams,setFlyoverParams]=useState('{}')
  const [flyoverKeyframes,setFlyoverKeyframes]=useState('6')
  const [flyoverInbetweens,setFlyoverInbetweens]=useState('3')
  const [flyoverDuration,setFlyoverDuration]=useState('120')
  const [flyoverBusy,setFlyoverBusy]=useState(false)
  const [flyoverGeneration,setFlyoverGeneration]=useState<Generation|null>(null)
  const [sandboxHistory,setSandboxHistory]=useState<AdminAiHistoryItem[]>([])
  const [historyLoading,setHistoryLoading]=useState(true)

  async function refreshSandboxHistory() {
    try {
      const items=await api.adminListGenerationSandboxHistory()
      setSandboxHistory(items)
      setSandboxGeneration(current => current ?? items.find(item =>
        item.kind==='sandbox'
        && item.generation.status==='completed'
        && Boolean(item.generation.output_asset)
      )?.generation ?? null)
    } catch(err) {
      onError(errorText(err))
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => { void refreshSandboxHistory() }, [])

  const historyHasActive=sandboxHistory.some(item =>
    ['queued','processing'].includes(item.generation.status)
  )
  useEffect(() => {
    if (!historyHasActive) return
    const timer=window.setInterval(() => { void refreshSandboxHistory() },2500)
    return () => window.clearInterval(timer)
  },[historyHasActive])

  useEffect(() => {
    if (!sandboxGeneration || !['queued','processing'].includes(sandboxGeneration.status)) return
    let cancelled = false
    const timer = window.setInterval(() => {
      void api.getGeneration(sandboxGeneration.id)
        .then((generation) => {
          if (cancelled) return
          setSandboxGeneration(generation)
          if (!['queued','processing'].includes(generation.status)) void refreshSandboxHistory()
        })
        .catch((err) => { if (!cancelled) onError(errorText(err)) })
    }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [sandboxGeneration?.id, sandboxGeneration?.status, onError])

  useEffect(() => {
    if (!flyoverGeneration || !['queued','processing'].includes(flyoverGeneration.status)) return
    let cancelled = false
    const timer = window.setInterval(() => {
      void api.getGeneration(flyoverGeneration.id)
        .then((generation) => {
          if (cancelled) return
          setFlyoverGeneration(generation)
          if (!['queued','processing'].includes(generation.status)) void refreshSandboxHistory()
        })
        .catch((err) => { if (!cancelled) onError(errorText(err)) })
    }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [flyoverGeneration?.id, flyoverGeneration?.status, onError])

  async function saveSettings(){
    const timeout=Number(primaryTimeout)
    if(!Number.isInteger(timeout)||timeout<30||timeout>600){onError('Primary timeout должен быть целым числом от 30 до 600 секунд');return}
    const margin=Number(providerMargin)
    const featherFractionValue=Number(featherFraction)
    const featherMinValue=Number(featherMin)
    const featherMaxValue=Number(featherMax)
    const recompositeMultiplierValue=Number(recompositeMultiplier)
    const boundaryBandValue=Number(boundaryBand)
    const maxLumaValue=Number(maxLuma)
    const maxColorValue=Number(maxColor)
    const maxStraightEdgeValue=Number(maxStraightEdge)
    const qualityRetriesValue=Number(qualityRetries)
    const invalidQuality = [
      margin, featherFractionValue, featherMinValue, featherMaxValue,
      recompositeMultiplierValue, boundaryBandValue, maxLumaValue, maxColorValue,
      maxStraightEdgeValue, qualityRetriesValue,
    ].some((value) => !Number.isFinite(value))
    if(invalidQuality){onError('Проверьте числовые параметры masked edit');return}
    if(featherMinValue>featherMaxValue){onError('Минимальный feather не может быть больше максимального');return}
    setBusy(true);onError(null)
    try{
      const saved=await api.adminUpdateGenerationSettings({
        primary_model:primary.trim(),
        fallback_model:fallback.trim()||null,
        primary_timeout_seconds:timeout,
        primary_params:JSON.parse(primaryParams||'{}') as Record<string,unknown>,
        fallback_params:JSON.parse(fallbackParams||'{}') as Record<string,unknown>,
        mode_params:JSON.parse(modeParams||'{}') as Record<string,Record<string,unknown>>,
        masked_edit_provider_context_margin_fraction:margin,
        masked_edit_feather_fraction:featherFractionValue,
        masked_edit_feather_min_px:featherMinValue,
        masked_edit_feather_max_px:featherMaxValue,
        masked_edit_recomposite_feather_multiplier:recompositeMultiplierValue,
        masked_edit_boundary_band_px:boundaryBandValue,
        masked_edit_max_luma_excess:maxLumaValue,
        masked_edit_max_color_excess:maxColorValue,
        masked_edit_max_straight_edge_fraction:maxStraightEdgeValue,
        generation_quality_max_retries:qualityRetriesValue,
      })
      onSettings(saved)
    }catch(err){onError(errorText(err))}
    finally{setBusy(false)}
  }
  async function runSandbox(){
    setSandboxBusy(true);onError(null)
    try{
      const created=await api.adminCreateGenerationSandbox({
        model_name:sandboxModel.trim(),
        prompt:sandboxPrompt.trim(),
        params:parseSandboxParams(sandboxParams),
      })
      setSandboxGeneration(created)
      void refreshSandboxHistory()
    }catch(err){onError(errorText(err))}
    finally{setSandboxBusy(false)}
  }
  async function runFlyover(){
    if (!sandboxGeneration?.output_asset || sandboxGeneration.status !== 'completed') return
    const keyframeCount=Number(flyoverKeyframes)
    const inbetweenFrames=Number(flyoverInbetweens)
    const frameDuration=Number(flyoverDuration)
    if (!Number.isInteger(keyframeCount)||keyframeCount<4||keyframeCount>8){onError('Ключевых кадров должно быть от 4 до 8');return}
    if (!Number.isInteger(inbetweenFrames)||inbetweenFrames<0||inbetweenFrames>5){onError('Промежуточных кадров должно быть от 0 до 5');return}
    if (!Number.isInteger(frameDuration)||frameDuration<60||frameDuration>500){onError('Длительность кадра должна быть от 60 до 500 мс');return}
    setFlyoverBusy(true);onError(null)
    try{
      const modelName=sandboxGeneration.model_name||sandboxModel.trim()
      if(!modelName) throw new Error('У исходного Sandbox результата нет model ID')
      const created=await api.adminCreateGenerationFlyoverGif({
        source_generation_id:sandboxGeneration.id,
        model_name:modelName,
        prompt:flyoverPrompt.trim(),
        params:parseSandboxParams(flyoverParams),
        keyframe_count:keyframeCount,
        inbetween_frames:inbetweenFrames,
        frame_duration_ms:frameDuration,
      })
      setFlyoverGeneration(created)
      void refreshSandboxHistory()
    }catch(err){onError(errorText(err))}
    finally{setFlyoverBusy(false)}
  }
  async function savePrice(mode: GenerationMode, value: number, active: boolean){try{const saved=await api.adminUpdateGenerationPrice(mode,value,active);onPrices([...prices.filter(x=>x.generation_type!==mode),saved])}catch(err){onError(errorText(err))}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>AI, стоимость и промпты</h2><p>Модели, параметры, стоимость кредитов и prompt templates управляются из БД.</p></div></div>
    <div className="admin-form-grid"><label>Primary model<input value={primary} onChange={e=>setPrimary(e.target.value)}/></label><label>Fallback model<input value={fallback} onChange={e=>setFallback(e.target.value)}/></label><label>Primary timeout, сек<input type="number" min="30" max="600" value={primaryTimeout} onChange={e=>setPrimaryTimeout(e.target.value)}/><small>После этого времени production переключается на fallback. Sandbox и GIF-пролёт не затрагиваются.</small></label><label className="admin-span-2">Primary params<textarea className="admin-code" value={primaryParams} onChange={e=>setPrimaryParams(e.target.value)}/></label><label className="admin-span-2">Fallback params<textarea className="admin-code" value={fallbackParams} onChange={e=>setFallbackParams(e.target.value)}/></label><label className="admin-span-2">Параметры по сценариям<textarea className="admin-code" value={modeParams} onChange={e=>setModeParams(e.target.value)}/></label>
      <div className="admin-span-2"><h3>Masked edit quality</h3><small>Контекст provider шире final commit region; финальный compositor по-прежнему запрещает изменения снаружи пользовательской области.</small></div>
      <label>Provider margin, доля<input type="number" min="0" max="0.25" step="0.005" value={providerMargin} onChange={e=>setProviderMargin(e.target.value)}/></label>
      <label>Feather fraction<input type="number" min="0" max="0.1" step="0.001" value={featherFraction} onChange={e=>setFeatherFraction(e.target.value)}/></label>
      <label>Feather min, px<input type="number" min="0" max="128" step="1" value={featherMin} onChange={e=>setFeatherMin(e.target.value)}/></label>
      <label>Feather max, px<input type="number" min="1" max="256" step="1" value={featherMax} onChange={e=>setFeatherMax(e.target.value)}/></label>
      <label>Re-composite multiplier<input type="number" min="1" max="4" step="0.05" value={recompositeMultiplier} onChange={e=>setRecompositeMultiplier(e.target.value)}/></label>
      <label>Boundary band, px<input type="number" min="1" max="64" step="1" value={boundaryBand} onChange={e=>setBoundaryBand(e.target.value)}/></label>
      <label>Max luma excess<input type="number" min="0" max="255" step="1" value={maxLuma} onChange={e=>setMaxLuma(e.target.value)}/></label>
      <label>Max color excess<input type="number" min="0" max="442" step="1" value={maxColor} onChange={e=>setMaxColor(e.target.value)}/></label>
      <label>Max straight edge<input type="number" min="0" max="1" step="0.01" value={maxStraightEdge} onChange={e=>setMaxStraightEdge(e.target.value)}/></label>
      <label>Quality retries<input type="number" min="0" max="3" step="1" value={qualityRetries} onChange={e=>setQualityRetries(e.target.value)}/></label>
      <div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy} onClick={()=>void saveSettings()}>Сохранить AI</button></div></div>
    <div className="admin-subpanel">
      <div className="admin-panel-title"><div><h3>AI Sandbox</h3><p>Одноразовый админский тест Nexus. Model ID, prompt и params применяются только к этому запуску: primary/fallback клиентов не меняются, кредиты не списываются.</p></div></div>
      <div className="admin-form-grid">
        <label className="admin-span-2">Nexus model ID<input value={sandboxModel} onChange={e=>setSandboxModel(e.target.value)} placeholder="provider/model-id"/></label>
        <label className="admin-span-2">Prompt<textarea value={sandboxPrompt} onChange={e=>setSandboxPrompt(e.target.value)} placeholder="Опишите тестовый рендер"/></label>
        <label className="admin-span-2">Model params (JSON)<textarea className="admin-code" value={sandboxParams} onChange={e=>setSandboxParams(e.target.value)}/></label>
        <div className="admin-form-actions"><button type="button" className="primary-button" disabled={sandboxBusy||!sandboxModel.trim()||!sandboxPrompt.trim()} onClick={()=>void runSandbox()}>{sandboxBusy?'Ставим в очередь…':'Запустить тест'}</button></div>
      </div>
      {sandboxGeneration && <div className="admin-card-list"><article className="admin-list-card admin-idea-card">
        {sandboxGeneration.output_asset && <img src={sandboxGeneration.output_asset.url} alt="AI Sandbox result"/>}
        <div><strong>{sandboxGeneration.model_name||sandboxModel}</strong><span>Статус: {sandboxGeneration.status}</span><p>Списано кредитов: {sandboxGeneration.credits_charged}{sandboxGeneration.fallback_used?' · использован fallback':''}</p>{sandboxGeneration.error && <p>{sandboxGeneration.error}</p>}</div>
        <div><small>{formatDate(sandboxGeneration.completed_at||sandboxGeneration.started_at||sandboxGeneration.created_at)}</small></div>
      </article></div>}
      {sandboxGeneration?.status==='completed'&&sandboxGeneration.output_asset&&<div className="admin-subpanel">
        <div className="admin-panel-title"><div><h3>Bird flyover GIF</h3><p>Дешёвый пролёт без video-модели: каждый следующий keyframe строится из предыдущего image-to-image кадра, затем локально добавляются промежуточные кадры и собирается GIF.</p></div></div>
        <div className="admin-form-grid">
          <label>Ключевых кадров<input type="number" min="4" max="8" value={flyoverKeyframes} onChange={e=>setFlyoverKeyframes(e.target.value)}/></label>
          <label>Промежуточных кадров<input type="number" min="0" max="5" value={flyoverInbetweens} onChange={e=>setFlyoverInbetweens(e.target.value)}/></label>
          <label>мс / кадр<input type="number" min="60" max="500" value={flyoverDuration} onChange={e=>setFlyoverDuration(e.target.value)}/></label>
          <label className="admin-span-2">Доп. инструкция<textarea value={flyoverPrompt} onChange={e=>setFlyoverPrompt(e.target.value)} placeholder="Например: сохраняй мягкий вечерний свет"/></label>
          <label className="admin-span-2">Flyover model params (JSON)<textarea className="admin-code" value={flyoverParams} onChange={e=>setFlyoverParams(e.target.value)}/></label>
          <div className="admin-span-2"><small>{Math.max(0,(Number(flyoverKeyframes)||0)-1)} image-вызовов · 0 video-вызовов · исходный кадр включён · 0 кредитов AuRoom</small></div>
          <div className="admin-form-actions"><button type="button" className="secondary-button" disabled={flyoverBusy} onClick={()=>void runFlyover()}>{flyoverBusy?'Собираем пролёт…':'Собрать GIF-пролёт'}</button></div>
        </div>
        {flyoverGeneration&&<div className="admin-card-list"><article className="admin-list-card admin-idea-card">
          {flyoverGeneration.output_asset&&<img src={flyoverGeneration.output_asset.url} alt="Bird flyover GIF"/>}
          <div><strong>Bird flyover GIF · {flyoverGeneration.model_name||sandboxGeneration.model_name}</strong><span>Статус: {flyoverGeneration.status}</span><p>Формат результата: GIF · списано кредитов: {flyoverGeneration.credits_charged}</p>{flyoverGeneration.error&&<p>{flyoverGeneration.error}</p>}</div>
          <div><small>{formatDate(flyoverGeneration.completed_at||flyoverGeneration.started_at||flyoverGeneration.created_at)}</small></div>
        </article></div>}
      </div>}
    </div>
    <div className="admin-subpanel">
      <div className="admin-panel-title"><div><h3>История AI Sandbox</h3><p>Still, новые GIF-пролёты и старые 360° WebP сохраняются после обновления страницы. Готовый still можно снова выбрать источником для пролёта.</p></div><button type="button" className="secondary-button" onClick={()=>void refreshSandboxHistory()}>Обновить историю</button></div>
      {historyLoading
        ? <small>Загружаем историю…</small>
        : sandboxHistory.length===0
          ? <small>Тестовых запусков пока нет.</small>
          : <div className="admin-card-list">{sandboxHistory.map(item=>{
              const generation=item.generation
              const durationSeconds=generation.started_at&&generation.completed_at
                ? Math.max(0,Math.round((new Date(generation.completed_at).getTime()-new Date(generation.started_at).getTime())/1000))
                : null
              const selected=item.kind==='sandbox'&&sandboxGeneration?.id===generation.id
              return <article className="admin-list-card admin-idea-card" key={generation.id}>
                {generation.output_asset&&<img src={generation.output_asset.url} alt={item.kind==='orbit'?'Legacy 360 degree orbit history':item.kind==='flyover_gif'?'Bird flyover GIF history':'AI Sandbox history result'}/>}
                <div><strong>{item.kind==='flyover_gif'?'Bird flyover GIF':item.kind==='orbit'?'Legacy 360° WebP':'Sandbox still'} · {generation.model_name||'model —'}</strong><span>{generation.status}{durationSeconds!==null?' · '+durationSeconds+' с':''}</span><p>{item.prompt||'Без дополнительного prompt'}</p><small>params: {JSON.stringify(item.params)}{item.kind==='flyover_gif'&&item.keyframe_count?' · '+item.keyframe_count+' keyframes · '+item.inbetween_frames+' промежуточных · '+item.frame_duration_ms+' мс':item.kind==='orbit'&&item.frame_count?' · '+item.frame_count+' кадров · '+item.frame_duration_ms+' мс':''}</small>{generation.error&&<p>{generation.error}</p>}</div>
                <div><small>{formatDate(generation.completed_at||generation.started_at||generation.created_at)}</small>{item.kind==='sandbox'&&generation.status==='completed'&&generation.output_asset&&<button type="button" className="secondary-button" disabled={selected} onClick={()=>{setSandboxGeneration(generation);setSandboxModel(generation.model_name||'');setSandboxPrompt(item.prompt);setSandboxParams(JSON.stringify(item.params,null,2));setFlyoverGeneration(null)}}>{selected?'Выбран для пролёта':'Использовать для пролёта'}</button>}</div>
              </article>
            })}</div>}
    </div>
    <div className="admin-subpanel"><h3>Стоимость генераций</h3><div className="admin-price-grid">{modes.map((m)=>{const row=prices.find(p=>p.generation_type===m.id);return <PriceEditor key={m.id} mode={m.id} label={m.label} initial={row} onSave={savePrice}/>})}</div></div>
    <div className="admin-prompts"><h3>Системные промпты</h3>{modes.map((m)=><PromptEditor key={m.id} mode={m.id} label={m.label} item={prompts.find(p=>p.generation_type===m.id)} onSaved={(saved)=>onPrompts([...prompts.filter(p=>p.generation_type!==m.id),saved])} onError={onError}/>)}</div>
  </section>
}

function PriceEditor({ mode, label, initial, onSave }: { mode: GenerationMode; label: string; initial?: AdminGenerationPrice; onSave:(mode:GenerationMode,value:number,active:boolean)=>Promise<void> }) {
  const [value,setValue]=useState(initial?String(initial.credits):'')
  const [active,setActive]=useState(initial?.is_active ?? true)
  const [busy,setBusy]=useState(false)
  async function save(){const credits=Number(value);if(!Number.isInteger(credits)||credits<=0)return;setBusy(true);try{await onSave(mode,credits,active)}finally{setBusy(false)}}
  return <div className="admin-price-card"><strong>{label}</strong><input type="number" min="1" value={value} onChange={e=>setValue(e.target.value)} placeholder="Кредиты"/><label><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/> активна</label><button className="secondary-button" disabled={busy} onClick={()=>void save()}>Сохранить</button></div>
}

function PromptEditor({mode,label,item,onSaved,onError}:{mode:GenerationMode;label:string;item?:AdminPrompt;onSaved:(p:AdminPrompt)=>void;onError:(v:string|null)=>void}){
  const [text,setText]=useState(item?.template||'');const [busy,setBusy]=useState(false)
  async function save(){setBusy(true);try{onSaved(await api.adminUpdatePrompt(mode,text))}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  return <div className="admin-prompt"><div><strong>{label}</strong><small>{item?`Обновлён ${formatDate(item.updated_at)}`:'Не настроен'}</small></div><textarea value={text} onChange={e=>setText(e.target.value)}/><button className="secondary-button" disabled={busy||!text.trim()} onClick={()=>void save()}>Сохранить</button></div>
}

function UsersPanel({ items, transactions, onItems, onTransactions, onError, focusUserId }: { items:AdminUser[]; transactions:AdminCreditTransaction[]; onItems:(v:AdminUser[])=>void; onTransactions:(v:AdminCreditTransaction[])=>void; onError:(v:string|null)=>void; focusUserId:string|null }) {
  const names=useMemo(()=>Object.fromEntries(items.map(u=>[u.id,u.display_name])),[items])
  async function update(user:AdminUser,payload:{status?:'active'|'disabled';role?:UserRole}){try{const saved=await api.adminUpdateUser(user.id,payload);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}
  async function changed(saved:AdminUser){onItems(items.map(x=>x.id===saved.id?saved:x));try{onTransactions(await api.adminListCreditTransactions())}catch(err){onError(errorText(err))}}
  useEffect(()=>{if(!focusUserId)return;requestAnimationFrame(()=>document.getElementById(`admin-user-${focusUserId}`)?.scrollIntoView({block:'center'}))},[focusUserId,items.length])
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Пользователи и кредиты</h2><p>Любое изменение баланса проходит через credit ledger.</p></div></div><div className="admin-card-list">{items.map(user=><article id={`admin-user-${user.id}`} className="admin-list-card admin-user-card" key={user.id}><div><strong>{user.display_name}</strong><span>{user.id}</span><p>{user.credits_balance} кредитов · {user.role} · {user.status}</p></div><div className="admin-user-controls"><select value={user.role} onChange={e=>void update(user,{role:e.target.value as UserRole})}><option value="user">user</option><option value="admin">admin</option><option value="superadmin">superadmin</option></select><select value={user.status} onChange={e=>void update(user,{status:e.target.value as 'active'|'disabled'})}><option value="active">active</option><option value="disabled">disabled</option></select><CreditEditor user={user} onChanged={(saved)=>void changed(saved)} onError={onError}/></div></article>)}</div>
    <div className="admin-subpanel"><div className="admin-panel-title"><div><h3>Credit ledger</h3><p>Последние 200 движений баланса.</p></div><button className="secondary-button" onClick={()=>void api.adminListCreditTransactions().then(onTransactions).catch(err=>onError(errorText(err)))}>Обновить ledger</button></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Пользователь</th><th>Тип</th><th>Изменение</th><th>Баланс</th><th>Причина</th></tr></thead><tbody>{transactions.map(tx=><tr key={tx.id}><td>{formatDate(tx.created_at)}</td><td>{names[tx.user_id]||tx.user_id}</td><td>{tx.kind}</td><td className={tx.amount>=0?'admin-credit-plus':'admin-credit-minus'}>{tx.amount>0?'+':''}{tx.amount}</td><td>{tx.balance_after}</td><td>{tx.reason||'—'}</td></tr>)}</tbody></table></div></div>
  </section>
}

function CreditEditor({ user, onChanged, onError }: { user: AdminUser; onChanged: (user: AdminUser) => void; onError:(v:string|null)=>void }) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit() {
    const value = Number(delta)
    if (!Number.isInteger(value) || value === 0 || reason.trim().length < 3) return
    setBusy(true)
    try { onChanged(await api.adminAdjustCredits(user.id, value, reason.trim())); setDelta(''); setReason('') }
    catch(err){onError(errorText(err))}
    finally { setBusy(false) }
  }
  return <div className="admin-credit-editor"><input type="number" placeholder="+/- кредиты" value={delta} onChange={(e) => setDelta(e.target.value)} /><input placeholder="Причина" value={reason} onChange={(e) => setReason(e.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => void submit()}>Применить</button></div>
}

function PaymentsPanel({items,onItems,onError}:{items:AdminPayment[];onItems:(v:AdminPayment[])=>void;onError:(v:string|null)=>void}){
  const [busy,setBusy]=useState<string|null>(null)
  const [providerIds,setProviderIds]=useState<Record<string,string>>({})
  async function action(item:AdminPayment,kind:'sync'|'refund'){if(kind==='refund'&&!window.confirm(`Вернуть ${formatMoney(item.amount,item.currency)} и списать ${item.credits} кредитов?`))return;setBusy(item.id);onError(null);try{const saved=kind==='sync'?await api.adminReconcilePayment(item.id, providerIds[item.id]?.trim()):await api.adminRefundPayment(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}finally{setBusy(null)}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Платежи</h2><p>Reconciliation и полный возврат выполняются сервером через YooKassa.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Пакет</th><th>Сумма</th><th>Кредиты</th><th>Статус</th><th>Чек</th><th/></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{formatDate(item.created_at)}</td><td><strong>{item.package_code}</strong><small>{item.yookassa_payment_id||item.id}</small></td><td>{formatMoney(item.amount,item.currency)}</td><td>{item.credits}</td><td>{item.status}{item.refund_status?` / refund: ${item.refund_status}`:''}{item.provider_error&&<small className="admin-error-text">{item.provider_error}</small>}</td><td>{item.receipt_email||'—'}</td><td>{!item.yookassa_payment_id&&<label>ID платежа в ЮKassa<input aria-label={`ID платежа в ЮKassa для ${item.package_code}`} maxLength={128} value={providerIds[item.id]||''} onChange={e=>setProviderIds({...providerIds,[item.id]:e.target.value})}/></label>}<button disabled={busy!==null||(!item.yookassa_payment_id&&!providerIds[item.id]?.trim())} onClick={()=>void action(item,'sync')}>Сверить</button>{item.status==='succeeded'&&item.refund_status!=='succeeded'&&<button disabled={busy!==null} onClick={()=>void action(item,'refund')}>{item.refund_status==='uncertain'?'Повторить возврат':'Возврат'}</button>}</td></tr>)}</tbody></table></div></section>
}

function BroadcastsPanel({items,onItems,onError}:{items:AdminBroadcast[];onItems:(v:AdminBroadcast[])=>void;onError:(v:string|null)=>void}){
  const [text,setText]=useState('')
  const [segment,setSegment]=useState<BroadcastSegment>('all')
  const [scheduled,setScheduled]=useState('')
  const [busy,setBusy]=useState<string|null>(null)
  async function create(){if(!text.trim())return;setBusy('create');try{const iso=scheduled?new Date(scheduled).toISOString():null;const saved=await api.adminCreateBroadcast(text.trim(),segment,iso);onItems([saved,...items]);setText('');setScheduled('')}catch(err){onError(errorText(err))}finally{setBusy(null)}}
  async function action(item:AdminBroadcast,kind:'send'|'retry'|'cancel'){
    const prompt=kind==='send'?`Поставить рассылку «${item.text.slice(0,80)}» в очередь?`:kind==='retry'?'Повторить отправку всем получателям с ошибкой?':'Отменить эту рассылку?'
    if(!window.confirm(prompt))return
    setBusy(item.id);try{const saved=kind==='send'?await api.adminSendBroadcast(item.id):kind==='retry'?await api.adminRetryBroadcast(item.id):await api.adminCancelBroadcast(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}finally{setBusy(null)}
  }
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Рассылки</h2><p>Очередь, сегменты, расписание и повторы работают через отдельный worker.</p></div></div><div className="admin-broadcast-compose"><textarea value={text} onChange={e=>setText(e.target.value)} placeholder="Сообщение пользователям Telegram"/><div className="admin-broadcast-options"><select value={segment} onChange={e=>setSegment(e.target.value as BroadcastSegment)}><option value="all">Все активные</option><option value="with_credits">С кредитами</option><option value="without_credits">Без кредитов</option></select><input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)}/><button className="primary-button" disabled={busy!==null||!text.trim()} onClick={()=>void create()}>{scheduled?'Запланировать':'Создать'}</button></div></div><div className="admin-card-list">{items.map(item=><article className="admin-list-card" key={item.id}><div><strong>{item.text}</strong><span>{item.segment} · {item.status} · {item.sent_count}/{item.recipient_count} · ошибок {item.failed_count}</span><p>{item.scheduled_at?`Запланировано: ${formatDate(item.scheduled_at)}`:item.sent_at?`Завершено: ${formatDate(item.sent_at)}`:`Создано: ${formatDate(item.created_at)}`}</p></div><div>{!['sent','canceled','scheduled'].includes(item.status)&&<button disabled={busy!==null} onClick={()=>void action(item,'send')}>В очередь</button>}{item.status==='scheduled'&&<span className="status-pill">Запланирована</span>}{item.failed_count>0&&<button disabled={busy!==null} onClick={()=>void action(item,'retry')}>Повторить ошибки</button>}{!['sent','canceled'].includes(item.status)&&<button disabled={busy!==null} onClick={()=>void action(item,'cancel')}>Отменить</button>}</div></article>)}</div></section>
}

function TelegramContentPanel({settings,onSaved,onError}:{settings:AdminTelegramContent;onSaved:(v:AdminTelegramContent)=>void;onError:(v:string|null)=>void}){
  const [botName,setBotName]=useState(settings.bot_name||'')
  const [shortDescription,setShortDescription]=useState(settings.short_description||'')
  const [description,setDescription]=useState(settings.description||'')
  const [startText,setStartText]=useState(settings.start_text||'')
  const [buttonText,setButtonText]=useState(settings.open_button_text||'')
  const [startCommand,setStartCommand]=useState(settings.start_command_description||'')
  const [appCommand,setAppCommand]=useState(settings.app_command_description||'')
  const [busy,setBusy]=useState(false)
  async function save(){setBusy(true);onError(null);try{onSaved(await api.adminUpdateTelegramContent({bot_name:botName.trim(),short_description:shortDescription.trim(),description:description.trim(),start_text:startText.trim(),open_button_text:buttonText.trim(),start_command_description:startCommand.trim(),app_command_description:appCommand.trim()}))}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  const valid=[botName,shortDescription,description,startText,buttonText,startCommand,appCommand].every(value=>value.trim())
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Telegram</h2><p>Имя, описание, приветствие и подписи кнопок бота хранятся в БД.</p></div><span className={`status-pill ${settings.configured?'':'muted'}`}>{settings.configured?'Настроено':'Нужно заполнить'}</span></div><div className="admin-form-grid"><label>Имя бота<input maxLength={64} value={botName} onChange={e=>setBotName(e.target.value)}/></label><label>Кнопка Mini App<input maxLength={64} value={buttonText} onChange={e=>setButtonText(e.target.value)}/></label><label className="admin-span-2">Короткое описание<input maxLength={120} value={shortDescription} onChange={e=>setShortDescription(e.target.value)}/></label><label className="admin-span-2">Описание<textarea maxLength={512} value={description} onChange={e=>setDescription(e.target.value)}/></label><label className="admin-span-2">Текст /start и /app<textarea maxLength={4096} value={startText} onChange={e=>setStartText(e.target.value)}/></label><label>/start — описание команды<input maxLength={256} value={startCommand} onChange={e=>setStartCommand(e.target.value)}/></label><label>/app — описание команды<input maxLength={256} value={appCommand} onChange={e=>setAppCommand(e.target.value)}/></label><div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy||!valid} onClick={()=>void save()}>Сохранить Telegram</button></div></div><div className="admin-subpanel"><small>Изменения применяются ботом автоматически после включения DB-конфига. Последнее изменение: {formatDate(settings.updated_at)}</small></div></section>
}

function OperationsPanel({settings,onSaved,onError}:{settings:AdminOperationalSettings;onSaved:(v:AdminOperationalSettings)=>void;onError:(v:string|null)=>void}){
  const [authLimit,setAuthLimit]=useState(settings.auth_rate_limit_per_minute.toString())
  const [generationLimit,setGenerationLimit]=useState(settings.generation_rate_limit_per_minute.toString())
  const [paymentLimit,setPaymentLimit]=useState(settings.payment_rate_limit_per_minute.toString())
  const [registrationDailyLimit,setRegistrationDailyLimit]=useState(settings.registration_rate_limit_per_day.toString())
  const [webhookLimit,setWebhookLimit]=useState(settings.yookassa_webhook_rate_limit_per_minute.toString())
  const [assetUploadLimit,setAssetUploadLimit]=useState(settings.asset_upload_rate_limit_per_minute.toString())
  const [assetCountLimit,setAssetCountLimit]=useState(settings.asset_max_retained_count_per_user.toString())
  const [assetBytesLimitMb,setAssetBytesLimitMb]=useState(Math.round(settings.asset_max_retained_bytes_per_user/1024/1024).toString())
  const [generationInflightLimit,setGenerationInflightLimit]=useState(settings.generation_max_inflight_per_user.toString())
  const [initialOfferDailyLimit,setInitialOfferDailyLimit]=useState(settings.initial_concept_offer_limit_per_day.toString())
  const [starterCredits,setStarterCredits]=useState(settings.starter_credits.toString())
  const [initialConceptCredits,setInitialConceptCredits]=useState(settings.initial_concept_credits.toString())
  const [mediaRetention,setMediaRetention]=useState(settings.media_retention_days.toString())
  const [backupInterval,setBackupInterval]=useState(settings.backup_interval_hours.toString())
  const [backupRetention,setBackupRetention]=useState(settings.backup_retention_days.toString())
  const [mediaMinFreeGb,setMediaMinFreeGb]=useState((settings.media_min_free_bytes/1024/1024/1024).toFixed(1).replace(/\.0$/,''))
  const [busy,setBusy]=useState(false)
  async function save(){setBusy(true);onError(null);try{onSaved(await api.adminUpdateOperationalSettings({auth_rate_limit_per_minute:Number(authLimit||30),generation_rate_limit_per_minute:Number(generationLimit||10),payment_rate_limit_per_minute:Number(paymentLimit||10),registration_rate_limit_per_day:Number(registrationDailyLimit||20),yookassa_webhook_rate_limit_per_minute:Number(webhookLimit||120),asset_upload_rate_limit_per_minute:Number(assetUploadLimit||12),asset_max_retained_count_per_user:Number(assetCountLimit||200),asset_max_retained_bytes_per_user:Math.round(Number(assetBytesLimitMb||512)*1024*1024),generation_max_inflight_per_user:Number(generationInflightLimit||2),initial_concept_offer_limit_per_day:Number(initialOfferDailyLimit||3),starter_credits:Number(starterCredits||0),initial_concept_credits:Number(initialConceptCredits||0),media_retention_days:Number(mediaRetention||30),backup_interval_hours:Number(backupInterval||24),backup_retention_days:Number(backupRetention||14),media_min_free_bytes:Math.round(Number(mediaMinFreeGb||2)*1024*1024*1024)}))}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Система</h2><p>Критичные security-лимиты всегда включены; значения, экономика, media и backup-политика управляются из БД.</p></div></div><div className="admin-form-grid"><label>Auth / мин<input type="number" min="1" value={authLimit} onChange={e=>setAuthLimit(e.target.value)}/></label><label>Генерации / мин<input type="number" min="1" value={generationLimit} onChange={e=>setGenerationLimit(e.target.value)}/></label><label>Платежи / мин<input type="number" min="1" value={paymentLimit} onChange={e=>setPaymentLimit(e.target.value)}/></label><label>Регистрации / день на IP<input type="number" min="1" value={registrationDailyLimit} onChange={e=>setRegistrationDailyLimit(e.target.value)}/></label><label>YooKassa webhook / мин на IP<input type="number" min="1" value={webhookLimit} onChange={e=>setWebhookLimit(e.target.value)}/></label><label>Uploads / мин на user/IP<input type="number" min="1" value={assetUploadLimit} onChange={e=>setAssetUploadLimit(e.target.value)}/></label><label>Retained media / user, файлов<input type="number" min="1" value={assetCountLimit} onChange={e=>setAssetCountLimit(e.target.value)}/></label><label>Retained media / user, MiB<input type="number" min="1" value={assetBytesLimitMb} onChange={e=>setAssetBytesLimitMb(e.target.value)}/></label><label>Одновременных генераций / user<input type="number" min="1" value={generationInflightLimit} onChange={e=>setGenerationInflightLimit(e.target.value)}/></label><label>Intro-концепций / 24ч / user<input type="number" min="1" value={initialOfferDailyLimit} onChange={e=>setInitialOfferDailyLimit(e.target.value)}/><small>После лимита генерация остаётся доступной по обычной цене master plan.</small></label><label>Стартовые кредиты<input type="number" min="0" value={starterCredits} onChange={e=>setStarterCredits(e.target.value)} /></label><label>Первая концепция, кредитов<input type="number" min="0" value={initialConceptCredits} onChange={e=>setInitialConceptCredits(e.target.value)} /><small>0 = бесплатно для обычного пользователя. Admin/superadmin всегда без списания.</small></label><label>Soft-deleted media, дней<input type="number" min="1" value={mediaRetention} onChange={e=>setMediaRetention(e.target.value)}/></label><label>Backup каждые, часов<input type="number" min="1" value={backupInterval} onChange={e=>setBackupInterval(e.target.value)}/></label><label>Хранить backup, дней<input type="number" min="1" value={backupRetention} onChange={e=>setBackupRetention(e.target.value)}/></label><label>Резерв свободного диска, GiB<input type="number" min="0.0625" step="0.5" value={mediaMinFreeGb} onChange={e=>setMediaMinFreeGb(e.target.value)}/><small>Новые uploads блокируются до заполнения диска.</small></label><div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy} onClick={()=>void save()}>Сохранить систему</button></div></div><div className="admin-subpanel"><p><strong>Секреты</strong> Nexus, YooKassa и Telegram здесь не хранятся — только operational-настройки.</p><small>Последнее изменение: {formatDate(settings.updated_at)}</small></div></section>
}

function AuditPanel({items}:{items:AdminAudit[]}){
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Аудит</h2><p>Последние действия операторов.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Действие</th><th>Сущность</th><th>Actor</th><th>Детали</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.action}</td><td>{item.entity_type}<small>{item.entity_id||''}</small></td><td>{item.actor_user_id||'system'}</td><td><small>{JSON.stringify(item.details)}</small></td></tr>)}</tbody></table></div></section>
}
