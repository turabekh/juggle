// Minimal, dependency-free document-head manager for SEO (PRD §7.1).
//
// Sets <title>, description/OpenGraph/Twitter meta, a canonical link, and an
// optional schema.org JSON-LD block for the current page. Modern crawlers (e.g.
// Googlebot) execute JS and index this, so listing pages become discoverable
// and eligible for rich results without a full server-side render. Elements it
// creates are removed on unmount; the title is restored.

import { type InjectionKey, inject, onUnmounted, watchEffect } from 'vue'

export interface HeadConfig {
  title: string
  description?: string
  canonical?: string
  image?: string
  jsonLd?: Record<string, unknown>
  /** Emit `<meta name="robots" content="noindex">` — for private tokenized pages (INV-13). */
  noindex?: boolean
}

/** Per-request SSR sink: holds the most-specific page's head getter, resolved by
 * entry-server AFTER serverPrefetch so async-loaded data (listing title, JSON-LD)
 * is present. Provided by the app factory on the server only. */
export interface HeadSink {
  getter: (() => HeadConfig | null) | null
}
export const SSR_HEAD_KEY: InjectionKey<HeadSink> = Symbol('ssr-head')

/** The site origin, safe on both client and server. On the server (SSR) there is
 * no `window`, so fall back to the configured public origin. Use this instead of
 * `window.location.origin` anywhere that may run during SSR (canonical URLs etc.). */
export function siteOrigin(): string {
  if (typeof window !== 'undefined') return window.location.origin
  return import.meta.env.VITE_PUBLIC_ORIGIN || 'https://kidspots.store'
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Serialise a resolved HeadConfig to `<head>` HTML for SSR injection. Mirrors the
 * client-side upserts below so hydration sees the same tags. */
export function renderHeadToString(c: HeadConfig | null): string {
  if (!c) return ''
  const t: string[] = [
    `<title>${escapeHtml(c.title)}</title>`,
    `<meta property="og:title" content="${escapeHtml(c.title)}">`,
    `<meta property="og:type" content="website">`,
    `<meta name="twitter:card" content="summary_large_image">`,
  ]
  if (c.description) {
    t.push(`<meta name="description" content="${escapeHtml(c.description)}">`)
    t.push(`<meta property="og:description" content="${escapeHtml(c.description)}">`)
  }
  if (c.canonical) {
    t.push(`<meta property="og:url" content="${escapeHtml(c.canonical)}">`)
    t.push(`<link rel="canonical" href="${escapeHtml(c.canonical)}">`)
  }
  if (c.image) t.push(`<meta property="og:image" content="${escapeHtml(c.image)}">`)
  if (c.noindex) t.push(`<meta name="robots" content="noindex, nofollow">`)
  if (c.jsonLd) {
    // Guard the </script> sequence when inlining JSON-LD.
    t.push(
      `<script type="application/ld+json">${JSON.stringify(c.jsonLd).replace(/</g, '\\u003c')}</script>`,
    )
  }
  return t.join('\n    ')
}

export function useHead(getter: () => HeadConfig | null): void {
  // Server: register the getter into the request sink instead of touching the DOM.
  // entry-server resolves it after serverPrefetch (setup order means the page's
  // useHead runs after the layout's, so the most-specific one wins).
  if (typeof document === 'undefined') {
    const sink = inject(SSR_HEAD_KEY, null)
    if (sink) sink.getter = getter
    return
  }

  const created: HTMLElement[] = []
  let jsonLdEl: HTMLScriptElement | null = null
  const previousTitle = document.title

  function upsertMeta(attr: 'name' | 'property', key: string, content: string): void {
    let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
    if (!el) {
      el = document.createElement('meta')
      el.setAttribute(attr, key)
      document.head.appendChild(el)
      created.push(el)
    }
    el.setAttribute('content', content)
  }

  function upsertCanonical(href: string): void {
    let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    if (!el) {
      el = document.createElement('link')
      el.setAttribute('rel', 'canonical')
      document.head.appendChild(el)
      created.push(el)
    }
    el.setAttribute('href', href)
  }

  const stop = watchEffect(() => {
    const c = getter()
    if (!c) return
    document.title = c.title
    upsertMeta('property', 'og:title', c.title)
    upsertMeta('property', 'og:type', 'website')
    upsertMeta('name', 'twitter:card', 'summary_large_image')
    if (c.description) {
      upsertMeta('name', 'description', c.description)
      upsertMeta('property', 'og:description', c.description)
    }
    if (c.canonical) {
      upsertMeta('property', 'og:url', c.canonical)
      upsertCanonical(c.canonical)
    }
    if (c.image) upsertMeta('property', 'og:image', c.image)
    if (c.noindex) upsertMeta('name', 'robots', 'noindex, nofollow')
    if (c.jsonLd) {
      if (!jsonLdEl) {
        jsonLdEl = document.createElement('script')
        jsonLdEl.type = 'application/ld+json'
        document.head.appendChild(jsonLdEl)
      }
      jsonLdEl.textContent = JSON.stringify(c.jsonLd)
    }
  })

  onUnmounted(() => {
    stop()
    document.title = previousTitle
    created.forEach((el) => el.remove())
    jsonLdEl?.remove()
  })
}
