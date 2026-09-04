import { useAuth } from '../auth'
import { LogOutIcon, UserIcon } from './Icons'

export function ProfileScreen() {
  const { user, signOut } = useAuth()
  return (
    <section className="page-content profile-page">
      <div className="page-heading-row"><div><span className="eyebrow">АККАУНТ AUROOM</span><h1>Профиль</h1><p>Данные текущего пользователя и доступ к сессии.</p></div></div>
      <div className="profile-card">
        <div className="profile-avatar"><UserIcon /></div>
        <div className="profile-main"><h2>{user?.display_name || 'Пользователь AuRoom'}</h2><span className="status-pill">Активен</span></div>
        <dl className="profile-details"><div><dt>ID</dt><dd>{user?.id}</dd></div><div><dt>Создан</dt><dd>{user?.created_at ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long' }).format(new Date(user.created_at)) : '—'}</dd></div><div><dt>Режим</dt><dd>Telegram Mini App / Web sandbox</dd></div></dl>
        <button className="secondary-button profile-logout" onClick={() => void signOut()}><LogOutIcon /> Выйти</button>
      </div>
    </section>
  )
}
