<template>
  <q-page class="jg-page" style="max-width: 640px">
    <q-btn flat dense no-caps icon="arrow_back" label="Back to cart" :to="{ name: 'cart' }" class="jg-muted q-mb-md" />
    <h1 class="text-h4 q-mb-lg">Checkout</h1>

    <template v-if="cart.items.length">
      <div class="jg-card q-pa-lg">
        <div class="text-weight-600 q-mb-md">Order summary</div>
        <div v-for="item in cart.items" :key="item.holdId" class="jg-sumrow">
          <div>
            <div class="text-weight-500">{{ item.title }}</div>
            <div class="jg-faint text-caption">
              {{ dayLabel(item.startsAt) }} · {{ item.childIds.length }} × {{ money(item.priceCents) }}
            </div>
          </div>
          <div class="text-weight-600">{{ money(item.priceCents * item.childIds.length) }}</div>
        </div>
        <q-separator class="q-my-md" />
        <div class="row items-center justify-between">
          <span class="text-subtitle1 text-weight-600">Total</span>
          <span class="text-h6">{{ money(cart.totalCents) }}</span>
        </div>
      </div>

      <div class="jg-card q-pa-lg q-mt-md jg-pay">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-icon name="lock" color="positive" />
          <span class="jg-muted text-caption">Secure payment · demo gateway</span>
        </div>
        <q-btn
          unelevated
          color="primary"
          no-caps
          size="lg"
          class="full-width"
          :loading="paying"
          :label="`Pay ${money(cart.totalCents)}`"
          @click="pay"
        />
      </div>
    </template>

    <EmptyState
      v-else
      icon="shopping_bag"
      title="Nothing to check out"
      subtitle="Your cart is empty."
    >
      <q-btn unelevated color="primary" no-caps label="Browse activities" :to="{ name: 'discover' }" />
    </EmptyState>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money } from '@/lib/format'
import { useCartStore } from '@/stores/cart'

const $q = useQuasar()
const router = useRouter()
const cart = useCartStore()

const paying = ref(false)
// Stable per-attempt key so a retry after a network blip is idempotent.
const idempotencyKey = ref(crypto.randomUUID())

async function pay(): Promise<void> {
  paying.value = true
  try {
    const items = cart.items.map((i) => ({
      hold_id: i.holdId,
      children: i.childIds.map((cid) => ({ child_id: cid })),
    }))
    const order = await api.booking.checkout(idempotencyKey.value, items)
    await api.booking.confirm(order.payment_id)
    cart.clearConsumed()
    $q.notify({ type: 'positive', message: 'Booked! See you there 🎉' })
    router.push({ name: 'bookings' })
  } catch (err) {
    // New key next attempt if the order never formed; otherwise the same order
    // is returned idempotently.
    idempotencyKey.value = crypto.randomUUID()
    $q.notify({ type: 'negative', message: apiError(err, 'Payment could not be completed') })
  } finally {
    paying.value = false
  }
}
</script>

<style scoped>
.jg-sumrow {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 8px 0;
}
.jg-pay { position: sticky; bottom: 12px; }
</style>
