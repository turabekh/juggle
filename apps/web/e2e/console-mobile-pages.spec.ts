// Console pages at phone width.
//
// The failure mode these guard against is horizontal page scroll: one element wider
// than the viewport drags the whole document sideways, and every page on the site
// then feels broken. Two causes were real here — a flex row that couldn't fit a
// 120px input beside its description (admin/config), and a fixed 200px select beside
// a search field (admin/impersonation) — plus fifteen dialogs with hardcoded
// min-widths of 400–520px on a 390px screen.
//
// The admin tables are deliberately NOT converted to Quasar's grid mode: grid ignores
// `body-cell-*` slots, which would silently drop Approve/Suspend, Hold/Release and
// End-session buttons. They scroll inside their own container instead, which leaves
// the page intact — the last assertion here is what keeps that honest.

import { expect, test, type Page } from '@playwright/test'

import { loginUI, publishedSession, signup } from './helpers'

const PHONE = { width: 390, height: 844 }
const ADMIN = 'admin@example.com'

async function expectNoPageOverflow(page: Page, label: string): Promise<void> {
  const { doc, vw } = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    vw: window.innerWidth,
  }))
  expect(doc, `${label} scrolls horizontally (${doc}px in a ${vw}px viewport)`)
    .toBeLessThanOrEqual(vw + 1)
}

test('provider console pages fit a phone', async ({ page }) => {
  const owner = await signup()
  const { orgId, programId } = await publishedSession(owner.token)
  await page.setViewportSize(PHONE)
  await loginUI(page, owner.email)

  for (const [label, url] of [
    ['provider dashboard', '/provider'],
    ['provider org', `/provider/orgs/${orgId}`],
    ['provider program', `/provider/programs/${programId}`],
  ] as const) {
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
    await expectNoPageOverflow(page, label)
  }
})

test('admin console pages fit a phone', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await loginUI(page, ADMIN)

  for (const slug of [
    'approvals', 'payouts', 'reviews', 'config', 'flags',
    'audit', 'funnel', 'users', 'operations', 'impersonation',
  ]) {
    await page.goto(`/admin/${slug}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(400)
    await expectNoPageOverflow(page, `admin/${slug}`)
  }
})

test('console dialogs fit a phone', async ({ page }) => {
  const owner = await signup()
  const { orgId } = await publishedSession(owner.token)
  await page.setViewportSize(PHONE)
  await loginUI(page, owner.email)
  await page.goto(`/provider/orgs/${orgId}`, { waitUntil: 'networkidle' })

  for (const name of [/new package/i, /add venue/i]) {
    await page.getByRole('button', { name }).first().click()
    const card = page.locator('.q-dialog .q-card').first()
    await expect(card).toBeVisible()
    await page.waitForTimeout(500) // the dialog scales in; measure once it settles
    const box = (await card.boundingBox())!
    expect(box.width).toBeLessThanOrEqual(PHONE.width)
    expect(box.width).toBeGreaterThan(250) // clamped, not collapsed
    await expectNoPageOverflow(page, `dialog ${String(name)}`)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }
})

test('admin tables keep their actions on a phone and scroll inside their card', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await loginUI(page, ADMIN)
  await page.goto('/admin/approvals', { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)

  // Grid mode would render these rows as cards and drop the buttons entirely.
  expect(await page.getByRole('button', { name: /approve/i }).count()).toBeGreaterThan(0)

  const scroller = await page.evaluate(() => {
    const el = document.querySelector('.q-table__middle') as HTMLElement | null
    return el ? { scrollW: el.scrollWidth, clientW: el.clientWidth } : null
  })
  expect(scroller!.scrollW).toBeGreaterThan(scroller!.clientW) // scrolls internally…
  await expectNoPageOverflow(page, 'admin/approvals') // …without moving the page
})
