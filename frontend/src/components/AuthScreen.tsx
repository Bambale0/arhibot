import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'
import { HomeIcon, SparkIcon } from './Icons'

export function AuthScreen() {
  const { loginWithEmail, registerWithEmail, error, clearError } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const appName = import.meta.env.VITE_APP_NAME || 'ArchiAI'

  async function submit(event: FormEvent) {
    event.preventDefault()
    clearError()
    setBusy(true)
    try {
      if (mode === 'login') await loginWithEmail(email.trim(), password)
      else await registerWithEmail(email.trim(), password, displayName.trim())
    } catch {
      // Auth provider/API surfaces the actual error in the next render only for bootstrap;
      // show a safe inline fallback for submit errors.
    } finally {
      setBusy(false)
    }
  }

  function switchMode(next: 'login' | 'register') {
    clearError()
    setMode(next)
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand-panel">
        <div className="brand-mark"><HomeIcon /></div>
        <div className="auth-brand-copy">
          <span className="eyebrow">AI DESIGN STUDIO</span>
          <h1>Увидьте пространство<br />до начала ремонта.</h1>
          <p>Загрузите фотографию дома или комнаты — получите направление для фасада и интерьера в одном рабочем пространстве.</p>
        </div>
        <div className="auth-feature-row">
          <div><SparkIcon /><span>Фасады</span></div>
          <div><SparkIcon /><span>Интерьеры</span></div>
          <div><SparkIcon /><span>Редизайн</span></div>
        </div>
      </section>

      <section className="auth-form-panel">
        <div className="auth-card">
          <div className="wordmark"><span className="wordmark-dot" />{appName}</div>
          <div className="auth-heading">
            <h2>{mode === 'login' ? 'С возвращением' : 'Создать аккаунт'}</h2>
            <p>{mode === 'login' ? 'Войдите, чтобы продолжить работу над проектами.' : 'Один аккаунт для всех архитектурных проектов.'}</p>
          </div>

          <div className="segmented">
            <button className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>Вход</button>
            <button className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>Регистрация</button>
          </div>

          <form onSubmit={submit} className="auth-form">
            {mode === 'register' && (
              <label>Имя
                <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required minLength={1} maxLength={120} placeholder="Игорь" autoComplete="name" />
              </label>
            )}
            <label>Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} required type="email" placeholder="name@example.com" autoComplete="email" />
            </label>
            <label>Пароль
              <input value={password} onChange={(e) => setPassword(e.target.value)} required type="password" minLength={mode === 'register' ? 10 : 1} placeholder={mode === 'register' ? 'Минимум 10 символов' : 'Ваш пароль'} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <button className="primary-button auth-submit" disabled={busy} type="submit">
              {busy ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
            </button>
          </form>
          <p className="telegram-hint">В Telegram Mini App авторизация произойдёт автоматически.</p>
        </div>
      </section>
    </main>
  )
}
