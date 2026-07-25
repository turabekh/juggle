<template>
  <q-page class="jg-page" style="max-width: 640px">
    <q-btn flat dense no-caps icon="arrow_back" label="Back to cart" :to="{ name: 'cart' }" class="jg-muted q-mb-md" />
    <h1 class="text-h4 q-mb-lg">Checkout</h1>

    <div v-if="resuming" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" />
      <span>Confirming your payment…</span>
    </div>

    <template v-else-if="cart.items.length">
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
          <span class="jg-muted text-caption">{{ live ? 'Secure payment · Stripe' : 'Secure payment · demo gateway' }}</span>
        </div>

        <!-- Live Stripe: create the order, then take card details in the Payment Element. -->
        <template v-if="live">
          <StripePaymentPanel
            v-if="order && order.client_secret"
            :publishable-key="publishableKey"
            :client-secret="order.client_secret"
            :payment-id="order.payment_id"
            :amount-cents="cart.totalCents"
            :return-url="returnUrl(order.payment_id)"
            @paid="onPaid"
            @failed="onFailed"
            @pending="onPending"
          />
          <q-btn
            v-else unelevated color="primary" no-caps size="lg" class="full-width"
            :loading="preparing" label="Continue to payment" @click="startOrder"
          />
        </template>

        <!-- Dev / FakeGateway: one-click confirm (no real card). -->
        <q-btn
          v-else
          unelevated color="primary" no-caps size="lg" class="full-width"
          :loading="paying" :label="`Pay ${money(cart.totalCents)}`" @click="payDev"
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
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StripePaymentPanel from '@/components/StripePaymentPanel.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money } from '@/lib/format'
import { siteOrigin } from '@/lib/head'
import type { Order } from '@/lib/types'
import { useCartStore } from '@/stores/cart'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const cart = useCartStore()

const live = ref(false)
const publishableKey = ref('')
const order = ref<Order | null>(null)
const preparing = ref(false)
const paying = ref(false)
const resuming = ref(false)
// Stable per-attempt key so a retry after a network blip is idempotent.
const idempotencyKey = ref(crypto.randomUUID())

function returnUrl(paymentId: string): string {
  return `${siteOrigin()}/checkout?pid=${paymentId}`
}

function finish(): void {
  cart.clearConsumed()
  $q.notify({ type: 'positive', message: 'Booked! See you there 🎉' })
  void router.push({ name: 'bookings' })
}

function onPaid(): void {
  finish()
}
function onPending(): void {
  cart.clearConsumed()
  $q.notify({
    type: 'info',
    message: 'Payment received — your booking will appear shortly.',
  })
  void router.push({ name: 'bookings' })
}
function onFailed(msg: string): void {
  order.value = null // let them retry with a fresh order
  idempotencyKey.value = crypto.randomUUID()
  $q.notify({ type: 'negative', message: msg })
}

async function startOrder(): Promise<void> {
  preparing.value = true
  try {
    const items = cart.items.map((i) => ({
      hold_id: i.holdId,
      children: i.childIds.map((cid) => ({ child_id: cid })),
    }))
    order.value = await api.booking.checkout(idempotencyKey.value, items)
    if (!order.value.client_secret) {
      throw new Error('Payment could not be initialised.')
    }
  } catch (err) {
    idempotencyKey.value = crypto.randomUUID()
    $q.notify({ type: 'negative', message: apiError(err, 'Could not start payment') })
  } finally {
    preparing.value = false
  }
}

async function payDev(): Promise<void> {
  paying.value = true
  try {
    const items = cart.items.map((i) => ({
      hold_id: i.holdId,
      children: i.childIds.map((cid) => ({ child_id: cid })),
    }))
    const created = await api.booking.checkout(idempotencyKey.value, items)
    await api.booking.confirm(created.payment_id)
    finish()
  } catch (err) {
    idempotencyKey.value = crypto.randomUUID()
    $q.notify({ type: 'negative', message: apiError(err, 'Payment could not be completed') })
  } finally {
    paying.value = false
  }
}

// Poll a payment to its terminal state (booking is confirmed by the webhook).
async function pollPayment(paymentId: string): Promise<'succeeded' | 'failed' | 'pending'> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const payment = await api.payments.status(paymentId)
    if (payment.status === 'succeeded') return 'succeeded'
    if (payment.status === 'failed' || payment.status === 'refunded') return 'failed'
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  return 'pending'
}

onMounted(async () => {
  try {
    const config = await api.payments.config()
    live.value = config.live && !!config.publishable_key
    publishableKey.value = config.publishable_key ?? ''
  } catch {
    live.value = false // fall back to the dev flow if config can't be read
  }

  // Returning from a 3DS redirect: Stripe appends redirect_status and preserves our ?pid.
  const pid = route.query.pid
  if (typeof pid === 'string' && route.query.redirect_status) {
    resuming.value = true
    const outcome = await pollPayment(pid)
    resuming.value = false
    if (outcome === 'succeeded') finish()
    else if (outcome === 'pending') onPending()
    else $q.notify({ type: 'negative', message: 'The payment did not go through.' })
  }
})
</script>

<style scoped>
.jg-sumrow {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 8px 0;
}
/* Offset by the mobile tab bar (0 on desktop) so the Pay button is never hidden
   behind it — this is the last step of checkout, it has to stay reachable. */
.jg-pay { position: sticky; bottom: calc(12px + var(--jg-tabbar-h, 0px)); }
</style>
