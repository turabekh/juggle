import { expect, test } from '@playwright/test'

import { api, loginUI, signup, uniqueEmail } from './helpers'

test('provider duplicates a program to a new cycle (§8.2)', async ({ page }) => {
  const owner = await signup()
  const org = await api.post<{ id: string }>('/org', { name: `Dup Org ${uniqueEmail('o')}` }, owner.token)
  const venue = await api.post<{ id: string }>(
    '/catalog/venues',
    { organisation_id: org.id, name: 'Hall' },
    owner.token,
  )
  const program = await api.post<{ id: string }>(
    '/catalog/programs',
    { organisation_id: org.id, title: 'Relist Camp', category: 'art' },
    owner.token,
  )
  for (const day of ['2030-09-30', '2030-10-01']) {
    await api.post(
      `/catalog/programs/${program.id}/sessions`,
      {
        venue_id: venue.id,
        starts_at: `${day}T09:00:00Z`,
        ends_at: `${day}T15:00:00Z`,
        capacity: 5,
        price_cents: 5000,
        age_min: 4,
        age_max: 12,
      },
      owner.token,
    )
  }
  await api.post(`/catalog/programs/${program.id}/publish`, {}, owner.token)

  await loginUI(page, owner.email)
  await page.goto(`/provider/programs/${program.id}`, { waitUntil: 'networkidle' })
  await expect(page.locator('.jg-srow')).toHaveCount(2)

  await page.getByRole('button', { name: /Duplicate to new dates/ }).click()
  const dialog = page.locator('.q-dialog')
  await expect(dialog).toContainText('Shifts every session forward') // default date valid
  await dialog.getByRole('button', { name: 'Duplicate' }).click()

  // The two originals plus two copies.
  await expect(page.locator('.jg-srow')).toHaveCount(4)
})
