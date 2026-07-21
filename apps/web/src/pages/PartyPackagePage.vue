<template>
  <q-page class="jg-page" style="max-width: 640px">
    <q-btn
      flat dense no-caps icon="arrow_back" label="Back"
      class="jg-muted q-mb-md" @click="router.back()"
    />

    <div v-if="loading" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" />
      <span>Loading party details…</span>
    </div>

    <EmptyState
      v-else-if="!pkg"
      icon="celebration"
      title="Party not found"
      subtitle="This party package isn't available."
    >
      <q-btn unelevated color="primary" no-caps label="Browse activities" :to="{ name: 'discover' }" />
    </EmptyState>

    <template v-else>
      <!-- Package header -->
      <h1 class="text-h4 q-mb-xs">{{ pkg.name }}</h1>
      <div class="jg-muted q-mb-md">
        {{ pkg.organisation_name }} · {{ pkg.venue_name
        }}<template v-if="pkg.venue_suburb">, {{ pkg.venue_suburb }}</template>
      </div>
      <p v-if="pkg.description" class="q-mb-md">{{ pkg.description }}</p>
      <div class="row q-gutter-sm q-mb-lg">
        <q-chip dense square icon="payments" :label="`${money(pkg.per_head_price_cents)} per guest`" />
        <q-chip dense square icon="groups" :label="`${pkg.min_headcount}–${pkg.max_headcount} guests`" />
        <q-chip v-if="pkg.outdoor" dense square icon="wb_sunny" label="Outdoor" />
      </div>

      <!-- Confirmed booking -->
      <div v-if="booked" class="jg-card q-pa-lg">
        <div class="row items-center q-gutter-sm q-mb-md">
          <q-icon name="check_circle" color="positive" size="28px" />
          <div class="text-h6">Party booked 🎉</div>
        </div>
        <div class="jg-sumrow">
          <span class="jg-muted">Guests</span><span class="text-weight-600">{{ booked.headcount }}</span>
        </div>
        <div class="jg-sumrow">
          <span class="jg-muted">Deposit paid</span><span class="text-weight-600">{{ money(booked.deposit_cents) }}</span>
        </div>
        <div class="jg-sumrow">
          <span class="jg-muted">Balance due</span><span class="text-weight-600">{{ money(booked.balance_cents) }}</span>
        </div>
        <div class="jg-faint text-caption q-mt-sm">
          The remaining balance is charged automatically to your card about a week before the party.
        </div>

        <q-separator class="q-my-md" />
        <div class="text-weight-600 q-mb-sm">Manage your booking</div>
        <div class="row items-end q-gutter-sm q-mb-md">
          <q-input
            v-model.number="adjustCount" type="number" outlined dense
            label="Guest count" :min="pkg.min_headcount" :max="pkg.max_headcount"
            style="max-width: 140px"
          />
          <q-btn
            no-caps unelevated color="primary" label="Update guests" :loading="adjusting"
            :disable="adjustCount === booked.headcount || !adjustValid" @click="doAdjust"
          />
        </div>
        <div class="jg-faint text-caption q-mb-md">
          You can change the guest count up to 72 hours before the party.
        </div>
        <q-btn
          flat no-caps color="negative" label="Cancel booking" :loading="cancelling" @click="doCancel"
        />
      </div>

      <!-- Deposit payment (after reserving a slot) -->
      <div v-else-if="pending" class="jg-card q-pa-lg jg-pay">
        <div class="text-weight-600 q-mb-sm">Pay your deposit to confirm</div>
        <div class="jg-sumrow">
          <span class="jg-muted">{{ pending.headcount }} guests × {{ money(pkg.per_head_price_cents) }}</span>
          <span class="text-weight-600">{{ money(pending.total_cents) }}</span>
        </div>
        <div class="jg-sumrow">
          <span class="jg-muted">Deposit due now ({{ pkg.deposit_pct_effective }}%)</span>
          <span class="text-weight-600">{{ money(pending.deposit_cents) }}</span>
        </div>
        <div class="jg-sumrow">
          <span class="jg-muted">Balance later</span><span>{{ money(pending.balance_cents) }}</span>
        </div>
        <q-separator class="q-my-md" />
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-icon name="lock" color="positive" />
          <span class="jg-muted text-caption">{{ live ? 'Secure payment · Stripe' : 'Secure payment · demo gateway' }}</span>
        </div>
        <StripePaymentPanel
          v-if="live && pending.client_secret"
          :publishable-key="publishableKey"
          :client-secret="pending.client_secret"
          :payment-id="pending.id"
          :amount-cents="pending.deposit_cents"
          :return-url="returnUrl"
          @paid="onDepositPaid"
          @pending="onDepositPending"
          @failed="onDepositFailed"
        />
        <q-btn
          v-else-if="!live"
          unelevated color="primary" no-caps size="lg" class="full-width"
          :loading="confirming" :label="`Pay deposit ${money(pending.deposit_cents)}`"
          @click="payDepositDev"
        />
      </div>

      <!-- Slot picker + headcount -->
      <div v-else class="jg-card q-pa-lg">
        <div class="text-weight-600 q-mb-sm">Choose a date</div>
        <div v-if="slots.length" class="q-mb-lg">
          <q-list bordered class="rounded-borders">
            <q-item
              v-for="s in slots" :key="s.id" clickable :active="selectedSlot === s.id"
              active-class="jg-slot-active" @click="selectedSlot = s.id"
            >
              <q-item-section>
                <q-item-label>{{ dayLabel(s.starts_at) }}</q-item-label>
                <q-item-label caption>{{ timeRange(s.starts_at, s.ends_at) }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-icon v-if="selectedSlot === s.id" name="check_circle" color="primary" />
              </q-item-section>
            </q-item>
          </q-list>
        </div>
        <div v-else class="jg-muted text-caption q-mb-md">
          No upcoming dates available right now — check back soon.
        </div>

        <template v-if="slots.length">
          <div class="text-weight-600 q-mb-sm">How many guests?</div>
          <q-input
            v-model.number="headcount" type="number" outlined dense
            :min="pkg.min_headcount" :max="pkg.max_headcount"
            :hint="`Between ${pkg.min_headcount} and ${pkg.max_headcount} guests`"
            style="max-width: 200px" class="q-mb-md"
          />
          <div v-if="headcountValid" class="jg-sumrow">
            <span class="jg-muted">Estimated total</span>
            <span class="text-weight-600">{{ money(estimatedTotal) }}</span>
          </div>
          <div v-if="headcountValid" class="jg-sumrow">
            <span class="jg-muted">Deposit due now ({{ pkg.deposit_pct_effective }}%)</span>
            <span class="text-weight-600">{{ money(estimatedDeposit) }}</span>
          </div>
          <q-btn
            unelevated color="primary" no-caps size="lg" class="full-width q-mt-md"
            :loading="reserving" :disable="!selectedSlot || !headcountValid"
            label="Reserve &amp; pay deposit" @click="reserve"
          />
        </template>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StripePaymentPanel from '@/components/StripePaymentPanel.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money, timeRange } from '@/lib/format'
import { siteOrigin } from '@/lib/head'
import type { PartyBooking, PartyPackageDetail, PartySlot } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ id: string }>()
const $q = useQuasar()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const pkg = ref<PartyPackageDetail | null>(null)
const slots = ref<PartySlot[]>([])
const selectedSlot = ref<string | null>(null)
const headcount = ref<number | null>(null)

