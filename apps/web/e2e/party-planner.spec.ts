// Party Planner (ADR-0011 Milestone B) e2e: the invitee vote loop, driven through the UI.
//
// Host orchestration (create plan + options + open) runs via the API for speed and because the
// package-browse dropdown only lists approved orgs; the novel surface — the public invitee page
// (enter details → tap a party → one-step RSVP-and-vote → live tally) is exercised through the UI.
// Anyone with the share link is auto-approved (no host approval step). Resolution/confirm is
// clock-driven (scheduler tick) and is covered by backend integration tests.
//
// Requires the stack up (make up + make seed, which enables the party_planner flag) and the web
// dev server. Run: make web-e2e.

import { expect, test } from '@playwright/test'

import { api, signup, uniqueEmail } from './helpers'

async function partyPackage(ownerToken: string): Promise<{ packageId: string; slotIds: string[] }> {
  const org = await api.post<{ id: string }>('/org', { name: `E2E Party ${uniqueEmail('o')}` }, ownerToken)
  const venue = await api.post<{ id: string }>(
    '/catalog/venues', { organisation_id: org.id, name: 'Party Hall' }, ownerToken,
  )
  const pkg = await api.post<{ id: string }>(
    `/parties/orgs/${org.id}/packages`,
    { venue_id: venue.id, name: 'Superhero Party', per_head_price_cents: 3500,
      min_headcount: 1, max_headcount: 30, outdoor: false },
    ownerToken,
  )
  const base = Date.now() + 30 * 3600_000 // 30h out — leaves room for the 24h deadline gap
  const slots = await api.post<{ id: string }[]>(
    `/parties/packages/${pkg.id}/slots`,
    { slots: [0, 1].map((i) => ({
      starts_at: new Date(base + i * 3600_000).toISOString(),
      ends_at: new Date(base + i * 3600_000 + 2 * 3600_000).toISOString(),
    })) },
    ownerToken,
  )
  return { packageId: pkg.id, slotIds: slots.map((s) => s.id) }
}

test('invitees enter details and vote in one step via the public link; tally updates', async ({
  page,
}) => {
  const host = await signup(uniqueEmail('host'))
  const { packageId, slotIds } = await partyPackage(host.token)

  // Host builds + opens a plan via the API (2 package options + 1 custom).
  const plan = await api.post<{ id: string }>('/party-planner/plans', { theme: 'dino' }, host.token)
  const pid = plan.id
  await api.post(`/party-planner/plans/${pid}/options/package`,
    { package_id: packageId, slot_id: slotIds[0] }, host.token)
  await api.post(`/party-planner/plans/${pid}/options/package`,
    { package_id: packageId, slot_id: slotIds[1] }, host.token)
  await api.post(`/party-planner/plans/${pid}/options/custom`,
    { text: 'Backyard party at ours' }, host.token)
  // Customise the party page — a pseudonymous title + template that must render on the public page.
  await apiPut(`/party-planner/plans/${pid}/page`, {
    template: 'superhero', title: "Dino's Big Day", message: 'Come celebrate with us!',
    hero_avatar: 'dino', widgets: ['welcome', 'countdown', 'board', 'reveal_venue'],
  }, host.token)
  const deadline = new Date(Date.now() + 90 * 60_000).toISOString() // 90 min out; stays open
  await apiPut(`/party-planner/plans/${pid}/deadline`, { deadline_at: deadline }, host.token)
  const shareToken = (await apiPost<{ share_token: string }>(
    `/party-planner/plans/${pid}/open`, {}, host.token,
  )).share_token

  // --- Invitee: enter details via the public link (no account), then tap a party to vote ---
  await page.goto(`/parties/plan/${shareToken}`, { waitUntil: 'networkidle' })
  // The host-customized party page renders (title + welcome widget).
  await expect(page.getByRole('heading', { name: "Dino's Big Day" })).toBeVisible()
  await expect(page.getByText('Come celebrate with us!')).toBeVisible()
  await page.getByLabel('Your name').fill('Alex Guest')
  await page.getByLabel('Email', { exact: true }).fill(uniqueEmail('guest'))
  await page.getByLabel('How many kids are you bringing?').fill('2')

  // Tapping the first option auto-approves + RSVPs + votes in one step — no host approval.
  const firstOption = page.locator('[data-testid="vote-option"]').first()
  await expect(firstOption).toBeVisible({ timeout: 10000 })
  await firstOption.click()
  await expect(page.getByText(/Vote counted/i)).toBeVisible({ timeout: 10000 })

  // The tally reflects the vote server-side.
  await expect
    .poll(async () => {
      const pub = await api.get<{ options: { id: string; votes: number }[] }>(
        `/party-planner/public/${shareToken}`,
      )
      return pub.options.reduce((n, o) => n + o.votes, 0)
    }, { timeout: 10000 })
    .toBeGreaterThanOrEqual(1)
})

// Small typed helpers (PUT/POST) — helpers.ts exposes GET/POST; the planner uses PUT for deadline.
async function apiPut<T>(path: string, body: unknown, token: string): Promise<T> {
  const res = await fetch((process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1') + path, {
    method: 'PUT',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`PUT ${path} → ${res.status}: ${await res.text()}`)
  return (await res.json()) as T
}
async function apiPost<T>(path: string, body: unknown, token: string): Promise<T> {
  const res = await fetch((process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1') + path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}: ${await res.text()}`)
  return (await res.json()) as T
}
