// Minimal, dependency-free document-head manager for SEO (PRD §7.1).
//
// Sets <title>, description/OpenGraph/Twitter meta, a canonical link, and an
// optional schema.org JSON-LD block for the current page. Modern crawlers (e.g.
// Googlebot) execute JS and index this, so listing pages become discoverable
// and eligible for rich results without a full server-side render. Elements it
// creates are removed on unmount; the title is restored.

import { onUnmounted, watchEffect } from 'vue'

export interface HeadConfig {
  title: string
  description?: string
  canonical?: string
  image?: string
  jsonLd?: Record<string, unknown>
}

export function useHead(getter: () => HeadConfig | null): void {
  // Client-only: during SSR there is no document. The server injects critical
  // per-listing meta from the fetched data; the client keeps it fresh here.
  if (typeof document === 'undefined') return

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
