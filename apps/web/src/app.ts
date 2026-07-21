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
import { type HeadSink, SSR_HEAD_KEY } from '@/lib/head'
import { createAppRouter } from '@/router'

export function createApp(ssrRequestHeaders: Record<string, string> = {}) {
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

  // Quasar's SSR server build populates ssrContext during install/render and reads
  // req.headers for platform/user-agent detection — so give it a real req. Pages
  // register their <head> config into headSink on the server; entry-server resolves
  // it after serverPrefetch (see useHead / head.ts).
  const ssrContext: Record<string, unknown> = { req: { headers: ssrRequestHeaders }, res: {} }
  const headSink: HeadSink = { getter: null }
  if (onServer) app.provide(SSR_HEAD_KEY, headSink)

  // ssrContext is the THIRD arg to Quasar's install (app.use forwards extra args):
  // the server build Object.assigns $q/_meta into it during install and reads
  // req.headers for platform detection; the client build ignores it. This mirrors
  // @quasar/app-vite. Vue's app.use() type only types one options arg, so widen it.
  const use = app.use as (plugin: unknown, options: unknown, ssrContext?: unknown) => typeof app
  use(
    Quasar,
    {
      plugins: { Notify, Dialog, Loading },
      config: { notify: { position: 'top', timeout: 2600 } },
    },
    ssrContext,
  )
  app.use(pinia)
  app.use(router)

  return { app, router, pinia, ssrContext, headSink }
}
