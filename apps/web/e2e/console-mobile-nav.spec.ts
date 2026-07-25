// Provider + admin console navigation on a phone.
//
// Both drawers were `:model-value="true"` — hard-coded open — so below Quasar's
// breakpoint they rendered as a modal overlay covering the console with nothing
// listening to `update:model-value`, i.e. no way to dismiss them. A provider
// literally could not use the console on a phone. These lock in the fix.

import { expect, test, type Page } from '@playwright/test'

import { loginUI, signup } from './helpers'

const PHONE = { width: 390, height: 844 }
const DESKTOP = { width: 1280, height: 900 }
const ADMIN = 'admin@example.com'

async function drawerVisible(page: Page, sel: string): Promise<boolean> {
  return page.locator(sel).isVisible()
}

test('provider console on a phone: drawer starts closed, opens, and closes on navigate',
  async ({ page }) => {
    const { email } = await signup()
    await page.setViewportSize(PHONE)
    await loginUI(page, email)
    await page.goto('/provider')

    // Content is reachable, not buried under a permanent overlay.
    await expect(page.locator('.jg-provnav')).toBeHidden()
    await expect(page.locator('.q-page-container')).toBeVisible()

    // The hamburger opens it.
    await page.locator('.jg-provhdr [aria-label="Menu"]').click()
    await expect(page.locator('.jg-provnav')).toBeVisible()

    // Tapping the backdrop dismisses it — the first gesture anyone tries.
    await page.locator('.q-drawer__backdrop').click({ position: { x: 340, y: 400 } })
    await expect(page.locator('.jg-provnav')).toBeHidden()

    // And picking a destination dismisses it, so you can see where you landed —
    // including the page you're already on, which is a no-op navigation.
    await page.locator('.jg-provhdr [aria-label="Menu"]').click()
    await expect(page.locator('.jg-provnav')).toBeVisible()
    await page.locator('.jg-provnav__item', { hasText: 'Dashboard' }).first().click()
    await expect(page.locator('.jg-provnav')).toBeHidden()
  })

test('provider console on desktop: drawer stays pinned open, no hamburger', async ({ page }) => {
  const { email } = await signup()
  await page.setViewportSize(DESKTOP)
  await loginUI(page, email)
  await page.goto('/provider')
  await expect(page.locator('.jg-provnav')).toBeVisible()
  await expect(page.locator('.jg-provhdr [aria-label="Menu"]')).toBeHidden()
})

test('admin console on a phone: drawer is dismissable', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await loginUI(page, ADMIN)  // the seeded console admin, as the other admin spec uses
  await page.goto('/admin/approvals')

  await expect(page.locator('.jg-adminnav')).toBeHidden()
  await page.locator('.jg-adminhdr [aria-label="Menu"]').click()
  await expect(page.locator('.jg-adminnav')).toBeVisible()

  await page.locator('.jg-adminnav__item', { hasText: 'Payouts' }).click()
  await page.waitForURL('**/admin/payouts')
  await expect(page.locator('.jg-adminnav')).toBeHidden()
})

test('admin console on desktop: drawer pinned open', async ({ page }) => {
  await page.setViewportSize(DESKTOP)
  await loginUI(page, ADMIN)
  await page.goto('/admin/approvals')
  await expect(page.locator('.jg-adminnav')).toBeVisible()
  await expect(page.locator('.jg-adminhdr [aria-label="Menu"]')).toBeHidden()
})
