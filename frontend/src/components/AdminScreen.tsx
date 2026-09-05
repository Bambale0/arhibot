import { useEffect, useMemo, useState, type FormEvent } from 'react'
import * as api from '../api'
import type {
  AdminAudit,
  AdminBroadcast,
  AdminGenerationSettings,
  AdminIdea,
  AdminOverview,
  AdminPayment,
  AdminPrompt,
  AdminTariff,
  AdminUser,
  GenerationMode,
  UserRole,
} from '../types'

const modes: { id: GenerationMode; label: string }[] = [
  { id: 'floor_plan', label: 'Планировка' },
  { id: 'facade', label: 'Фасад' },
  { id: 'master_plan', label: 'Мастер-план' },
  { id: 'interior', label: 'Интерьер' },
]

type Tab = 'tariffs' | 'ideas' | 'generation' | 'users' | 'payments' | 'broadcasts' | 'audit'

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Не удалось выполнить операцию'
}

function formatMoney(amount: string, currency: string) {
  return `${Number(amount).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${currency}`
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`admin-provider-status ${ok ? 'ok' : 'off'}`}><i />{label}: {ok ? 'настроен' : 'не настроен'}</span>
}

function CreditEditor({ user, onChanged }: { user: AdminUser; onChanged: (user: AdminUser) => void }) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit() {
    const value = Number(delta)
    if (!Number.isInteger(value) || value === 0 || reason.trim().length < 3) return
    setBusy(true)
    try {
      onChanged(await api.adminAdjustCredits(user.id, value, reason.trim()))
      setDelta('')
      setReason('')
    } finally { setBusy(false) }
  }
  return <div className="admin-credit-editor"><input type="number" placeholder="+/- кредиты" value={delta} onChange={(e) => setDelta(e.target.value)} /><input placeholder="Причина" value={reason} onChange={(e) => setReason(e.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => void submit()}>Применить</button></div>
}

