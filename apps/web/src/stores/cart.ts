import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { api } from '@/lib/api'
import { storage } from '@/lib/storage'

/** A held session in the cart, plus the children who'll attend it. */
export interface CartItem {
  holdId: string
  sessionId: string
  title: string
  orgName: string
  venueName: string
  startsAt: string
  endsAt: string
  priceCents: number
  childIds: string[]
}

const CART_KEY = 'juggle.cart'

function load(): CartItem[] {
  try {
    const raw = storage.get(CART_KEY)
    return raw ? (JSON.parse(raw) as CartItem[]) : []
  } catch {
    return []
  }
}

export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>(load())

  watch(
    items,
    (val) => storage.set(CART_KEY, JSON.stringify(val)),
    { deep: true },
  )

  const count = computed(() => items.value.length)
  const seatCount = computed(() => items.value.reduce((n, i) => n + i.childIds.length, 0))
  const totalCents = computed(() =>
    items.value.reduce((sum, i) => sum + i.priceCents * i.childIds.length, 0),
  )

  function add(item: CartItem): void {
    items.value.push(item)
  }

  /** Remove an item and release its held seats back to inventory. */
  async function removeItem(holdId: string): Promise<void> {
    items.value = items.value.filter((i) => i.holdId !== holdId)
    try {
      await api.inventory.release(holdId)
    } catch {
      // Best effort — the hold will also expire on its own TTL.
    }
  }

  /** Clear after a successful checkout (holds are consumed, do not release). */
  function clearConsumed(): void {
    items.value = []
  }

  return { items, count, seatCount, totalCents, add, removeItem, clearConsumed }
})
