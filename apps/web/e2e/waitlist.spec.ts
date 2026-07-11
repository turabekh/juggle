import { expect, test } from '@playwright/test'

import { api, loginUI, publishedSession, signup, uniqueEmail } from './helpers'

test('waitlist: join a sold-out session, receive an offer, claim the seat (§7.7)', async ({
  page,
}) => {
  const owner = await signup()
  const { sessionId } = await publishedSession(owner.token, { capacity: 1 })

  // A holder takes the only seat with a pending booking (so it can be cancelled).
  const holder = await signup()
  const hold = await api.post<{ id: string }>(
    '/inventory/holds',
    { session_id: sessionId, quantity: 1 },
    holder.token,
  )
  const holderChild = await api.post<{ id: string }>(
    '/identity/children',
    { first_name: 'Ada', date_of_birth: '2019-06-01' },
    holder.token,
  )
  const order = await api.post<{ payment_id: string }>(
    '/booking/checkout',
    {
      idempotency_key: uniqueEmail('k'),
      items: [{ hold_id: hold.id, children: [{ child_id: holderChild.id }] }],
    },
    holder.token,
  )

  // Parent B (with a child) joins the waitlist from the sold-out listing.
  const b = await signup()
  await api.post('/identity/children', { first_name: 'Bo', date_of_birth: '2019-06-01' }, b.token)
  await loginUI(page, b.email)

  await page.goto(`/sessions/${sessionId}`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /Join the waitlist/ }).click()
  await expect(page.locator('.jg-waitlist')).toContainText('#1')

  // Free the seat — the holder cancels — and B reads their bookings to reconcile.
  await api.post(`/booking/payments/${order.payment_id}/cancel`, {}, holder.token)
  await page.goto('/bookings', { waitUntil: 'networkidle' })
  await expect(page.locator('.jg-offer')).toContainText('Seat available')

  // Claim it: pick the child and book.
  await page.getByRole('button', { name: 'Claim seat' }).click()
  await page.locator('.q-dialog .q-radio').first().click()
  await page.locator('.q-dialog').getByRole('button', { name: 'Book seat' }).click()

  // The offer clears once claimed.
  await expect(page.locator('.jg-offer')).toHaveCount(0)
})
