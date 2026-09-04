import type { DemoGeneration } from './types'

const KEY = 'auroom.demo_history'

export function loadDemoHistory(): DemoGeneration[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function appendDemoHistory(item: DemoGeneration) {
  const next = [item, ...loadDemoHistory().filter((entry) => entry.id !== item.id)].slice(0, 100)
  localStorage.setItem(KEY, JSON.stringify(next))
}

export function clearDemoHistory() {
  localStorage.removeItem(KEY)
}
