import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import * as api from '../api'
import type { Asset, Generation, GenerationMode, Project } from '../types'
import { BackIcon, HomeIcon, ImageIcon, PlanIcon, RoomIcon, SiteIcon, SparkIcon, TrashIcon, UploadIcon } from './Icons'

const modes: { id: GenerationMode; title: string; text: string; icon: typeof HomeIcon }[] = [
  { id: 'floor_plan', title: 'Планировка', text: 'Функциональная схема дома по параметрам и пожеланиям.', icon: PlanIcon },
  { id: 'facade', title: 'Фасад', text: 'Новый внешний образ дома с сохранением основной геометрии.', icon: HomeIcon },
  { id: 'master_plan', title: 'Мастер-план', text: 'Организация дома и ключевых зон на участке.', icon: SiteIcon },
  { id: 'interior', title: 'Интерьер', text: 'Дизайн помещения по исходному пространству и пожеланиям.', icon: RoomIcon },
]
const modeHeading: Record<GenerationMode, string> = {
  floor_plan: 'Спроектируем планировку дома', facade: 'Создадим внешний облик дома', master_plan: 'Соберём мастер-план участка', interior: 'Разработаем дизайн помещения',
}
const statusText: Record<Generation['status'], string> = { queued: 'В очереди', processing: 'AuRoom создаёт вариант…', completed: 'Готово', failed: 'Не удалось создать' }
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ` }
function sleep(ms: number) { return new Promise((resolve) => setTimeout(resolve, ms)) }

export function WorkspaceScreen({ project, initialMode, initialPrompt, initialAsset, onBack, onProjectChange }: { project: Project; initialMode?: GenerationMode; initialPrompt?: string; initialAsset?: Asset | null; onBack: () => void; onProjectChange: (project: Project) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [asset, setAsset] = useState<Asset | null>(initialAsset || null)
  const [mode, setMode] = useState<GenerationMode>(initialMode || 'floor_plan')
  const [prompt, setPrompt] = useState(initialPrompt || '')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [generationBusy, setGenerationBusy] = useState(false)
  const [generation, setGeneration] = useState<Generation | null>(null)
  const requiresAsset = mode === 'facade' || mode === 'interior'
  const canGenerate = !generationBusy && (!requiresAsset || Boolean(asset))

  async function upload(file?: File) {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Поддерживаются JPEG, PNG и WebP.'); return }
    setUploading(true); setError(null)
    try { const uploaded = await api.uploadAsset(project.id, file, 'generation_input'); setAsset(uploaded); setGeneration(null) }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось загрузить изображение') }
    finally { setUploading(false) }
  }
  function handleInput(e: ChangeEvent<HTMLInputElement>) { void upload(e.target.files?.[0]) }
  function handleDrop(e: DragEvent) { e.preventDefault(); setDragOver(false); void upload(e.dataTransfer.files?.[0]) }
  async function removeAsset() {
    if (!asset || generationBusy) return
    const current = asset; setAsset(null); setGeneration(null)
    try { await api.deleteAsset(current.id) } catch { setAsset(current) }
  }

  async function runGeneration() {
    if (!canGenerate) return
    setError(null); setGeneration(null); setGenerationBusy(true)
    try {
      let current = await api.createGeneration({ project_id: project.id, input_asset_id: asset?.id || null, type: mode, prompt })
      setGeneration(current)
      const deadline = Date.now() + 4 * 60 * 1000
      while (current.status === 'queued' || current.status === 'processing') {
        if (Date.now() > deadline) throw new Error('Генерация занимает больше обычного. Она останется в истории — проверьте результат позже.')
        await sleep(2000); current = await api.getGeneration(current.id); setGeneration(current)
      }
      if (current.status === 'failed') throw new Error(current.error || 'AI-модель не смогла завершить генерацию. Кредиты за технический сбой возвращаются автоматически.')
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 409) setError('Недостаточно кредитов. Пополните баланс в Профиле.')
      else if (err instanceof api.ApiError && err.status === 503) setError('Генерация пока не настроена: проверьте Nexus и стоимость сценария в веб-админке.')
      else setError(err instanceof Error ? err.message : 'Не удалось запустить генерацию')
    } finally { setGenerationBusy(false) }
  }

  async function archiveProject() {
    try { onProjectChange(await api.updateProject(project.id, { status: project.status === 'archived' ? 'active' : 'archived' })) }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось обновить проект') }
  }

  const meta = [project.context.house_area_m2 ? `${project.context.house_area_m2} м²` : null, project.context.floors ? `${project.context.floors} этажа` : null, project.context.architecture_style || null].filter(Boolean)
  const sourceLabel = mode === 'floor_plan' ? 'Референс или схема · необязательно' : mode === 'master_plan' ? 'Фото или схема участка · необязательно' : 'Исходное изображение · обязательно'
  const resultReady = generation?.status === 'completed' && generation.output_asset

  return <main className="workspace-shell">
    <aside className="workspace-sidebar"><button className="back-button" onClick={onBack}><BackIcon /> Назад в AuRoom</button><div className="sidebar-project"><span className="eyebrow">ПРОЕКТ</span><h2>{project.name}</h2>{meta.length ? <div className="project-meta-list">{meta.map((item) => <span key={String(item)}>{item}</span>)}</div> : <p>Параметры пока не заполнены.</p>}</div><div className="sidebar-progress"><span>Рабочий процесс</span><div className="progress-item done"><b>1</b><div><strong>Проект</strong><small>Создан</small></div></div><div className={`progress-item ${asset || !requiresAsset ? 'done' : 'current'}`}><b>2</b><div><strong>Исходник</strong><small>{asset ? 'Загружен' : requiresAsset ? 'Нужен референс' : 'Необязателен'}</small></div></div><div className={`progress-item ${asset || !requiresAsset ? 'current' : ''}`}><b>3</b><div><strong>Генерация</strong><small>{generation ? statusText[generation.status] : 'Сценарий и пожелания'}</small></div></div></div><button className="sidebar-text-button" onClick={() => void archiveProject()}>{project.status === 'archived' ? 'Вернуть в активные' : 'Архивировать проект'}</button></aside>
    <section className="workspace-main"><header className="workspace-mobile-header"><button className="icon-button" onClick={onBack}><BackIcon /></button><strong>{project.name}</strong><span /></header><div className="workspace-content">
      <div className="workspace-heading"><span className="eyebrow">AUROOM · НОВАЯ ГЕНЕРАЦИЯ</span><h1>{modeHeading[mode]}</h1><p>{requiresAsset ? 'Добавьте исходник и опишите результат.' : 'Можно генерировать по параметрам проекта и текстовому ТЗ. Референс — опционально.'}</p></div>
      <section className="work-section"><div className="section-number">01</div><div className="section-body"><div className="section-title"><h3>{sourceLabel}</h3><span>JPEG · PNG · WebP · до 20 МБ</span></div>{!asset ? <button className={`upload-zone ${dragOver ? 'drag-over' : ''}`} onClick={() => inputRef.current?.click()} onDragOver={(e) => {e.preventDefault(); setDragOver(true)}} onDragLeave={() => setDragOver(false)} onDrop={handleDrop} disabled={uploading || generationBusy}><div className="upload-icon"><UploadIcon /></div><strong>{uploading ? 'Загружаем…' : requiresAsset ? 'Добавьте исходное изображение' : 'Добавить референс (необязательно)'}</strong><span>{uploading ? 'Проверяем изображение и сохраняем на сервере' : 'Нажмите или перетащите файл'}</span></button> : <div className="asset-preview"><img src={asset.url} alt="Исходное изображение" /><div className="asset-overlay"><div><ImageIcon/><span><strong>{asset.original_filename || 'Изображение'}</strong><small>{asset.width}×{asset.height} · {formatBytes(asset.size_bytes)}</small></span></div><button className="icon-button danger" onClick={() => void removeAsset()} disabled={generationBusy} title="Удалить"><TrashIcon/></button></div></div>}<input hidden ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={handleInput} /></div></section>
      <section className="work-section"><div className="section-number">02</div><div className="section-body"><div className="section-title"><h3>Сценарий</h3><span>4 функции AuRoom</span></div><div className="mode-grid four-modes">{modes.map((item) => { const Icon=item.icon; return <button key={item.id} disabled={generationBusy} className={`mode-card ${mode === item.id ? 'selected' : ''}`} onClick={() => {setMode(item.id); setGeneration(null)}}><span className="mode-icon"><Icon/></span><strong>{item.title}</strong><p>{item.text}</p><span className="radio-dot" /></button>})}</div></div></section>
      <section className="work-section"><div className="section-number">03</div><div className="section-body"><div className="section-title"><h3>Пожелания</h3><span>Необязательно</span></div><textarea className="prompt-input" disabled={generationBusy} value={prompt} onChange={(e) => {setPrompt(e.target.value); setGeneration(null)}} placeholder="Например: современный минимализм, натуральные материалы, три спальни, приватная терраса…" maxLength={4000}/><div className="prompt-footer"><span>{prompt.length}/4000</span></div></div></section>
      {error && <div className="banner-error workspace-error">{error}<button onClick={() => setError(null)}>Закрыть</button></div>}
      {generation && <section className="generation-result"><div className="generation-result-head"><div><span className="eyebrow">AUROOM AI</span><h3>{statusText[generation.status]}</h3></div><span className="status-pill">{generation.credits_charged} кр. · {generation.fallback_used ? 'резервная модель' : generation.status === 'completed' ? 'готово' : 'AI'}</span></div>{resultReady ? <><div className="generation-result-image"><img src={generation.output_asset!.url} alt="Результат AuRoom"/></div><p>Результат сохранён на сервере и доступен в истории.</p></> : <p>{generation.status === 'failed' ? (generation.error || 'Генерация завершилась с ошибкой.') : 'Задача отправлена в AI. При техническом сбое зарезервированные кредиты вернутся автоматически.'}</p>}</section>}
      <div className="generate-bar"><div><SparkIcon/><span><strong>{canGenerate ? (generationBusy ? 'AuRoom создаёт изображение…' : 'Готово к генерации') : 'Для этого сценария нужен исходник'}</strong><small>Стоимость сценария задаётся в веб-админке</small></span></div><button className="primary-button generate-button" disabled={!canGenerate} onClick={() => void runGeneration()}>{generationBusy ? 'Генерируем…' : 'Создать'} <SparkIcon/></button></div>
    </div></section>
  </main>
}
