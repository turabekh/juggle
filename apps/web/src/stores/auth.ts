import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, setAuthToken } from '@/lib/api'
import type { User } from '@/lib/types'

const TOKEN_KEY = 'juggle.token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const ready = ref(false)

  const isAuthed = computed(() => token.value !== null)

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

  return { token, user, ready, isAuthed, login, signup, logout, restore }
})
