import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'
import type { User } from './types'

type AuthContextValue = {
  user: User | null
  loading: boolean
  error: string | null
  loginWithEmail: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : 'Что-то пошло не так'
}

function shouldRetryTelegramAuth(error: unknown) {
  if (!(error instanceof api.ApiError)) return true
  return error.status === 408 || error.status === 429 || error.status >= 500
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const telegram = window.Telegram?.WebApp
    telegram?.ready?.()
    telegram?.expand?.()

    let cancelled = false
    async function bootstrap() {
      let lastError: unknown = null
      try {
        if (api.hasStoredSession()) {
          try {
            const current = await api.getMe()
            if (!cancelled) {
              setUser(current)
              setError(null)
            }
            return
          } catch (sessionError) {
            lastError = sessionError
            api.clearTokens()
          }
        }

        const initData = telegram?.initData?.trim()
        if (!initData) {
          if (lastError && !cancelled) setError(messageOf(lastError))
          return
        }

        for (let attempt = 0; attempt < 4; attempt += 1) {
          try {
            const pair = await api.loginTelegram(initData)
            if (!cancelled) {
              setUser(pair.user)
              setError(null)
            }
            return
          } catch (telegramError) {
            lastError = telegramError
            api.clearTokens()
            const retry = shouldRetryTelegramAuth(telegramError) && attempt < 3
            if (!retry) break
            await wait(800 * (attempt + 1))
            if (cancelled) return
          }
        }

        if (!cancelled && lastError) setError(messageOf(lastError))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const loginWithEmail = useCallback(async (email: string, password: string) => {
    setError(null)
    try {
      const pair = await api.login(email, password)
      setUser(pair.user)
    } catch (loginError) {
      setError(messageOf(loginError))
      throw loginError
    }
  }, [])

  const signOut = useCallback(async () => {
    await api.logout()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, error, loginWithEmail, signOut, clearError: () => setError(null) }),
    [user, loading, error, loginWithEmail, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
