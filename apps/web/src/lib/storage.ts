// SSR-safe key/value storage. On the client it proxies localStorage; during
// server-side rendering (no `window`) it falls back to an in-memory map so store
// setup and route guards never touch a missing localStorage.

const memory: Record<string, string> = {}
const hasLocalStorage = typeof window !== 'undefined' && !!window.localStorage

export const storage = {
  get(key: string): string | null {
    return hasLocalStorage ? window.localStorage.getItem(key) : (memory[key] ?? null)
  },
  set(key: string, value: string): void {
    if (hasLocalStorage) window.localStorage.setItem(key, value)
    else memory[key] = value
  },
  remove(key: string): void {
    if (hasLocalStorage) window.localStorage.removeItem(key)
    else delete memory[key]
  },
}
