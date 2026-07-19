import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, configureAuth, setAuthToken, setRefreshToken } from '@/lib/api'
import { decodeJwt } from '@/lib/jwt'
import { storage } from '@/lib/storage'
import type { User } from '@/lib/types'

const TOKEN_KEY = 'juggle.token'
const REFRESH_KEY = 'juggle.refresh'
const ADMIN_BACKUP_KEY = 'juggle.adminToken'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const user = ref<User | null>(null)
  const ready = ref(false)

  const isAuthed = computed(() => token.value !== null)
  const isAdmin = computed(() => user.value?.is_admin === true)

  const claims = computed(() => (token.value ? decodeJwt(token.value) : null))
  const isImpersonating = computed(() => !!claims.value?.imp)
  const impersonationMode = computed(() => claims.value?.mode ?? null)

  /** Persist a rotated access (and optionally refresh) token into store + storage. */
  function applyTokens(accessToken: string, newRefresh?: string): void {
    token.value = accessToken
    setAuthToken(accessToken)
    storage.set(TOKEN_KEY, accessToken)
    if (newRefresh !== undefined) {
      refreshToken.value = newRefresh
      setRefreshToken(newRefresh)
      storage.set(REFRESH_KEY, newRefresh)
    }
  }

  // Let the api layer push transparently-refreshed tokens back here, and fall
  // back to a full logout if a refresh ultimately fails.
  configureAuth({
    onRefreshed: (accessToken, newRefresh) => applyTokens(accessToken, newRefresh),
    onLogout: () => logout(),
  })

  async function _establish(accessToken: string, newRefresh?: string): Promise<void> {
    applyTokens(accessToken, newRefresh)
    user.value = await api.auth.me()
  }

  async function login(email: string, password: string): Promise<void> {
    const res = await api.auth.login(email, password)
    await _establish(res.access_token, res.refresh_token)
  }

  async function signup(email: string, password: string, fullName?: string): Promise<void> {
    const res = await api.auth.signup(email, password, fullName)
    await _establish(res.access_token, res.refresh_token)
  }

  /** SMS one-time-code sign-in: request a code, then verify it to sign in. */
  async function requestOtp(phone: string): Promise<void> {
    await api.auth.requestOtp(phone)
  }

  async function verifyOtp(phone: string, code: string): Promise<void> {
    const res = await api.auth.verifyOtp(phone, code)
    await _establish(res.access_token, res.refresh_token)
  }

  function _clearLocal(): void {
    token.value = null
    refreshToken.value = null
    user.value = null
    setAuthToken(null)
    setRefreshToken(null)
    storage.remove(TOKEN_KEY)
    storage.remove(REFRESH_KEY)
    storage.remove(ADMIN_BACKUP_KEY)
  }

  function logout(): void {
    // Best-effort server-side revoke so the refresh token is truly dead.
    const rt = refreshToken.value
    if (rt) void api.auth.logout(rt).catch(() => undefined)
    _clearLocal()
  }

  /** Swap the admin token for an impersonation token, backing the admin up. The
   * admin's refresh token is left in place; the api layer refuses to refresh an
   * impersonation session, so it can't be silently upgraded back to admin. */
  async function enterImpersonation(impersonationToken: string): Promise<void> {
    if (token.value) storage.set(ADMIN_BACKUP_KEY, token.value)
    token.value = impersonationToken
    setAuthToken(impersonationToken)
    storage.set(TOKEN_KEY, impersonationToken)
    user.value = await api.auth.me()
  }

  /** Restore the admin session after an impersonation. */
  async function exitImpersonation(): Promise<void> {
    const backup = storage.get(ADMIN_BACKUP_KEY)
    storage.remove(ADMIN_BACKUP_KEY)
    if (backup) {
      token.value = backup
      setAuthToken(backup)
      storage.set(TOKEN_KEY, backup)
      user.value = await api.auth.me()
    } else {
      logout()
    }
  }

  async function restore(): Promise<void> {
    const storedToken = storage.get(TOKEN_KEY)
    const storedRefresh = storage.get(REFRESH_KEY)
    if (storedToken) {
      token.value = storedToken
      setAuthToken(storedToken)
      if (storedRefresh) {
        refreshToken.value = storedRefresh
        setRefreshToken(storedRefresh)
      }
      try {
        // If the access token has expired, the api layer refreshes transparently.
        user.value = await api.auth.me()
      } catch {
        _clearLocal()
      }
    }
    ready.value = true
  }

  return {
    token,
    user,
    ready,
    isAuthed,
    isAdmin,
    isImpersonating,
    impersonationMode,
    login,
    signup,
    requestOtp,
    verifyOtp,
    logout,
    enterImpersonation,
    exitImpersonation,
    restore,
  }
})
