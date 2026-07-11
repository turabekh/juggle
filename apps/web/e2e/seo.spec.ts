import { expect, test } from '@playwright/test'

import { publishedSession, signup } from './helpers'

test('listing page exposes SEO meta + schema.org Event JSON-LD (§7.1)', async ({ page }) => {
  const owner = await signup()
  const { sessionId } = await publishedSession(owner.token)

  await page.goto(`/sessions/${sessionId}`, { waitUntil: 'networkidle' })

  await expect(page).toHaveTitle(/E2E Holiday Camp .+ \| Juggle/)
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new RegExp(`/sessions/${sessionId}$`),
  )

  const raw = await page.locator('script[type="application/ld+json"]').textContent()
  const jsonLd = JSON.parse(raw ?? '{}')
  expect(jsonLd['@type']).toBe('Event')
  expect(jsonLd.name).toBe('E2E Holiday Camp')
  expect(jsonLd.offers.priceCurrency).toBe('AUD')
  expect(jsonLd.offers.availability).toContain('InStock')
})