export function AdminScreen({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('tariffs')
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [tariffs, setTariffs] = useState<AdminTariff[]>([])
  const [ideas, setIdeas] = useState<AdminIdea[]>([])
  const [generation, setGeneration] = useState<AdminGenerationSettings | null>(null)
  const [prompts, setPrompts] = useState<AdminPrompt[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [payments, setPayments] = useState<AdminPayment[]>([])
  const [broadcasts, setBroadcasts] = useState<AdminBroadcast[]>([])
  const [audit, setAudit] = useState<AdminAudit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    setError(null)
    try {
      const [o, t, i, g, p, u, pay, b, a] = await Promise.all([
        api.adminOverview(), api.adminListTariffs(), api.adminListIdeas(),
        api.adminGetGenerationSettings(), api.adminListPrompts(), api.adminListUsers(),
        api.adminListPayments(), api.adminListBroadcasts(), api.adminListAudit(),
      ])
      setOverview(o); setTariffs(t); setIdeas(i); setGeneration(g); setPrompts(p)
      setUsers(u); setPayments(pay); setBroadcasts(b); setAudit(a)
    } catch (err) { setError(errorText(err)) }
    finally { setLoading(false) }
  }

  useEffect(() => { void reload() }, [])

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div><span className="eyebrow">AUROOM CONTROL PLANE</span><h1>Веб-админка</h1><p>Бизнес-настройки меняются здесь, без правки кода и `.env`.</p></div>
        <div className="admin-header-actions"><button className="secondary-button" onClick={() => void reload()}>Обновить</button><button className="secondary-button" onClick={onClose}>← В приложение</button></div>
      </header>
      {overview && <div className="admin-provider-row"><StatusDot ok={overview.yookassa_configured} label="YooKassa"/><StatusDot ok={overview.nexus_configured} label="Nexus"/><StatusDot ok={overview.telegram_configured} label="Telegram"/></div>}
      {error && <div className="banner-error">{error}<button onClick={() => setError(null)}>Закрыть</button></div>}
      <nav className="admin-tabs">
        {([
          ['tariffs','Тарифы'], ['ideas','Идеи'], ['generation','AI и промпты'], ['users','Пользователи'],
          ['payments','Платежи'], ['broadcasts','Рассылки'], ['audit','Аудит'],
        ] as [Tab,string][]).map(([id,label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      {loading ? <div className="admin-loading">Загружаем настройки…</div> : (
        <div className="admin-content">
          {tab === 'tariffs' && <TariffsPanel items={tariffs} onItems={setTariffs} onError={setError} />}
          {tab === 'ideas' && <IdeasPanel items={ideas} onItems={setIdeas} onError={setError} />}
          {tab === 'generation' && generation && <GenerationPanel settings={generation} prompts={prompts} onSettings={setGeneration} onPrompts={setPrompts} onError={setError} />}
          {tab === 'users' && <UsersPanel items={users} onItems={setUsers} onError={setError} />}
          {tab === 'payments' && <PaymentsPanel items={payments} onItems={setPayments} onError={setError} />}
          {tab === 'broadcasts' && <BroadcastsPanel items={broadcasts} onItems={setBroadcasts} onError={setError} />}
          {tab === 'audit' && <AuditPanel items={audit} />}
        </div>
      )}
    </main>
  )
}

function TariffsPanel({ items, onItems, onError }: { items: AdminTariff[]; onItems: (v: AdminTariff[]) => void; onError: (v: string | null) => void }) {
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
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Тарифы</h2><p>Цена и кредиты берутся только из БД.</p></div></div>
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
  </section>
}

function IdeasPanel({ items, onItems, onError }: { items: AdminIdea[]; onItems: (v: AdminIdea[]) => void; onError: (v: string | null) => void }) {
  const [editing, setEditing] = useState<AdminIdea | null>(null)
  const [title, setTitle] = useState(''); const [category, setCategory] = useState(''); const [text, setText] = useState(''); const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<GenerationMode>('facade'); const [sortOrder, setSortOrder] = useState('0'); const [active, setActive] = useState(true); const [busy, setBusy] = useState(false)
  function reset(){setEditing(null);setTitle('');setCategory('');setText('');setPrompt('');setMode('facade');setSortOrder('0');setActive(true)}
  function edit(item:AdminIdea){setEditing(item);setTitle(item.title);setCategory(item.category);setText(item.text);setPrompt(item.prompt);setMode(item.generation_type);setSortOrder(String(item.sort_order));setActive(item.is_active)}
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);onError(null);try{const payload={title:title.trim(),category:category.trim(),text:text.trim(),prompt:prompt.trim(),generation_type:mode,is_active:active,sort_order:Number(sortOrder)};const saved=editing?await api.adminUpdateIdea(editing.id,payload):await api.adminCreateIdea(payload);onItems(editing?items.map(x=>x.id===saved.id?saved:x):[...items,saved]);reset()}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  async function toggle(item:AdminIdea){try{const saved=await api.adminUpdateIdea(item.id,{is_active:!item.is_active});onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Идеи</h2><p>Лента клиента полностью формируется из этих записей.</p></div></div>
    <form className="admin-form-grid" onSubmit={(e)=>void submit(e)}><label>Название<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Категория<input required value={category} onChange={e=>setCategory(e.target.value)}/></label><label>Сценарий<select value={mode} onChange={e=>setMode(e.target.value as GenerationMode)}>{modes.map(m=><option value={m.id} key={m.id}>{m.label}</option>)}</select></label><label>Порядок<input type="number" value={sortOrder} onChange={e=>setSortOrder(e.target.value)}/></label><label className="admin-span-2">Текст<textarea required value={text} onChange={e=>setText(e.target.value)}/></label><label className="admin-span-2">Промпт при выборе<textarea value={prompt} onChange={e=>setPrompt(e.target.value)}/></label><label className="admin-checkbox"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/> Опубликована</label><div className="admin-form-actions"><button className="primary-button" disabled={busy}>{editing?'Сохранить':'Добавить идею'}</button>{editing&&<button type="button" className="secondary-button" onClick={reset}>Отмена</button>}</div></form>
    <div className="admin-card-list">{items.map(item=><article className="admin-list-card" key={item.id}><div><strong>{item.title}</strong><span>{item.category} · {modes.find(m=>m.id===item.generation_type)?.label}</span><p>{item.text}</p></div><div><span className={`status-pill ${item.is_active?'':'muted'}`}>{item.is_active?'Опубликована':'Скрыта'}</span><button onClick={()=>edit(item)}>Изменить</button><button onClick={()=>void toggle(item)}>{item.is_active?'Скрыть':'Опубликовать'}</button></div></article>)}</div>
  </section>
}

function GenerationPanel({ settings, prompts, onSettings, onPrompts, onError }: { settings: AdminGenerationSettings; prompts: AdminPrompt[]; onSettings:(v:AdminGenerationSettings)=>void; onPrompts:(v:AdminPrompt[])=>void; onError:(v:string|null)=>void }) {
  const [primary,setPrimary]=useState(settings.primary_model);const [fallback,setFallback]=useState(settings.fallback_model||'');const [primaryParams,setPrimaryParams]=useState(JSON.stringify(settings.primary_params,null,2));const [fallbackParams,setFallbackParams]=useState(JSON.stringify(settings.fallback_params,null,2));const [modeParams,setModeParams]=useState(JSON.stringify(settings.mode_params,null,2));const [busy,setBusy]=useState(false)
  async function saveSettings(){setBusy(true);onError(null);try{const saved=await api.adminUpdateGenerationSettings({primary_model:primary.trim(),fallback_model:fallback.trim()||null,primary_params:JSON.parse(primaryParams||'{}'),fallback_params:JSON.parse(fallbackParams||'{}'),mode_params:JSON.parse(modeParams||'{}')});onSettings(saved)}catch(err){onError(err instanceof SyntaxError?'Проверьте JSON параметров.':errorText(err))}finally{setBusy(false)}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>AI и промпты</h2><p>Worker читает эти значения из БД при каждой генерации.</p></div></div><div className="admin-form-grid"><label>Primary model<input value={primary} onChange={e=>setPrimary(e.target.value)}/></label><label>Fallback model<input value={fallback} onChange={e=>setFallback(e.target.value)}/></label><label className="admin-span-2">Primary params JSON<textarea className="admin-code" value={primaryParams} onChange={e=>setPrimaryParams(e.target.value)}/></label><label className="admin-span-2">Fallback params JSON<textarea className="admin-code" value={fallbackParams} onChange={e=>setFallbackParams(e.target.value)}/></label><label className="admin-span-2">Параметры сценариев JSON<textarea className="admin-code" value={modeParams} onChange={e=>setModeParams(e.target.value)}/></label><div className="admin-form-actions"><button className="primary-button" disabled={busy} onClick={()=>void saveSettings()}>Сохранить AI-настройки</button></div></div><div className="admin-prompts"><h3>Промпты сценариев</h3>{prompts.map(p=><PromptEditor key={p.generation_type} prompt={p} onSaved={saved=>onPrompts(prompts.map(x=>x.generation_type===saved.generation_type?saved:x))} onError={onError}/>)}</div></section>
}

function PromptEditor({ prompt, onSaved, onError }: { prompt:AdminPrompt;onSaved:(v:AdminPrompt)=>void;onError:(v:string|null)=>void }){const [value,setValue]=useState(prompt.template);const [busy,setBusy]=useState(false);const label=modes.find(m=>m.id===prompt.generation_type)?.label||prompt.generation_type;async function save(){setBusy(true);try{onSaved(await api.adminUpdatePrompt(prompt.generation_type,value))}catch(err){onError(errorText(err))}finally{setBusy(false)}}return <div className="admin-prompt"><div><strong>{label}</strong><small>Доступны {'{project_context}'} и {'{user_prompt}'}</small></div><textarea value={value} onChange={e=>setValue(e.target.value)}/><button className="secondary-button" disabled={busy} onClick={()=>void save()}>Сохранить промпт</button></div>}

function UsersPanel({items,onItems,onError}:{items:AdminUser[];onItems:(v:AdminUser[])=>void;onError:(v:string|null)=>void}){function replace(saved:AdminUser){onItems(items.map(x=>x.id===saved.id?saved:x))}async function state(user:AdminUser,field:'status'|'role',value:string){try{replace(await api.adminUpdateUser(user.id,field==='status'?{status:value as 'active'|'disabled'}:{role:value as UserRole}))}catch(err){onError(errorText(err))}}return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Пользователи</h2><p>Баланс, статус и роли управляются без SQL.</p></div></div><div className="admin-card-list">{items.map(user=><article className="admin-list-card admin-user-card" key={user.id}><div><strong>{user.display_name}</strong><span>{user.id}</span><p>Баланс: <b>{user.credits_balance}</b> кредитов</p></div><div className="admin-user-controls"><select value={user.status} onChange={e=>void state(user,'status',e.target.value)}><option value="active">active</option><option value="disabled">disabled</option></select><select value={user.role} onChange={e=>void state(user,'role',e.target.value)}><option value="user">user</option><option value="admin">admin</option><option value="superadmin">superadmin</option></select><CreditEditor user={user} onChanged={replace}/></div></article>)}</div></section>}

function PaymentsPanel({items,onItems,onError}:{items:AdminPayment[];onItems:(v:AdminPayment[])=>void;onError:(v:string|null)=>void}){async function sync(item:AdminPayment){try{const saved=await api.adminReconcilePayment(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Платежи</h2><p>История YooKassa и ручная сверка статуса.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>User</th><th>Тариф</th><th>Сумма</th><th>Статус</th><th/></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{new Date(item.created_at).toLocaleString('ru-RU')}</td><td><small>{item.user_id}</small></td><td>{item.package_code}<small>+{item.credits}</small></td><td>{formatMoney(item.amount,item.currency)}</td><td>{item.status}{item.provider_error&&<small className="admin-error-text">{item.provider_error}</small>}</td><td><button onClick={()=>void sync(item)}>Сверить</button></td></tr>)}</tbody></table></div></section>}

function BroadcastsPanel({items,onItems,onError}:{items:AdminBroadcast[];onItems:(v:AdminBroadcast[])=>void;onError:(v:string|null)=>void}){const [text,setText]=useState('');const [busy,setBusy]=useState(false);async function create(){if(!text.trim())return;setBusy(true);try{const saved=await api.adminCreateBroadcast(text.trim());onItems([saved,...items]);setText('')}catch(err){onError(errorText(err))}finally{setBusy(false)}}async function send(item:AdminBroadcast){if(!window.confirm(`Отправить рассылку всем активным Telegram-пользователям?\n\n${item.text}`))return;try{const saved=await api.adminSendBroadcast(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Рассылки</h2><p>Создание и отправка без серверной CLI-команды.</p></div></div><div className="admin-broadcast-compose"><textarea maxLength={4000} placeholder="Сообщение пользователям…" value={text} onChange={e=>setText(e.target.value)}/><button className="primary-button" disabled={busy||!text.trim()} onClick={()=>void create()}>Создать рассылку</button></div><div className="admin-card-list">{items.map(item=><article className="admin-list-card" key={item.id}><div><strong>{item.status}</strong><p>{item.text}</p><span>{item.sent_count}/{item.recipient_count} отправлено · ошибок {item.failed_count}</span></div><div>{item.status!=='sent'&&<button className="secondary-button" onClick={()=>void send(item)}>Отправить</button>}</div></article>)}</div></section>}

function AuditPanel({items}:{items:AdminAudit[]}){const rows=useMemo(()=>items.slice(0,200),[items]);return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Аудит</h2><p>Кто и какие операторские изменения выполнял.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Действие</th><th>Объект</th><th>Actor</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{new Date(row.created_at).toLocaleString('ru-RU')}</td><td>{row.action}</td><td>{row.entity_type}<small>{row.entity_id||''}</small></td><td><small>{row.actor_user_id||'system'}</small></td></tr>)}</tbody></table></div></section>}
