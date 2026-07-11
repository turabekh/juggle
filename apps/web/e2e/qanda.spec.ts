import { expect, test } from '@playwright/test'

import { api, loginUI, publishedSession, signup } from './helpers'

test('listing Q&A: parent asks, provider answers, parent sees it (§7.2)', async ({ page }) => {
  const owner = await signup()
  const { programId, sessionId } = await publishedSession(owner.token)
  const parent = await signup()

  await loginUI(page, parent.email)
  await page.goto(`/sessions/${sessionId}`, { waitUntil: 'networkidle' })

  const qSection = page.locator('section', { hasText: 'Questions' })
  await qSection.locator('textarea').fill('Do you provide lunch?')
  await qSection.getByRole('button', { name: 'Ask' }).click()
  await expect(page.locator('.jg-qa')).toContainText('Do you provide lunch?')
  await expect(page.locator('.jg-qa')).toContainText('Awaiting a reply')

  // The provider answers (via API), then the parent reloads and sees it.
  const questions = await api.get<{ id: string }[]>(`/qanda/programs/${programId}/questions`)
  await api.post(
    `/qanda/questions/${questions[0].id}/answer`,
    { answer: 'Yes — a nut-free lunch is included.' },
    owner.token,
  )
  await page.reload({ waitUntil: 'networkidle' })
  await expect(page.locator('.jg-qa')).toContainText('Yes — a nut-free lunch is included.')
})
