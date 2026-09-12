import '../telegram-fullscreen.css'

export function TelegramFullscreenButton() {
  if (!window.Telegram?.WebApp) return null

  function requestFullscreen() {
    const telegram = window.Telegram?.WebApp
    if (!telegram) return
    try {
      telegram.expand?.()
      telegram.requestFullscreen?.()
    } catch {
      // Older Telegram clients may only support expand().
    }
  }

  return (
    <button
      className="telegram-fullscreen-button"
      type="button"
      title="На весь экран"
      aria-label="Открыть на весь экран"
      onClick={requestFullscreen}
    >
      <span aria-hidden="true">⛶</span>
      <span>На весь экран</span>
    </button>
  )
}
