import { useCallback, useEffect, useRef, useState } from 'react'
import '../telegram-fullscreen.css'

function FullscreenIcon({ active }: { active: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {active ? <>
        <path d="M9 3v4a2 2 0 0 1-2 2H3" />
        <path d="M15 3v4a2 2 0 0 0 2 2h4" />
        <path d="M9 21v-4a2 2 0 0 0-2-2H3" />
        <path d="M15 21v-4a2 2 0 0 1 2-2h4" />
      </> : <>
        <path d="M8 3H5a2 2 0 0 0-2 2v3" />
        <path d="M16 3h3a2 2 0 0 1 2 2v3" />
        <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
        <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
      </>}
    </svg>
  )
}

export function TelegramFullscreenButton() {
  const webApp = window.Telegram?.WebApp
  const [isFullscreen, setIsFullscreen] = useState(() => Boolean(webApp?.isFullscreen))
  const lastThreeFingerToggleAt = useRef(0)

  useEffect(() => {
    if (!webApp?.requestFullscreen) return
    const syncFullscreen = () => setIsFullscreen(Boolean(webApp.isFullscreen))
    syncFullscreen()
    webApp.onEvent?.('fullscreenChanged', syncFullscreen)
    webApp.onEvent?.('fullscreenFailed', syncFullscreen)
    return () => {
      webApp.offEvent?.('fullscreenChanged', syncFullscreen)
      webApp.offEvent?.('fullscreenFailed', syncFullscreen)
    }
  }, [webApp])

  const toggleFullscreen = useCallback(() => {
    if (!webApp?.requestFullscreen) return
    try {
      const active = webApp.isFullscreen ?? isFullscreen
      if (active) {
        if (!webApp.exitFullscreen) return
        webApp.exitFullscreen()
        setIsFullscreen(false)
        return
      }
      webApp.expand?.()
      webApp.requestFullscreen()
      setIsFullscreen(true)
    } catch {
      // Telegram can reject fullscreen transiently; the Mini App stays usable.
    }
  }, [isFullscreen, webApp])

  useEffect(() => {
    if (!webApp?.requestFullscreen) return
    const handleThreeFingerTouch = (event: TouchEvent) => {
      if (event.touches.length !== 3) return
      const now = Date.now()
      if (now - lastThreeFingerToggleAt.current < 500) return
      lastThreeFingerToggleAt.current = now
      toggleFullscreen()
    }
    document.addEventListener('touchstart', handleThreeFingerTouch, { passive: true })
    return () => document.removeEventListener('touchstart', handleThreeFingerTouch)
  }, [toggleFullscreen, webApp])

  if (!webApp?.requestFullscreen) return null
  const label = isFullscreen ? 'Выйти из полноэкранного режима' : 'Открыть на весь экран'

  return (
    <button
      className="telegram-fullscreen-button"
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={isFullscreen}
      onClick={toggleFullscreen}
    >
      <FullscreenIcon active={isFullscreen} />
    </button>
  )
}
