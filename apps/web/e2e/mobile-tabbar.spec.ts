// Mobile bottom tab bar. The header nav is `gt-xs`, so on phones this bar IS the
// primary navigation — if it regresses, a phone user has no way around the app.
//
// The non-obvious cases here are the two that broke while building it: the site
// footer sits outside the page container (so padding the container alone leaves it
// under the bar), and checkout's sticky "Pay" button pins to the viewport bottom
// (so it has to offset by the bar's height, or the last step of checkout is covered).

import { expect, test } from '@playwright/test'

import { api, loginUI, publishedSession, signup } from './helpers'

const PHONE = { width: 390, height: 844 }
const DESKTOP = { width: 1280, height: 900 }

test('phone: the tab bar replaces the header nav', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await page.goto('/')

  const bar = page.locator('.jg-tabbar')
  await expect(bar).toBeVisible()
  await expect(page.locator('nav.jg-nav')).toBeHidden()

  // Signed out: never a dead end — Sign in is a tab.
  expect(await bar.locator('.jg-tabbar__label').allInnerTexts()).toEqual([
    'Discover', 'Parties', 'Cart', 'Sign in',
  ])

  // Pinned to the bottom edge.
  const box = (await bar.boundingBox())!
  expect(Math.round(box.y + box.height)).toBe(PHONE.height)

  // Cart and Sign in aren't also in the header — one destination, one control.
  await expect(page.locator('.jg-header .jg-signin')).toBeHidden()
  await expect(page.locator('.jg-header [aria-label="Cart"]')).toBeHidden()
})

test('desktop: no tab bar, header nav instead', async ({ page }) => {
  await page.setViewportSize(DESKTOP)
  await page.goto('/')
  await expect(page.locator('.jg-tabbar')).toBeHidden()
  await expect(page.locator('nav.jg-nav')).toBeVisible()
  await expect(page.locator('.jg-header [aria-label="Cart"]')).toBeVisible()
})

test('phone: tapping a tab navigates and moves the active state', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await page.goto('/')
  await expect(page.locator('.jg-tabbar')).toBeVisible()
  expect(await page.locator('.jg-tabbar__item--on .jg-tabbar__label').innerText())
    .toBe('Discover')

  await page.locator('.jg-tabbar__item', { hasText: 'Parties' }).click()
  await page.waitForURL('**/parties')
  expect(await page.locator('.jg-tabbar__item--on .jg-tabbar__label').innerText())
    .toBe('Parties')
})

test('phone: a signed-in parent gets Bookings and Account', async ({ page }) => {
  const { email } = await signup()
  await page.setViewportSize(PHONE)
  await loginUI(page, email)
  await page.goto('/')

  await expect(page.locator('.jg-tabbar')).toBeVisible()
  expect(await page.locator('.jg-tabbar__label').allInnerTexts()).toEqual([
    'Discover', 'Parties', 'Bookings', 'Cart', 'Account',
  ])
  // The avatar menu stays — it holds provider/admin/sign-out, which no tab covers.
  await expect(page.locator('.jg-header [aria-label="Account"]')).toBeVisible()
})

test('phone: the page scrolls clear of the fixed bar', async ({ page }) => {
  await page.setViewportSize(PHONE)
  await page.goto('/parties')
  await expect(page.locator('.jg-tabbar')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(300)

  const bar = (await page.locator('.jg-tabbar').boundingBox())!
  // The footer's padding deliberately runs behind the bar; its *content* must not.
  const inner = (await page.locator('.jg-footer__inner').boundingBox())!
  expect(inner.y + inner.height).toBeLessThanOrEqual(bar.y + 1)
})

test('phone: checkout\'s sticky Pay button is not hidden behind the bar', async ({ page }) => {
  const owner = await signup()
  const { sessionId } = await publishedSession(owner.token)
  const parent = await signup()

  await page.setViewportSize(PHONE)
  await loginUI(page, parent.email)

  // Build the cart via the API + the store's own persisted shape; driving the
  // add-a-kid dialog isn't what this test is about.
  const hold = await api.post<{ id: string }>(
    '/inventory/holds', { session_id: sessionId, quantity: 1 }, parent.token)
  const child = await api.post<{ id: string }>(
    '/identity/children', { first_name: 'Robin', date_of_birth: '2019-06-01' }, parent.token)
  await page.goto('/')
  await page.evaluate(([holdId, childId, sid]) => {
    localStorage.setItem('juggle.cart', JSON.stringify([{
      holdId, sessionId: sid, title: 'E2E Holiday Camp', orgName: 'E2E Org',
      venueName: 'Hall', startsAt: '2030-09-30T09:00:00Z', endsAt: '2030-09-30T15:00:00Z',
      priceCents: 5000, childIds: [childId],
    }]))
  }, [hold.id, child.id, sessionId])

  await page.goto('/checkout')
  await expect(page.locator('.jg-tabbar')).toBeVisible()
  const pay = page.locator('.jg-pay')
  await expect(pay).toBeVisible()

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(300)
  const payBox = (await pay.boundingBox())!
  const barBox = (await page.locator('.jg-tabbar').boundingBox())!
  expect(payBox.y + payBox.height).toBeLessThanOrEqual(barBox.y + 1)
})
