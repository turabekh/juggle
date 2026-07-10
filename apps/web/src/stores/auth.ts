import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, setAuthToken } from '@/lib/api'
import { decodeJwt } from '@/lib/jwt'
import type { User } from '@/lib/types'

const TOKEN_KEY = 'juggle.token'
const ADMIN_BACKUP_KEY = 'juggle.adminToken'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const ready = ref(false)

  const isAuthed = computed(() => token.value !== null)
  const isAdmin = computed(() => user.value?.is_admin === true)

  const claims = computed(() => (token.value ? decodeJwt(token.value) : null))
  const isImpersonating = computed(() => !!claims.value?.imp)
  const impersonationMode = computed(() => claims.value?.mode ?? null)

  async function _establish(accessToken: string): Promise<void> {
    token.value = accessToken
    setAuthToken(accessToken)
    localStorage.setItem(TOKEN_KEY, accessToken)
    user.value = await api.auth.me()
  }

  async function login(email: string, password: string): Promise<void> {
    const res = await api.auth.login(email, password)
    await _establish(res.access_token)
  }

  async function signup(email: string, password: string, fullName?: string): Promise<void> {
    const res = await api.auth.signup(email, password, fullName)
    await _establish(res.access_token)
  }

  function logout(): void {
    token.value = null
    user.value = null
    setAuthToken(null)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ADMIN_BACKUP_KEY)
  }

  /** Swap the admin token for an impersonation token, backing the admin up. */
  async function enterImpersonation(impersonationToken: string): Promise<void> {
    if (token.value) localStorage.setItem(ADMIN_BACKUP_KEY, token.value)
    await _establish(impersonationToken)
  }

  /** Restore the admin session after an impersonation. */
  async function exitImpersonation(): Promise<void> {
    const backup = localStorage.getItem(ADMIN_BACKUP_KEY)
    localStorage.removeItem(ADMIN_BACKUP_KEY)
    if (backup) {
      await _establish(backup)
    } else {
      logout()
    }
  }

  async function restore(): Promise<void> {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored) {
      token.value = stored
      setAuthToken(stored)
      try {
        user.value = await api.auth.me()
      } catch {
        logout()
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
    logout,
    enterImpersonation,
    exitImpersonation,
    restore,
  }
})
