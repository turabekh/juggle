// Server entry: renders the app for a URL to an HTML string plus the pinia state
// to serialize for client hydration. Called per request by server.mjs.
//
// NOTE: blocked on Quasar's client-only bundle under `@quasar/vite-plugin` (see
// server.mjs header). The pipeline is correct; the UI layer can't SSR yet.

import type { StateTree } from 'pinia'
import { renderToString } from 'vue/server-renderer'

import { createApp } from '@/app'

export interface RenderResult {
  html: string
  state: Record<string, StateTree>
  status: number
}

export async function render(url: string): Promise<RenderResult> {
  const { app, router, pinia } = createApp()

  await router.push(url)
  await router.isReady()

  const matched = router.currentRoute.value.matched
  const status = matched.some((r) => r.name === 'notfound') ? 404 : 200

  const html = await renderToString(app)
  return { html, state: pinia.state.value, status }
}
