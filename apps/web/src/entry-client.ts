// Client entry: mounts the SPA (empty #app) or hydrates server-rendered markup
// (built with @quasar/vite-plugin runMode 'ssr-client'), restoring any pinia
// state the server serialized. Also registers the PWA SW.

import type { StateTree } from 'pinia'

import { createApp } from '@/app'

declare global {
  interface Window {
    __PINIA__?: Record<string, StateTree>
  }
}

const { app, router, pinia } = createApp()

if (typeof window !== 'undefined' && window.__PINIA__) {
  pinia.state.value = window.__PINIA__
}

router.isReady().then(() => {
  app.mount('#app')
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        /* offline support is best-effort */
      })
    })
  }
})
