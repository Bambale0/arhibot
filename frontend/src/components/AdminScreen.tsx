import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import * as api from '../api'
import type {
  AdminAudit,
  AdminBillingSettings,
  AdminBroadcast,
  AdminCreditTransaction,
  AdminGenerationPrice,
  AdminGenerationSettings,
  AdminIdea,
  AdminOverview,
  AdminPayment,
  AdminPrompt,
  AdminTariff,
  AdminUser,
  BroadcastSegment,
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

function formatDate(value?: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`admin-provider-status ${ok ? 'ok' : 'off'}`}><i />{label}: {ok ? 'настроен' : 'не настроен'}</span>
}

export function AdminScreen({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('tariffs')
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [tariffs, setTariffs] = useState<AdminTariff[]>([])
  const [billingSettings, setBillingSettings] = useState<AdminBillingSettings | null>(null)
  const [ideas, setIdeas] = useState<AdminIdea[]>([])
  const [generation, setGeneration] = useState<AdminGenerationSettings | null>(null)
  const [prices, setPrices] = useState<AdminGenerationPrice[]>([])
  const [prompts, setPrompts] = useState<AdminPrompt[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [transactions, setTransactions] = useState<AdminCreditTransaction[]>([])
  const [payments, setPayments] = useState<AdminPayment[]>([])
  const [broadcasts, setBroadcasts] = useState<AdminBroadcast[]>([])
  const [audit, setAudit] = useState<AdminAudit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    setError(null)
    try {
      const [o, t, bs, i, g, gp, p, u, tx, pay, b, a] = await Promise.all([
        api.adminOverview(),
        api.adminListTariffs(),
        api.adminGetBillingSettings(),
        api.adminListIdeas(),
        api.adminGetGenerationSettings(),
        api.adminListGenerationPrices(),
        api.adminListPrompts(),
        api.adminListUsers(),
        api.adminListCreditTransactions(),
        api.adminListPayments(),
        api.adminListBroadcasts(),
        api.adminListAudit(),
      ])
      setOverview(o)
      setTariffs(t)
      setBillingSettings(bs)
      setIdeas(i)
      setGeneration(g)
      setPrices(gp)
      setPrompts(p)
      setUsers(u)
      setTransactions(tx)
      setPayments(pay)
      setBroadcasts(b)
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
        <div className="admin-header-actions"><button className="secondary-button" onClick={() => void reload()}>Обновить</button><button className="secondary-button" onClick={onClose}>← В приложение</button></div>
      </header>
      {overview && <div className="admin-provider-row"><StatusDot ok={overview.yookassa_configured} label="YooKassa"/><StatusDot ok={overview.nexus_configured} label="Nexus"/><StatusDot ok={overview.telegram_configured} label="Telegram"/></div>}
      {error && <div className="banner-error">{error}<button onClick={() => setError(null)}>Закрыть</button></div>}
      <nav className="admin-tabs">
        {([
          ['tariffs','Тарифы и касса'], ['ideas','Идеи'], ['generation','AI и стоимость'], ['users','Пользователи и кредиты'],
          ['payments','Платежи'], ['broadcasts','Рассылки'], ['audit','Аудит'],
        ] as [Tab,string][]).map(([id,label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      {loading ? <div className="admin-loading">Загружаем настройки…</div> : (
        <div className="admin-content">
          {tab === 'tariffs' && billingSettings && <TariffsPanel items={tariffs} onItems={setTariffs} billingSettings={billingSettings} onBillingSettings={setBillingSettings} onError={setError} />}
          {tab === 'ideas' && <IdeasPanel items={ideas} onItems={setIdeas} onError={setError} />}
          {tab === 'generation' && generation && <GenerationPanel settings={generation} prices={prices} prompts={prompts} onSettings={setGeneration} onPrices={setPrices} onPrompts={setPrompts} onError={setError} />}
          {tab === 'users' && <UsersPanel items={users} transactions={transactions} onItems={setUsers} onTransactions={setTransactions} onError={setError} />}
          {tab === 'payments' && <PaymentsPanel items={payments} onItems={setPayments} onError={setError} />}
          {tab === 'broadcasts' && <BroadcastsPanel items={broadcasts} onItems={setBroadcasts} onError={setError} />}
          {tab === 'audit' && <AuditPanel items={audit} />}
        </div>
      )}
    </main>
  )
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

function IdeasPanel({ items, onItems, onError }: { items: AdminIdea[]; onItems: (v: AdminIdea[]) => void; onError: (v: string | null) => void }) {
  const [editing, setEditing] = useState<AdminIdea | null>(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [text, setText] = useState('')
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<GenerationMode>('facade')
  const [sortOrder, setSortOrder] = useState('0')
  const [active, setActive] = useState(true)
  const [imageAssetId, setImageAssetId] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(false)

  function reset(){setEditing(null);setTitle('');setCategory('');setText('');setPrompt('');setMode('facade');setSortOrder('0');setActive(true);setImageAssetId(null);setImageUrl(null)}
  function edit(item:AdminIdea){setEditing(item);setTitle(item.title);setCategory(item.category);setText(item.text);setPrompt(item.prompt);setMode(item.generation_type);setSortOrder(String(item.sort_order));setActive(item.is_active);setImageAssetId(item.image_asset_id);setImageUrl(item.image_url)}
  async function uploadImage(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); onError(null)
    try { const asset = await api.uploadAsset(null, file, 'project_reference'); setImageAssetId(asset.id); setImageUrl(asset.url) }
    catch (err) { onError(errorText(err)) }
    finally { setUploading(false); e.target.value = '' }
  }
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);onError(null);try{const payload={title:title.trim(),category:category.trim(),text:text.trim(),prompt:prompt.trim(),generation_type:mode,image_asset_id:imageAssetId,is_active:active,sort_order:Number(sortOrder)};const saved=editing?await api.adminUpdateIdea(editing.id,payload):await api.adminCreateIdea(payload);onItems(editing?items.map(x=>x.id===saved.id?saved:x):[...items,saved]);reset()}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  async function toggle(item:AdminIdea){try{const saved=await api.adminUpdateIdea(item.id,{is_active:!item.is_active});onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Идеи</h2><p>Публикуйте настоящие визуальные референсы с готовым prompt.</p></div></div>
    <form className="admin-form-grid" onSubmit={(e)=>void submit(e)}><label>Название<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Категория<input required value={category} onChange={e=>setCategory(e.target.value)}/></label><label>Сценарий<select value={mode} onChange={e=>setMode(e.target.value as GenerationMode)}>{modes.map(m=><option value={m.id} key={m.id}>{m.label}</option>)}</select></label><label>Порядок<input type="number" value={sortOrder} onChange={e=>setSortOrder(e.target.value)}/></label><label className="admin-span-2">Текст<textarea required value={text} onChange={e=>setText(e.target.value)}/></label><label className="admin-span-2">Промпт при выборе<textarea value={prompt} onChange={e=>setPrompt(e.target.value)}/></label><label className="admin-span-2">Изображение<input type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={(e) => void uploadImage(e)}/>{imageUrl && <img className="admin-idea-preview" src={imageUrl} alt="Превью идеи"/>}</label><label className="admin-checkbox"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/> Опубликована</label><div className="admin-form-actions">{imageAssetId && <button type="button" className="secondary-button" onClick={() => {setImageAssetId(null);setImageUrl(null)}}>Убрать изображение</button>}<button className="primary-button" disabled={busy||uploading}>{editing?'Сохранить':'Добавить идею'}</button>{editing&&<button type="button" className="secondary-button" onClick={reset}>Отмена</button>}</div></form>
    <div className="admin-card-list">{items.map(item=><article className="admin-list-card admin-idea-card" key={item.id}>{item.image_url && <img src={item.image_url} alt={item.title}/>}<div><strong>{item.title}</strong><span>{item.category} · {modes.find(m=>m.id===item.generation_type)?.label}</span><p>{item.text}</p></div><div><span className={`status-pill ${item.is_active?'':'muted'}`}>{item.is_active?'Опубликована':'Скрыта'}</span><button onClick={()=>edit(item)}>Изменить</button><button onClick={()=>void toggle(item)}>{item.is_active?'Скрыть':'Опубликовать'}</button></div></article>)}</div>
  </section>
}

function GenerationPanel({ settings, prices, prompts, onSettings, onPrices, onPrompts, onError }: { settings: AdminGenerationSettings; prices: AdminGenerationPrice[]; prompts: AdminPrompt[]; onSettings:(v:AdminGenerationSettings)=>void; onPrices:(v:AdminGenerationPrice[])=>void; onPrompts:(v:AdminPrompt[])=>void; onError:(v:string|null)=>void }) {
  const [primary,setPrimary]=useState(settings.primary_model || '')
  const [fallback,setFallback]=useState(settings.fallback_model||'')
  const [primaryParams,setPrimaryParams]=useState(JSON.stringify(settings.primary_params,null,2))
  const [fallbackParams,setFallbackParams]=useState(JSON.stringify(settings.fallback_params,null,2))
  const [modeParams,setModeParams]=useState(JSON.stringify(settings.mode_params,null,2))
  const [busy,setBusy]=useState(false)
  async function saveSettings(){setBusy(true);onError(null);try{const saved=await api.adminUpdateGenerationSettings({primary_model:primary.trim(),fallback_model:fallback.trim()||null,primary_params:JSON.parse(primaryParams||'{}') as Record<string,unknown>,fallback_params:JSON.parse(fallbackParams||'{}') as Record<string,unknown>,mode_params:JSON.parse(modeParams||'{}') as Record<string,Record<string,unknown>>});onSettings(saved)}catch(err){onError(errorText(err))}finally{setBusy(false)}}
  async function savePrice(mode: GenerationMode, value: number, active: boolean){try{const saved=await api.adminUpdateGenerationPrice(mode,value,active);onPrices([...prices.filter(x=>x.generation_type!==mode),saved])}catch(err){onError(errorText(err))}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>AI, стоимость и промпты</h2><p>Модели, параметры, стоимость кредитов и prompt templates управляются из БД.</p></div></div>
    <div className="admin-form-grid"><label>Primary model<input value={primary} onChange={e=>setPrimary(e.target.value)}/></label><label>Fallback model<input value={fallback} onChange={e=>setFallback(e.target.value)}/></label><label className="admin-span-2">Primary params<textarea className="admin-code" value={primaryParams} onChange={e=>setPrimaryParams(e.target.value)}/></label><label className="admin-span-2">Fallback params<textarea className="admin-code" value={fallbackParams} onChange={e=>setFallbackParams(e.target.value)}/></label><label className="admin-span-2">Параметры по сценариям<textarea className="admin-code" value={modeParams} onChange={e=>setModeParams(e.target.value)}/></label><div className="admin-form-actions"><button type="button" className="primary-button" disabled={busy} onClick={()=>void saveSettings()}>Сохранить AI</button></div></div>
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

function UsersPanel({ items, transactions, onItems, onTransactions, onError }: { items:AdminUser[]; transactions:AdminCreditTransaction[]; onItems:(v:AdminUser[])=>void; onTransactions:(v:AdminCreditTransaction[])=>void; onError:(v:string|null)=>void }) {
  const names=useMemo(()=>Object.fromEntries(items.map(u=>[u.id,u.display_name])),[items])
  async function update(user:AdminUser,payload:{status?:'active'|'disabled';role?:UserRole}){try{const saved=await api.adminUpdateUser(user.id,payload);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}}
  async function changed(saved:AdminUser){onItems(items.map(x=>x.id===saved.id?saved:x));try{onTransactions(await api.adminListCreditTransactions())}catch(err){onError(errorText(err))}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Пользователи и кредиты</h2><p>Любое изменение баланса проходит через credit ledger.</p></div></div><div className="admin-card-list">{items.map(user=><article className="admin-list-card admin-user-card" key={user.id}><div><strong>{user.display_name}</strong><span>{user.id}</span><p>{user.credits_balance} кредитов · {user.role} · {user.status}</p></div><div className="admin-user-controls"><select value={user.role} onChange={e=>void update(user,{role:e.target.value as UserRole})}><option value="user">user</option><option value="admin">admin</option><option value="superadmin">superadmin</option></select><select value={user.status} onChange={e=>void update(user,{status:e.target.value as 'active'|'disabled'})}><option value="active">active</option><option value="disabled">disabled</option></select><CreditEditor user={user} onChanged={(saved)=>void changed(saved)} onError={onError}/></div></article>)}</div>
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
  async function action(item:AdminPayment,kind:'sync'|'refund'){setBusy(item.id);onError(null);try{const saved=kind==='sync'?await api.adminReconcilePayment(item.id):await api.adminRefundPayment(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}finally{setBusy(null)}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Платежи</h2><p>Reconciliation и полный возврат выполняются сервером через YooKassa.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Пакет</th><th>Сумма</th><th>Кредиты</th><th>Статус</th><th>Чек</th><th/></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{formatDate(item.created_at)}</td><td><strong>{item.package_code}</strong><small>{item.yookassa_payment_id||item.id}</small></td><td>{formatMoney(item.amount,item.currency)}</td><td>{item.credits}</td><td>{item.status}{item.refund_status?` / refund: ${item.refund_status}`:''}{item.provider_error&&<small className="admin-error-text">{item.provider_error}</small>}</td><td>{item.receipt_email||'—'}</td><td><button disabled={busy!==null} onClick={()=>void action(item,'sync')}>Сверить</button>{item.status==='succeeded'&&item.refund_status!=='succeeded'&&<button disabled={busy!==null} onClick={()=>void action(item,'refund')}>Возврат</button>}</td></tr>)}</tbody></table></div></section>
}

function BroadcastsPanel({items,onItems,onError}:{items:AdminBroadcast[];onItems:(v:AdminBroadcast[])=>void;onError:(v:string|null)=>void}){
  const [text,setText]=useState('')
  const [segment,setSegment]=useState<BroadcastSegment>('all')
  const [scheduled,setScheduled]=useState('')
  const [busy,setBusy]=useState<string|null>(null)
  async function create(){if(!text.trim())return;setBusy('create');try{const iso=scheduled?new Date(scheduled).toISOString():null;const saved=await api.adminCreateBroadcast(text.trim(),segment,iso);onItems([saved,...items]);setText('');setScheduled('')}catch(err){onError(errorText(err))}finally{setBusy(null)}}
  async function action(item:AdminBroadcast,kind:'send'|'retry'|'cancel'){setBusy(item.id);try{const saved=kind==='send'?await api.adminSendBroadcast(item.id):kind==='retry'?await api.adminRetryBroadcast(item.id):await api.adminCancelBroadcast(item.id);onItems(items.map(x=>x.id===saved.id?saved:x))}catch(err){onError(errorText(err))}finally{setBusy(null)}}
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Рассылки</h2><p>Очередь, сегменты, расписание и повторы работают через отдельный worker.</p></div></div><div className="admin-broadcast-compose"><textarea value={text} onChange={e=>setText(e.target.value)} placeholder="Сообщение пользователям Telegram"/><div className="admin-broadcast-options"><select value={segment} onChange={e=>setSegment(e.target.value as BroadcastSegment)}><option value="all">Все активные</option><option value="with_credits">С кредитами</option><option value="without_credits">Без кредитов</option></select><input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)}/><button className="primary-button" disabled={busy!==null||!text.trim()} onClick={()=>void create()}>{scheduled?'Запланировать':'Создать'}</button></div></div><div className="admin-card-list">{items.map(item=><article className="admin-list-card" key={item.id}><div><strong>{item.text}</strong><span>{item.segment} · {item.status} · {item.sent_count}/{item.recipient_count} · ошибок {item.failed_count}</span><p>{item.scheduled_at?`Запланировано: ${formatDate(item.scheduled_at)}`:item.sent_at?`Завершено: ${formatDate(item.sent_at)}`:`Создано: ${formatDate(item.created_at)}`}</p></div><div>{!['sent','canceled','scheduled'].includes(item.status)&&<button disabled={busy!==null} onClick={()=>void action(item,'send')}>В очередь</button>}{item.status==='scheduled'&&<span className="status-pill">Запланирована</span>}{item.failed_count>0&&<button disabled={busy!==null} onClick={()=>void action(item,'retry')}>Повторить ошибки</button>}{!['sent','canceled'].includes(item.status)&&<button disabled={busy!==null} onClick={()=>void action(item,'cancel')}>Отменить</button>}</div></article>)}</div></section>
}

function AuditPanel({items}:{items:AdminAudit[]}){
  return <section className="admin-panel"><div className="admin-panel-title"><div><h2>Аудит</h2><p>Последние действия операторов.</p></div></div><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Дата</th><th>Действие</th><th>Сущность</th><th>Actor</th><th>Детали</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{formatDate(item.created_at)}</td><td>{item.action}</td><td>{item.entity_type}<small>{item.entity_id||''}</small></td><td>{item.actor_user_id||'system'}</td><td><small>{JSON.stringify(item.details)}</small></td></tr>)}</tbody></table></div></section>
}
