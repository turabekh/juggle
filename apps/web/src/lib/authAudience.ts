// Which experience a person is signing in to. One login page, two destinations:
// the parent marketplace or the provider console. An account can be both — this
// only decides where you land; a header switcher moves you between them after.

import type { RouteLocationRaw } from 'vue-router'

export type Audience = 'parent' | 'provider'

/** Read the intended audience from a route query (`?as=provider`). */
export function audienceFromQuery(as: unknown): Audience {
  return as === 'provider' ? 'provider' : 'parent'
}

/** Where to send someone after they authenticate. An explicit `?redirect=`
 * (e.g. a deep link they were bounced from) always wins over the toggle. */
export function landingFor(audience: Audience, redirect?: string | null): RouteLocationRaw {
  if (redirect) return redirect
  return audience === 'provider' ? { name: 'provider' } : { name: 'discover' }
}
