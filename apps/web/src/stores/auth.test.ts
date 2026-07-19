import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Mock the api layer: the auth store calls api.auth.me()/logout() and the token
// setters. Keep storage + decodeJwt real (jsdom localStorage; base64 JWT parse).
vi.mock('@/lib/api', () => ({
  api: { auth: { me: vi.fn(), logout: vi.fn().mockResolvedValue(undefined) } },
  configureAuth: vi.fn(),
  setAuthToken: vi.fn(),
  setRefreshToken: vi.fn(),
}))

import { api, setRefreshToken } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const me = vi.mocked(api.auth.me)
const REFRESH_KEY = 'juggle.refresh'
const ADMIN_BACKUP_KEY = 'juggle.adminToken'
const ADMIN_REFRESH_BACKUP_KEY = 'juggle.adminRefresh'

/** A fake, unsigned JWT — decodeJwt only base64-decodes the payload. */
function jwt(payload: Record<string, unknown>): string {
  return `h.${btoa(JSON.stringify(payload))}.s`
}

const ADMIN_TOKEN = jwt({ sub: 'admin-1', adm: true })
const IMP_TOKEN = jwt({ sub: 'target-1', imp: 'admin-1', mode: 'act_as', isid: 's1' })
const CREATED = '2026-01-01T00:00:00Z'
const ADMIN_USER = { id: 'admin-1', is_admin: true, full_name: 'Ops', email: 'a@x.io', created_at: CREATED }
const TARGET_USER = { id: 'target-1', is_admin: false, full_name: 'Pat', email: 'p@x.io', created_at: CREATED }

describe('auth store — impersonation hardening (INV-10)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  async function signedInAdmin() {
    // Seed a live admin session (access + refresh) via restore().
    localStorage.setItem('juggle.token', ADMIN_TOKEN)
    localStorage.setItem(REFRESH_KEY, 'admin-refresh')
    me.mockResolvedValueOnce(ADMIN_USER)
    const auth = useAuthStore()
    await auth.restore()
    return auth
  }

  it('nulls the admin refresh token while impersonating and backs both up', async () => {
    const auth = await signedInAdmin()
    me.mockResolvedValueOnce(TARGET_USER)
    await auth.enterImpersonation(IMP_TOKEN)

    // Refresh token is pulled out of play (fail-closed) and both are backed up.
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
    expect(setRefreshToken).toHaveBeenCalledWith(null)
    expect(localStorage.getItem(ADMIN_BACKUP_KEY)).toBe(ADMIN_TOKEN)
    expect(localStorage.getItem(ADMIN_REFRESH_BACKUP_KEY)).toBe('admin-refresh')
    expect(auth.isImpersonating).toBe(true)
  })

  it('restores the admin access + refresh token on exit', async () => {
    const auth = await signedInAdmin()
    me.mockResolvedValueOnce(TARGET_USER)
    await auth.enterImpersonation(IMP_TOKEN)

    me.mockResolvedValueOnce(ADMIN_USER)
    await auth.exitImpersonation()

    expect(auth.token).toBe(ADMIN_TOKEN)
    expect(localStorage.getItem(REFRESH_KEY)).toBe('admin-refresh') // refresh restored
    expect(localStorage.getItem(ADMIN_BACKUP_KEY)).toBeNull()
    expect(localStorage.getItem(ADMIN_REFRESH_BACKUP_KEY)).toBeNull()
    expect(auth.isImpersonating).toBe(false)
  })

  it('falls back to the admin backup when a reload finds a dead impersonation token', async () => {
    // Storage as it looks mid-impersonation after a reload.
    localStorage.setItem('juggle.token', IMP_TOKEN)
    localStorage.setItem(ADMIN_BACKUP_KEY, ADMIN_TOKEN)
    localStorage.setItem(ADMIN_REFRESH_BACKUP_KEY, 'admin-refresh')

    // me() rejects for the dead imp token, then resolves for the restored admin.
    me.mockRejectedValueOnce(new Error('401')).mockResolvedValueOnce(ADMIN_USER)

    const auth = useAuthStore()
    await auth.restore()

    expect(auth.token).toBe(ADMIN_TOKEN) // admin session recovered, not wiped
    expect(auth.isImpersonating).toBe(false)
    expect(localStorage.getItem(REFRESH_KEY)).toBe('admin-refresh')
    expect(localStorage.getItem(ADMIN_BACKUP_KEY)).toBeNull()
  })

  it('clears everything when a dead non-impersonation token is found on reload', async () => {
    localStorage.setItem('juggle.token', ADMIN_TOKEN)
    localStorage.setItem(REFRESH_KEY, 'admin-refresh')
    me.mockRejectedValue(new Error('401'))

    const auth = useAuthStore()
    await auth.restore()

    expect(auth.token).toBeNull()
    expect(localStorage.getItem('juggle.token')).toBeNull()
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
  })
})
