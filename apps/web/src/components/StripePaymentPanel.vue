<template>
  <div>
    <div ref="host" class="q-mb-md jg-element" />
    <div v-if="errorMsg" class="text-negative text-caption q-mb-sm">{{ errorMsg }}</div>
    <q-btn
      unelevated color="primary" no-caps size="lg" class="full-width"
      :loading="busy" :disable="!ready"
      :label="`Pay ${money(amountCents)}`" @click="pay"
    />
  </div>
</template>

<script setup lang="ts">
import { loadStripe, type Stripe, type StripeElements } from '@stripe/stripe-js'
import { onMounted, ref } from 'vue'

import { api } from '@/lib/api'
import { money } from '@/lib/format'

const props = defineProps<{
  publishableKey: string
  clientSecret: string
  paymentId: string
  amountCents: number
  returnUrl: string
}>()
const emit = defineEmits<{ (e: 'paid'): void; (e: 'pending'): void; (e: 'failed', msg: string): void }>()

const host = ref<HTMLElement | null>(null)
const ready = ref(false)
const busy = ref(false)
const errorMsg = ref('')
let stripe: Stripe | null = null
let elements: StripeElements | null = null

onMounted(async () => {
  stripe = await loadStripe(props.publishableKey)
  if (!stripe || !host.value) {
    errorMsg.value = 'Could not load the secure payment form. Please refresh and try again.'
    return
  }
  elements = stripe.elements({ clientSecret: props.clientSecret })
  elements.create('payment').mount(host.value)
  ready.value = true
})

// The booking is confirmed server-side by the Stripe webhook, so after the charge
// succeeds we poll the payment until it settles rather than trusting the client alone.
async function waitForConfirmation(): Promise<'succeeded' | 'failed' | 'pending'> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const payment = await api.payments.status(props.paymentId)
    if (payment.status === 'succeeded') return 'succeeded'
    if (payment.status === 'failed' || payment.status === 'refunded') return 'failed'
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  return 'pending'
}

async function pay(): Promise<void> {
  if (!stripe || !elements) return
  busy.value = true
  errorMsg.value = ''
  try {
    // redirect: 'if_required' keeps card payments inline; 3DS bounces to return_url,
    // where the checkout page resumes the poll from the query params.
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: props.returnUrl },
      redirect: 'if_required',
    })
    if (error) {
      errorMsg.value = error.message ?? 'Payment failed. Please try again.'
      emit('failed', errorMsg.value)
      return
    }
    const outcome = await waitForConfirmation()
    if (outcome === 'succeeded') emit('paid')
    else if (outcome === 'failed') emit('failed', 'The payment did not go through.')
    else emit('pending')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.jg-element {
  min-height: 44px;
}
</style>
