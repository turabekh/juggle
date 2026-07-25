import { expect, test } from '@playwright/test'

import { API, api, loginUI, signup } from './helpers'

test('admin merges a duplicate account into a primary (§10.2)', async ({ page }) => {
  // A duplicate (source) with a child, and the primary (target) to keep.
  const source = await signup()
  await api.post('/identity/children', { first_name: 'Pip', date_of_birth: '2019-06-01' }, source.token)
  const target = await signup()

  await loginUI(page, 'admin@example.com')
  await page.goto('/admin/users', { waitUntil: 'networkidle' })

  // Select the primary account.
  await page.getByLabel('Search by email or name').fill(target.email)
  await page.getByText(target.email).click()

  // Merge the duplicate into it (the button only shows once a user is selected).
  const mergeBtn = page.getByRole('button', { name: /Merge a duplicate into this account/ })
  await expect(mergeBtn).toBeVisible()
  await mergeBtn.click()
  const dialog = page.locator('.q-dialog')
  await dialog.getByLabel('Find the duplicate account').fill(source.email)
  await dialog.getByText(source.email).click()
  await dialog.getByRole('button', { name: 'Merge' }).click()
  await expect(page.locator('.q-notification')).toContainText('merged')

  // The duplicate can no longer log in; the child moved to the target.
  // Use the shared API base, not a hardcoded port — this spec ignored E2E_API_URL.
  const login = await fetch(`${API}/identity/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: source.email, password: 'supersecret' }),
  })
  expect(login.status).toBe(401)
  const kids = await api.get<{ first_name: string }[]>('/identity/children', target.token)
  expect(kids.map((k) => k.first_name)).toContain('Pip')
})
