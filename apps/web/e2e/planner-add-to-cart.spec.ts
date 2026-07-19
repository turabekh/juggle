// Planner → "Add whole plan to cart": the parent builds a holiday plan and adds
// every matching session to the cart in one tap (reuses the session→hold→cart
// rails; no new money code). Requires the stack up with the `planner` flag ON
// (make seed enables it) and the web dev server. Run:
//   E2E_BASE_URL=http://localhost:9000 E2E_API_URL=http://localhost:8001/api/v1 \
//     npx playwright test planner-add-to-cart

import { expect, test } from '@playwright/test'

import { api, loginUI, PASSWORD, signup, uniqueEmail } from './helpers'

/** Publish one program (with a session on a given day) under a fresh org + suburb. */
async function publishProgram(
  token: string,
  opts: { suburb: string; title: string; category: string; startsAt: string; endsAt: string },
): Promise<string> {
  const org = await api.post<{ id: string }>('/org', { name: `PL Org ${uniqueEmail('o')}` }, token)
  const venue = await api.post<{ id: string }>(
    '/catalog/venues',
    { organisation_id: org.id, name: 'Hall', suburb: opts.suburb, postcode: '6000' },
    token,
  )
  const program = await api.post<{ id: string }>(
    '/catalog/programs',
    { organisation_id: org.id, title: opts.title, category: opts.category },
    token,
  )
  const session = await api.post<{ id: string }>(
    `/catalog/programs/${program.id}/sessions`,
    {
      venue_id: venue.id,
      starts_at: opts.startsAt,
      ends_at: opts.endsAt,
      capacity: 8,
      price_cents: 5000,
      age_min: 4,
      age_max: 12,
    },
    token,
  )
  await api.post(`/catalog/programs/${program.id}/publish`, {}, token)
  return session.id
}

test('parent builds a plan and adds the whole plan to the cart', async ({ page }) => {
  // Unique suburb so the planner's candidate set is exactly this test's sessions.
  const suburb = `Planville${Math.random().toString(36).slice(2, 8)}`
  const email = uniqueEmail('parent')
  const { token } = await signup(email)

  // A child whose age at the session falls in the 4–12 range.
  await api.post('/identity/children', { first_name: 'Robin', date_of_birth: '2020-06-01' }, token)

  // Two *different* activities on two different days.
  await publishProgram(token, {
    suburb,
    title: 'Art Attack',
    category: 'art',
    startsAt: '2030-09-30T01:00:00Z',
    endsAt: '2030-09-30T05:00:00Z',
  })
  await publishProgram(token, {
    suburb,
    title: 'Soccer Stars',
    category: 'sport',
    startsAt: '2030-10-01T01:00:00Z',
    endsAt: '2030-10-01T05:00:00Z',
  })

  await loginUI(page, email, PASSWORD)

  // Build the plan.
  await page.goto('/planner', { waitUntil: 'networkidle' })
  await page.locator('.q-select').first().click()
  await page.locator('.q-menu .q-item').filter({ hasText: /^8$/ }).first().click()
  await page.keyboard.press('Escape')
  await page.locator('input[type="date"]').nth(0).fill('2030-09-28')
  await page.locator('input[type="date"]').nth(1).fill('2030-10-05')
  await page.getByPlaceholder('e.g. Scarborough').fill(suburb)
  await page.getByRole('button', { name: 'Build my plan' }).click()

  // Plan renders with both activities.
  await expect(page.getByText('Art Attack')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('Soccer Stars')).toBeVisible()

  // One tap adds the whole plan.
  await page.getByRole('button', { name: 'Add whole plan to cart' }).click()
  await expect(page.locator('.q-notification')).toContainText('Added 2 sessions to cart', {
    timeout: 10000,
  })

  // The cart holds both sessions.
  await page.goto('/cart', { waitUntil: 'networkidle' })
  await expect(page.getByText('Art Attack')).toBeVisible()
  await expect(page.getByText('Soccer Stars')).toBeVisible()
})
