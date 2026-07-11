import { expect, test } from '@playwright/test'

import { api, loginUI, signup } from './helpers'

test('co-guardian: invite → accept → shared child appears (§7.3)', async ({ browser }) => {
  const a = await signup()
  const b = await signup()
  await api.post('/identity/children', { first_name: 'Pip', date_of_birth: '2019-06-01' }, a.token)

  // Guardian A invites B by email.
  const ctxA = await browser.newContext()
  const pageA = await ctxA.newPage()
  await loginUI(pageA, a.email)
  await pageA.goto('/account', { waitUntil: 'networkidle' })
  await pageA.getByRole('button', { name: /Add a co-guardian/ }).click()
  await pageA.locator('.q-dialog input').fill(b.email)
  await pageA.locator('.q-dialog').getByRole('button', { name: /Send invite/ }).click()
  await expect(pageA.locator('section', { hasText: 'Family' })).toContainText('Invite sent')

  // B accepts and now sees A's child.
  const ctxB = await browser.newContext()
  const pageB = await ctxB.newPage()
  await loginUI(pageB, b.email)
  await pageB.goto('/account', { waitUntil: 'networkidle' })
  await pageB.getByRole('button', { name: 'Accept' }).click()
  await expect(pageB.locator('.jg-kids').first()).toContainText('Pip')

  await ctxA.close()
  await ctxB.close()
})
