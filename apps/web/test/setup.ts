// Global test setup: install Quasar so components that use q-* render, and clear
// browser storage between tests for deterministic store/persistence tests.
import { config } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { afterEach, beforeEach } from 'vitest'

config.global.plugins = [[Quasar, {}]]

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})
