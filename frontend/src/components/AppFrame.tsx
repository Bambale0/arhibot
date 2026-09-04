import type { ReactNode } from 'react'
import { useAuth } from '../auth'
import { HistoryIcon, HomeIcon, IdeaIcon, LogOutIcon, PlusIcon, UserIcon } from './Icons'

export type AppSection = 'home' | 'ideas' | 'create' | 'history' | 'profile'

const items: { id: AppSection; label: string; icon: typeof HomeIcon }[] = [
  { id: 'home', label: 'Главная', icon: HomeIcon },
  { id: 'ideas', label: 'Идеи', icon: IdeaIcon },
  { id: 'create', label: 'Создать', icon: PlusIcon },
  { id: 'history', label: 'История', icon: HistoryIcon },
  { id: 'profile', label: 'Профиль', icon: UserIcon },
]

export function AppFrame({ active, onNavigate, children }: { active: AppSection; onNavigate: (section: AppSection) => void; children: ReactNode }) {
  const { user, signOut } = useAuth()
  return (
    <main className="app-shell with-bottom-nav">
      <header className="topbar">
        <button className="brand-button" onClick={() => onNavigate('home')}>
          <span className="wordmark"><span className="wordmark-dot" />AuRoom</span>
        </button>
        <div className="topbar-user">
          <div className="avatar">{user?.display_name?.slice(0, 1).toUpperCase() || 'A'}</div>
          <span className="desktop-user-name">{user?.display_name}</span>
          <button className="icon-button subtle" title="Выйти" onClick={() => void signOut()}><LogOutIcon /></button>
        </div>
      </header>
      {children}
      <nav className="bottom-nav" aria-label="Основная навигация">
        {items.map((item) => {
          const Icon = item.icon
          return <button key={item.id} className={active === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)}><Icon /><span>{item.label}</span></button>
        })}
      </nav>
    </main>
  )
}
