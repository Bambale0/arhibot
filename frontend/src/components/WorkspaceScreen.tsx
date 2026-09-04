import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import * as api from '../api'
import type { Asset, DemoGeneration, GenerationMode, Project } from '../types'
import { BackIcon, HomeIcon, ImageIcon, RoomIcon, SparkIcon, TrashIcon, UploadIcon } from './Icons'

const modes: { id: GenerationMode; title: string; text: string; icon: typeof HomeIcon }[] = [
  { id: 'facade', title: 'Фасад', text: 'Новый образ дома с сохранением геометрии.', icon: HomeIcon },
  { id: 'interior', title: 'Интерьер', text: 'Концепция комнаты по исходному пространству.', icon: RoomIcon },
  { id: 'redesign', title: 'Редизайн', text: 'Обновить существующий интерьер без стройки с нуля.', icon: SparkIcon },
]

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

export function WorkspaceScreen({ project, onBack, onProjectChange }: { project: Project; onBack: () => void; onProjectChange: (project: Project) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [asset, setAsset] = useState<Asset | null>(null)
  const [mode, setMode] = useState<GenerationMode>('facade')
  const [prompt, setPrompt] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [demoBusy, setDemoBusy] = useState(false)
  const [demoResult, setDemoResult] = useState<DemoGeneration | null>(null)
  const demoEnabled = import.meta.env.VITE_DEMO_GENERATION === 'true'

  async function upload(file?: File) {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Поддерживаются JPEG, PNG и WebP.')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const uploaded = await api.uploadAsset(project.id, file, 'generation_input')
      setAsset(uploaded)
      setDemoResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить изображение')
    } finally {
      setUploading(false)
    }
  }

  function handleInput(e: ChangeEvent<HTMLInputElement>) { void upload(e.target.files?.[0]) }
  function handleDrop(e: DragEvent) { e.preventDefault(); setDragOver(false); void upload(e.dataTransfer.files?.[0]) }

  async function removeAsset() {
    if (!asset) return
    const current = asset
    setAsset(null)
    setDemoResult(null)
    try { await api.deleteAsset(current.id) } catch { setAsset(current) }
  }

  async function runDemo() {
    if (!asset) return
    if (!demoEnabled) {
      setError('Интерфейс готов. Реальную генерацию подключим к Generation API следующим backend-срезом.')
      return
    }
    setError(null)
    setDemoBusy(true)
    await new Promise((resolve) => setTimeout(resolve, 1200))
    setDemoResult({ id: crypto.randomUUID(), mode, prompt, sourceUrl: asset.url, createdAt: new Date().toISOString() })
    setDemoBusy(false)
  }

  async function archiveProject() {
    try {
      const updated = await api.updateProject(project.id, { status: project.status === 'archived' ? 'active' : 'archived' })
      onProjectChange(updated)
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось обновить проект') }
  }

  const meta = [project.context.house_area_m2 ? `${project.context.house_area_m2} м²` : null, project.context.floors ? `${project.context.floors} этажа` : null, project.context.architecture_style || null].filter(Boolean)

  return (
    <main className="workspace-shell">
      <aside className="workspace-sidebar">
        <button className="back-button" onClick={onBack}><BackIcon /> Все проекты</button>
        <div className="sidebar-project"><span className="eyebrow">ПРОЕКТ</span><h2>{project.name}</h2>{meta.length ? <div className="project-meta-list">{meta.map((item) => <span key={String(item)}>{item}</span>)}</div> : <p>Параметры пока не заполнены.</p>}</div>
        <div className="sidebar-progress"><span>Рабочий процесс</span><div className="progress-item done"><b>1</b><div><strong>Проект</strong><small>Создан</small></div></div><div className={`progress-item ${asset ? 'done' : 'current'}`}><b>2</b><div><strong>Исходник</strong><small>{asset ? 'Загружен' : 'Нужна фотография'}</small></div></div><div className={`progress-item ${asset ? 'current' : ''}`}><b>3</b><div><strong>Концепт</strong><small>Сценарий и пожелания</small></div></div></div>
        <button className="sidebar-text-button" onClick={() => void archiveProject()}>{project.status === 'archived' ? 'Вернуть в активные' : 'Архивировать проект'}</button>
      </aside>

      <section className="workspace-main">
        <header className="workspace-mobile-header"><button className="icon-button" onClick={onBack}><BackIcon /></button><strong>{project.name}</strong><span /></header>
        <div className="workspace-content">
          <div className="workspace-heading"><span className="eyebrow">НОВЫЙ КОНЦЕПТ</span><h1>Как изменим пространство?</h1><p>Загрузите исходное фото, выберите сценарий и добавьте пожелания.</p></div>

          <section className="work-section"><div className="section-number">01</div><div className="section-body"><div className="section-title"><h3>Исходное изображение</h3><span>JPEG · PNG · WebP · до 20 МБ</span></div>
            {!asset ? (
              <button className={`upload-zone ${dragOver ? 'drag-over' : ''}`} onClick={() => inputRef.current?.click()} onDragOver={(e) => {e.preventDefault(); setDragOver(true)}} onDragLeave={() => setDragOver(false)} onDrop={handleDrop} disabled={uploading}>
                <div className="upload-icon"><UploadIcon /></div><strong>{uploading ? 'Загружаем…' : 'Перетащите фото сюда'}</strong><span>{uploading ? 'Проверяем изображение и сохраняем на сервере' : 'или нажмите, чтобы выбрать файл'}</span>
              </button>
            ) : (
              <div className="asset-preview"><img src={asset.url} alt="Исходное изображение" /><div className="asset-overlay"><div><ImageIcon/><span><strong>{asset.original_filename || 'Изображение'}</strong><small>{asset.width}×{asset.height} · {formatBytes(asset.size_bytes)}</small></span></div><button className="icon-button danger" onClick={() => void removeAsset()} title="Удалить"><TrashIcon/></button></div></div>
            )}
            <input hidden ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={handleInput} />
          </div></section>

          <section className="work-section"><div className="section-number">02</div><div className="section-body"><div className="section-title"><h3>Сценарий</h3><span>Выберите один</span></div><div className="mode-grid">{modes.map((item) => { const Icon=item.icon; return <button key={item.id} className={`mode-card ${mode === item.id ? 'selected' : ''}`} onClick={() => {setMode(item.id); setDemoResult(null)}}><span className="mode-icon"><Icon/></span><strong>{item.title}</strong><p>{item.text}</p><span className="radio-dot" /></button>})}</div></div></section>

          <section className="work-section"><div className="section-number">03</div><div className="section-body"><div className="section-title"><h3>Пожелания</h3><span>Необязательно</span></div><textarea className="prompt-input" value={prompt} onChange={(e) => {setPrompt(e.target.value); setDemoResult(null)}} placeholder="Например: тёплый минимализм, натуральный камень, больше дерева, мягкий вечерний свет…" maxLength={2000}/><div className="prompt-footer"><span>{prompt.length}/2000</span><button onClick={() => setPrompt('Современный минимализм, натуральные материалы, тёплая нейтральная палитра, реалистичное освещение.')}>Заполнить пример</button></div></div></section>

          {error && <div className="banner-error workspace-error">{error}<button onClick={() => setError(null)}>Закрыть</button></div>}

          {demoResult && <section className="demo-result"><div className="demo-result-head"><div><span className="eyebrow">DEMO MODE</span><h3>UX генерации готов</h3></div><span className="status-pill">Демо</span></div><div className="demo-result-image"><img src={demoResult.sourceUrl} alt="Демонстрационный результат"/><div className="demo-watermark">DEMO · здесь будет AI output</div></div><p>Это не AI-результат: в demo-mode показывается исходник, чтобы проверить клиентский flow до подключения Generation API.</p></section>}

          <div className="generate-bar"><div><SparkIcon/><span><strong>{asset ? 'Всё готово для концепта' : 'Сначала добавьте исходное фото'}</strong><small>{demoEnabled ? 'Включён безопасный demo-mode' : 'Generation API будет следующим backend-срезом'}</small></span></div><button className="primary-button generate-button" disabled={!asset || demoBusy} onClick={() => void runDemo()}>{demoBusy ? 'Готовим…' : demoEnabled ? 'Показать demo flow' : 'Создать концепт'} <SparkIcon/></button></div>
        </div>
      </section>
    </main>
  )
}
