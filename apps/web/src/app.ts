// Universal app factory — used by both the client entry (SPA mount / SSR
// hydration) and the server entry (renderToString). A fresh app + router + pinia
// is created per call so server requests never share state.

import { createApp as createClientApp, createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar, Dialog, Loading, Notify } from 'quasar'
import { createMemoryHistory, createWebHistory } from 'vue-router'

import '@quasar/extras/material-icons/material-icons.css'
import '@quasar/extras/material-icons-round/material-icons-round.css'
import 'quasar/src/css/index.sass'
import '@/css/app.scss'

import App from '@/App.vue'
import { createAppRouter } from '@/router'

export function createApp() {
  const onServer = import.meta.env.SSR
  const hydrating =
    !onServer &&
    typeof document !== 'undefined' &&
    !!document.getElementById('app')?.firstElementChild

  // SSR app on the server and when hydrating server markup; a plain client app
  // for a from-scratch SPA mount (empty #app) so there's no hydration warning.
  const app = onServer || hydrating ? createSSRApp(App) : createClientApp(App)
  const router = createAppRouter(onServer ? createMemoryHistory() : createWebHistory())
  const pinia = createPinia()

  app.use(Quasar, {
    plugins: { Notify, Dialog, Loading },
    config: { notify: { position: 'top', timeout: 2600 } },
  })
  app.use(pinia)
  app.use(router)

  return { app, router, pinia }
}
