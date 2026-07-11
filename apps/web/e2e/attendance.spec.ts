import { expect, test } from '@playwright/test'

import { bookAndConfirm, loginUI, publishedSession, signup } from './helpers'

test('provider checks a child in on the morning-of roster (§8.3)', async ({ page }) => {
  const owner = await signup()
  const { programId, sessionId } = await publishedSession(owner.token)

  // Two confirmed families on the session.
  const g1 = await signup()
  await bookAndConfirm(g1.token, sessionId)
  const g2 = await signup()
  await bookAndConfirm(g2.token, sessionId)

  await loginUI(page, owner.email)
  await page.goto(`/provider/programs/${programId}`, { waitUntil: 'networkidle' })

  await page.getByRole('button', { name: 'Roster' }).first().click()
  const dialog = page.locator('.q-dialog')
  await expect(dialog).toContainText('0 of 2 checked in')

  // Tap the first child's check-in box.
  await dialog.locator('.q-item .q-checkbox').first().click()
  await expect(dialog).toContainText('1 of 2 checked in')
})
