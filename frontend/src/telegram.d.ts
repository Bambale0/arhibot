export {}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData?: string
        ready?: () => void
        expand?: () => void
        version?: string
        isFullscreen?: boolean
        requestFullscreen?: () => void
        exitFullscreen?: () => void
        onEvent?: (eventType: string, callback: (...args: unknown[]) => void) => void
        offEvent?: (eventType: string, callback: (...args: unknown[]) => void) => void
        colorScheme?: 'light' | 'dark'
        setHeaderColor?: (color: string) => void
        setBackgroundColor?: (color: string) => void
      }
    }
  }
}
