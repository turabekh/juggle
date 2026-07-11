import { describe, expect, it } from 'vitest'

import { storage } from '@/lib/storage'

// jsdom provides window.localStorage, so the shim proxies it here; the in-memory
// SSR fallback path is exercised implicitly on the server (no window).
describe('storage shim', () => {
  it('sets, gets, and removes values', () => {
    expect(storage.get('k')).toBeNull()
    storage.set('k', 'v')
    expect(storage.get('k')).toBe('v')
    expect(localStorage.getItem('k')).toBe('v')
    storage.remove('k')
    expect(storage.get('k')).toBeNull()
  })
})
