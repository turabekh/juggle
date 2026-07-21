// Server entry: renders the app for a URL to an HTML string, the resolved <head>
// HTML (title/meta/JSON-LD for SEO), and the pinia state to serialize for client
// hydration. Called per request by server.mjs.
//
// Quasar SSR is enabled via the @quasar/vite-plugin `runMode: 'ssr-server'` build
// (see vite.config.ts) — no Quasar-CLI migration required.

import type { StateTree } from 'pinia'
import { renderToString } from 'vue/server-renderer'

import { createApp } from '@/app'
import { renderHeadToString } from '@/lib/head'

export interface RenderResult {
  html: string
  head: string
  state: Record<string, StateTree>
  status: number
}

export async function render(
  url: string,
  headers: Record<string, string> = {},
): Promise<RenderResult> {
  const { app, router, pinia, headSink } = createApp(headers)

  await router.push(url)
  await router.isReady()

  const matched = router.currentRoute.value.matched
  const status = matched.some((r) => r.name === 'notfound') ? 404 : 200

  // renderToString awaits each component's onServerPrefetch, so async page data
  // (listing details) is loaded before we resolve the head getter below.
  const html = await renderToString(app)
  const head = renderHeadToString(headSink.getter ? headSink.getter() : null)

  return { html, head, state: pinia.state.value, status }
}
