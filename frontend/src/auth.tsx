import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'
import type { User } from './types'

type AuthContextValue = {
  user: User | null
  loading: boolean
  error: string | null
  canRetrySession: boolean
  loginWithEmail: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  retrySession: () => void
  clearError: () => void
}

const EXPLICIT_LOGOUT_KEY = 'auroom.explicit_logout'

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
  const [canRetrySession, setCanRetrySession] = useState(false)
  const [bootstrapVersion, setBootstrapVersion] = useState(0)

  useEffect(() => {
    const telegram = window.Telegram?.WebApp
    try {
      telegram?.ready?.()
      telegram?.expand?.()
    } catch { /* old Telegram clients may reject bridge calls */ }

    let cancelled = false
    async function bootstrap() {
      let lastError: unknown = null
      try {
        if (sessionStorage.getItem(EXPLICIT_LOGOUT_KEY) === '1') {
          if (!cancelled) {
            setError('Вы вышли из аккаунта. Можно безопасно войти снова.')
            setCanRetrySession(true)
          }
          return
        }
        if (api.hasStoredSession()) {
          try {
            const current = await api.getMe()
            if (!cancelled) {
              setUser(current)
              setError(null)
              setCanRetrySession(false)
            }
            return
          } catch (sessionError) {
            lastError = sessionError
            if (shouldRetryTelegramAuth(sessionError)) {
              if (!cancelled) {
                setError(messageOf(sessionError))
                setCanRetrySession(true)
              }
              return
            }
            api.clearTokens()
          }
        } else {
          try {
            const restored = await api.restoreSession()
            if (restored) {
              if (!cancelled) {
                  setUser(restored)
                  setError(null)
                  setCanRetrySession(false)
              }
              return
            }
          } catch (sessionError) {
            lastError = sessionError
            if (shouldRetryTelegramAuth(sessionError)) {
              if (!cancelled) {
                setError(messageOf(sessionError))
                setCanRetrySession(true)
              }
              return
            }
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
              setCanRetrySession(false)
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
  }, [bootstrapVersion])

  const loginWithEmail = useCallback(async (email: string, password: string) => {
    setError(null)
    setCanRetrySession(false)
    try {
      const pair = await api.login(email, password)
      sessionStorage.removeItem(EXPLICIT_LOGOUT_KEY)
      setUser(pair.user)
    } catch (loginError) {
      setError(messageOf(loginError))
      throw loginError
    }
  }, [])

  const signOut = useCallback(async () => {
    sessionStorage.setItem(EXPLICIT_LOGOUT_KEY, '1')
    setUser(null)
    setError('Вы вышли из аккаунта. Можно безопасно войти снова.')
    setCanRetrySession(true)
    try {
      await api.logout()
    } catch {
      // The server-side refresh cookie expires independently. Local logout must still complete.
    }
  }, [])

  const retrySession = useCallback(() => {
    sessionStorage.removeItem(EXPLICIT_LOGOUT_KEY)
    setError(null)
    setCanRetrySession(false)
    setLoading(true)
    setBootstrapVersion((value) => value + 1)
  }, [])

  const value = useMemo(
    () => ({ user, loading, error, canRetrySession, loginWithEmail, signOut, retrySession, clearError: () => setError(null) }),
    [user, loading, error, canRetrySession, loginWithEmail, signOut, retrySession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
