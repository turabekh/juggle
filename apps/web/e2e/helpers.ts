// Shared e2e helpers: talk to the API to set up state, and drive the UI for
// auth. Tests create their own accounts/orgs/sessions so they don't depend on
// any particular seed and can run in parallel.

import { expect, type Page } from '@playwright/test'

export const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'
export const PASSWORD = 'supersecret'

let counter = 0
export function uniqueEmail(prefix: string): string {
  counter += 1
  const rand = Math.random().toString(36).slice(2, 8)
  return `${prefix}-${Date.now().toString(36)}-${rand}-${counter}@example.com`
}

async function apiFetch<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string,
): Promise<T> {
  const res = await fetch(API + path, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}: ${await res.text()}`)
  return (await res.json().catch(() => ({}))) as T
}

export const api = {
  post: <T>(path: string, body?: unknown, token?: string) => apiFetch<T>('POST', path, body, token),
  get: <T>(path: string, token?: string) => apiFetch<T>('GET', path, undefined, token),
}

/** Create an account via the API and return its bearer token. */
export async function signup(email = uniqueEmail('u')): Promise<{ email: string; token: string }> {
  const { access_token } = await api.post<{ access_token: string }>('/identity/signup', {
    email,
    password: PASSWORD,
  })
  return { email, token: access_token }
}

export interface SessionSetup {
  orgId: string
  programId: string
  sessionId: string
}

/** Create a published, upcoming session under a fresh org. */
export async function publishedSession(
  ownerToken: string,
  opts: { capacity?: number; startsAt?: string; endsAt?: string; whatToBring?: string } = {},
): Promise<SessionSetup> {
  const starts = opts.startsAt ?? '2030-09-30T09:00:00Z'
  const ends = opts.endsAt ?? '2030-09-30T15:00:00Z'
  const org = await api.post<{ id: string }>('/org', { name: `E2E Org ${uniqueEmail('o')}` }, ownerToken)
  const venue = await api.post<{ id: string }>(
    '/catalog/venues',
    { organisation_id: org.id, name: 'Hall', suburb: 'Perth', postcode: '6000' },
    ownerToken,
  )
  const program = await api.post<{ id: string }>(
    '/catalog/programs',
    { organisation_id: org.id, title: 'E2E Holiday Camp', category: 'art' },
    ownerToken,
  )
  const session = await api.post<{ id: string }>(
    `/catalog/programs/${program.id}/sessions`,
    {
      venue_id: venue.id,
      starts_at: starts,
      ends_at: ends,
      capacity: opts.capacity ?? 5,
      price_cents: 5000,
      age_min: 4,
      age_max: 12,
      what_to_bring: opts.whatToBring,
    },
    ownerToken,
  )
  await api.post(`/catalog/programs/${program.id}/publish`, {}, ownerToken)
  return { orgId: org.id, programId: program.id, sessionId: session.id }
}

/** Book + confirm one child on a session (via API), returning the child id. */
export async function bookAndConfirm(
  token: string,
  sessionId: string,
  dob = '2019-06-01',
): Promise<{ childId: string; paymentId: string }> {
  const hold = await api.post<{ id: string }>(
    '/inventory/holds',
    { session_id: sessionId, quantity: 1 },
    token,
  )
  const child = await api.post<{ id: string }>(
    '/identity/children',
    { first_name: 'Robin', date_of_birth: dob },
    token,
  )
  const order = await api.post<{ payment_id: string }>(
    '/booking/checkout',
    { idempotency_key: uniqueEmail('k'), items: [{ hold_id: hold.id, children: [{ child_id: child.id }] }] },
    token,
  )
  await api.post(`/booking/payments/${order.payment_id}/confirm`, {}, token)
  return { childId: child.id, paymentId: order.payment_id }
}

/** Log in through the UI so the SPA holds a real session. */
export async function loginUI(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto('/login', { waitUntil: 'networkidle' })
  const inputs = page.locator('.q-form input')
  await inputs.nth(0).fill(email)
  await inputs.nth(1).fill(password)
  await inputs.nth(1).press('Enter')
  await expect(page.locator('.jg-scard').first()).toBeVisible({ timeout: 15000 })
}
