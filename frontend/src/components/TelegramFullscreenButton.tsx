import '../telegram-fullscreen.css'

function FullscreenIcon() {
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
      <path d="M8 3H5a2 2 0 0 0-2 2v3" />
      <path d="M16 3h3a2 2 0 0 1 2 2v3" />
      <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
      <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
    </svg>
  )
}

export function TelegramFullscreenButton() {
  const telegram = window.Telegram?.WebApp
  if (!telegram?.requestFullscreen) return null

  function requestFullscreen() {
    try {
      telegram.expand?.()
      telegram.requestFullscreen?.()
    } catch {
      // Telegram clients can reject fullscreen transiently; keep the app usable.
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
      <FullscreenIcon />
    </button>
  )
}
