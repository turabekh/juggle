import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'

import { type CartItem, useCartStore } from '@/stores/cart'

function item(over: Partial<CartItem> = {}): CartItem {
  return {
    holdId: `hold-${Math.random().toString(36).slice(2)}`,
    sessionId: 'sess-1',
    title: 'Camp',
    orgName: 'Sunshine',
    venueName: 'Hall',
    startsAt: '2026-12-01T09:00:00Z',
    endsAt: '2026-12-01T15:00:00Z',
    priceCents: 5000,
    childIds: ['c1'],
    ...over,
  }
}

describe('cart store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('tracks count, seats and totals across items and children', () => {
    const cart = useCartStore()
    expect(cart.count).toBe(0)
    cart.add(item({ childIds: ['c1', 'c2'], priceCents: 5000 }))
    cart.add(item({ childIds: ['c3'], priceCents: 3000 }))
    expect(cart.count).toBe(2)
    expect(cart.seatCount).toBe(3) // 2 + 1
    expect(cart.totalCents).toBe(5000 * 2 + 3000 * 1) // 13000
  })

  it('clearConsumed empties the cart', () => {
    const cart = useCartStore()
    cart.add(item())
    cart.clearConsumed()
    expect(cart.count).toBe(0)
  })

  it('persists to localStorage so a reload restores the cart', async () => {
    const cart = useCartStore()
    cart.add(item({ holdId: 'h-keep' }))
    await nextTick() // the persistence watcher runs on flush
    expect(localStorage.getItem('juggle.cart')).toContain('h-keep')

    // A fresh store (new pinia) hydrates from storage.
    setActivePinia(createPinia())
    const reloaded = useCartStore()
    expect(reloaded.count).toBe(1)
    expect(reloaded.items[0].holdId).toBe('h-keep')
  })
})
