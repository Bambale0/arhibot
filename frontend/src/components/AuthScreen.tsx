import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'
import { HomeIcon, PlanIcon, RoomIcon, SiteIcon, SparkIcon } from './Icons'

export function AuthScreen() {
  const { loginWithEmail, error, clearError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    clearError()
    setBusy(true)
    try {
      await loginWithEmail(email.trim(), password)
    } catch {
      // Auth provider exposes the API error in the next render.
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand-panel">
        <div className="brand-mark"><HomeIcon /></div>
        <div className="auth-brand-copy">
          <span className="eyebrow">AUROOM · AI DESIGN</span>
          <h1>Дом и интерьер<br />в одном пространстве.</h1>
          <p>AuRoom помогает пройти путь от планировки и участка до фасада и дизайна помещений.</p>
        </div>
        <div className="auth-feature-row">
          <div><PlanIcon /><span>Планировки</span></div>
          <div><HomeIcon /><span>Фасады</span></div>
          <div><SiteIcon /><span>Участок</span></div>
          <div><RoomIcon /><span>Интерьеры</span></div>
        </div>
      </section>

      <section className="auth-form-panel">
        <div className="auth-card">
          <div className="wordmark"><span className="wordmark-dot" />AuRoom</div>
          <div className="auth-heading">
            <h2>Вход</h2>
            <p>В Telegram Mini App вход выполняется автоматически. Веб-вход оставлен для тестового аккаунта.</p>
          </div>

          <form onSubmit={submit} className="auth-form">
            <label>Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} required type="email" placeholder="name@example.com" autoComplete="email" />
            </label>
            <label>Пароль
              <input value={password} onChange={(e) => setPassword(e.target.value)} required type="password" minLength={1} placeholder="Ваш пароль" autoComplete="current-password" />
            </label>
            {error && <div className="inline-error">{error}</div>}
            <button className="primary-button auth-submit" disabled={busy} type="submit">
              {busy ? 'Подождите…' : 'Войти'}
            </button>
          </form>
          <p className="telegram-hint"><SparkIcon /> Новые пользователи заходят через Telegram — отдельной регистрации в AuRoom нет.</p>
        </div>
      </section>
    </main>
  )
}