const live = ref(false)
const publishableKey = ref('')

const reserving = ref(false)
const confirming = ref(false)
const adjusting = ref(false)
const cancelling = ref(false)

const pending = ref<PartyBooking | null>(null) // reserved, awaiting deposit
const booked = ref<PartyBooking | null>(null) // deposit confirmed
const adjustCount = ref<number>(0)

const returnUrl = computed(() => `${siteOrigin()}/parties/packages/${props.id}`)

const headcountValid = computed(
  () =>
    !!pkg.value &&
    typeof headcount.value === 'number' &&
    headcount.value >= pkg.value.min_headcount &&
    headcount.value <= pkg.value.max_headcount,
)
const estimatedTotal = computed(() =>
  pkg.value && typeof headcount.value === 'number'
    ? pkg.value.per_head_price_cents * headcount.value
    : 0,
)
const estimatedDeposit = computed(() =>
  pkg.value ? Math.round((estimatedTotal.value * pkg.value.deposit_pct_effective) / 100) : 0,
)
const adjustValid = computed(
  () =>
    !!pkg.value &&
    adjustCount.value >= pkg.value.min_headcount &&
    adjustCount.value <= pkg.value.max_headcount,
)

async function reserve(): Promise<void> {
  if (!auth.isAuthed) {
    void router.push({ name: 'login', query: { redirect: returnUrl.value.replace(siteOrigin(), '') } })
    return
  }
  if (!selectedSlot.value || typeof headcount.value !== 'number') return
  reserving.value = true
  try {
    pending.value = await api.parties.book(selectedSlot.value, headcount.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not reserve that date') })
  } finally {
    reserving.value = false
  }
}

async function payDepositDev(): Promise<void> {
  if (!pending.value) return
  confirming.value = true
  try {
    booked.value = await api.parties.devConfirm(pending.value.id)
    adjustCount.value = booked.value.headcount
    pending.value = null
    $q.notify({ type: 'positive', message: 'Deposit paid — your party is booked 🎉' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Deposit could not be confirmed') })
  } finally {
    confirming.value = false
  }
}

function onDepositPaid(): void {
  if (pending.value) {
    booked.value = { ...pending.value }
    adjustCount.value = pending.value.headcount
    pending.value = null
  }
  $q.notify({ type: 'positive', message: 'Deposit paid — your party is booked 🎉' })
}
function onDepositPending(): void {
  pending.value = null
  $q.notify({ type: 'info', message: 'Deposit received — your booking will confirm shortly.' })
  void router.push({ name: 'bookings' })
}
function onDepositFailed(msg: string): void {
  $q.notify({ type: 'negative', message: msg })
}

async function doAdjust(): Promise<void> {
  if (!booked.value) return
  adjusting.value = true
  try {
    booked.value = await api.parties.adjust(booked.value.id, adjustCount.value)
    adjustCount.value = booked.value.headcount
    $q.notify({ type: 'positive', message: 'Guest count updated' })
  } catch (err) {
    if (booked.value) adjustCount.value = booked.value.headcount
    $q.notify({ type: 'negative', message: apiError(err, 'Could not update guest count') })
  } finally {
    adjusting.value = false
  }
}

async function doCancel(): Promise<void> {
  if (!booked.value) return
  $q.dialog({
    title: 'Cancel party?',
    message: 'Your deposit may be retained per the cancellation policy. This cannot be undone.',
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    if (!booked.value) return
    cancelling.value = true
    try {
      await api.parties.cancel(booked.value.id)
      booked.value = null
      $q.notify({ type: 'info', message: 'Your party booking has been cancelled.' })
      void router.push({ name: 'bookings' })
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err, 'Could not cancel the booking') })
    } finally {
      cancelling.value = false
    }
  })
}

onMounted(async () => {
  try {
    const config = await api.payments.config()
    live.value = config.live && !!config.publishable_key
    publishableKey.value = config.publishable_key ?? ''
  } catch {
    live.value = false
  }
  try {
    pkg.value = await api.parties.package(props.id)
    slots.value = await api.parties.slots(props.id)
    headcount.value = pkg.value.min_headcount
  } catch {
    pkg.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-sumrow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}
.jg-pay {
  position: sticky;
  bottom: 12px;
}
.jg-slot-active {
  background: rgba(25, 118, 210, 0.08);
}
</style>
