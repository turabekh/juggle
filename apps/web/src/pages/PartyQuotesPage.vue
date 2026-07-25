<template>
  <q-page class="jg-page" style="max-width: 760px">
    <div class="row items-center justify-between q-mb-lg">
      <h1 class="text-h4 q-my-none">Party quotes</h1>
      <q-btn
        v-if="available"
        unelevated color="primary" no-caps icon="add" label="New enquiry"
        @click="showForm = true"
      />
    </div>
    <p class="jg-muted q-mb-lg">
      Want something bespoke — an entertainer at your place, a custom package? Send the details
      and the provider replies with a price. You can ask for one revision, then it's yours to
      accept until it expires.
    </p>

    <div v-if="loading" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" /><span>Loading…</span>
    </div>

    <EmptyState
      v-else-if="!available"
      icon="request_quote"
      title="Quotes aren't switched on yet"
      subtitle="Bespoke party quotes are coming soon. In the meantime you can book any party package instantly."
    >
      <q-btn unelevated color="primary" no-caps label="Browse parties" :to="{ name: 'parties' }" />
    </EmptyState>

    <div v-else-if="requests.length" class="jg-list">
      <article v-for="r in requests" :key="r.id" class="jg-card q-pa-md q-mb-md">
        <div class="row items-start justify-between q-gutter-sm">
          <div>
            <div class="text-weight-600">{{ r.organisation_name }}</div>
            <div class="jg-faint text-caption">
              {{ dayLabel(r.starts_at) }} · {{ timeRange(r.starts_at, r.ends_at) }} ·
              {{ r.kid_count }} kids, ages {{ ageBand(r.child_age_min, r.child_age_max) }}
            </div>
            <div v-if="r.suburb" class="jg-faint text-caption">{{ r.suburb }}</div>
          </div>
          <q-chip dense square :color="statusColor(r.status)" text-color="white"
                  :label="statusLabel(r.status)" />
        </div>

        <p v-if="r.notes" class="q-mt-sm q-mb-none text-body2">{{ r.notes }}</p>

        <!-- The live quote -->
        <template v-if="r.quote">
          <q-separator class="q-my-md" />
          <div class="row items-center justify-between">
            <div class="text-weight-600">
              {{ money(r.quote.total_cents) }}
              <span class="jg-faint text-caption">
                · {{ money(r.quote.per_head_price_cents) }}/head × {{ r.quote.headcount }}
              </span>
            </div>
            <div class="jg-faint text-caption">
              Deposit today {{ money(r.quote.deposit_cents) }}
            </div>
          </div>
          <div class="jg-faint text-caption">
            {{ dayLabel(r.quote.starts_at) }} · {{ timeRange(r.quote.starts_at, r.quote.ends_at) }}
            <template v-if="r.quote.venue_name"> · {{ r.quote.venue_name }}</template>
          </div>
          <p v-if="r.quote.message" class="q-mt-sm q-mb-none text-body2">{{ r.quote.message }}</p>
          <div v-if="r.quote.revision_message" class="jg-faint text-caption q-mt-sm">
            You asked: “{{ r.quote.revision_message }}”
          </div>

          <div v-if="isOpen(r.quote)" class="q-mt-md">
            <div class="jg-faint text-caption q-mb-sm">
              Expires {{ dayLabel(r.quote.expires_at) }}
            </div>
            <q-btn
              unelevated color="primary" no-caps icon="check" label="Accept & pay deposit"
              :loading="busy === r.quote.id" @click="accept(r.quote)"
            />
            <q-btn
              v-if="r.quote.can_request_revision"
              flat no-caps color="primary" class="q-ml-sm" icon="edit_note"
              label="Ask for a change" @click="openRevision(r.quote)"
            />
          </div>
          <div v-else-if="r.quote.status === 'revision_requested'" class="jg-faint q-mt-md">
            Waiting on the provider's revised quote.
          </div>

          <!-- Deposit settlement, identical to instant-book: it IS the same booking. -->
          <div v-if="pending && pending.id === r.quote.booking_id" class="q-mt-md">
            <q-separator class="q-mb-md" />
            <div class="row items-center q-gutter-sm q-mb-sm">
              <q-icon name="lock" color="positive" />
              <span class="jg-muted text-caption">
                {{ live ? 'Secure payment · Stripe' : 'Secure payment · demo gateway' }}
              </span>
            </div>
            <StripePaymentPanel
              v-if="live && pending.client_secret"
              :publishable-key="publishableKey"
              :client-secret="pending.client_secret"
              :payment-id="pending.id"
              :amount-cents="pending.deposit_cents"
              :return-url="returnUrl"
              @paid="onDepositPaid"
              @failed="onDepositFailed"
            />
            <q-btn
              v-else-if="!live"
              unelevated color="primary" no-caps size="lg" class="full-width"
              :loading="confirming" :label="`Pay deposit ${money(pending.deposit_cents)}`"
              @click="payDepositDev"
            />
          </div>
        </template>

        <div v-if="canWithdraw(r)" class="q-mt-md">
          <q-btn flat dense no-caps size="sm" color="negative" label="Withdraw enquiry"
                 @click="withdraw(r)" />
        </div>
      </article>
    </div>

    <EmptyState
      v-else
      icon="request_quote"
      title="No enquiries yet"
      subtitle="Ask a provider to quote for a bespoke party."
    >
      <q-btn unelevated color="primary" no-caps label="New enquiry" @click="showForm = true" />
    </EmptyState>

    <!-- Brief form -->
    <q-dialog v-model="showForm">
      <q-card style="min-width: 460px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Request a quote</div>
          <div class="jg-faint text-caption">
            Structured details only — the provider replies with one price and what's included.
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-select
            v-model="form.organisation_id" outlined dense emit-value map-options
            :options="providerOptions" label="Provider"
          />
          <q-input v-model="form.date" outlined dense type="date" label="Party date" />
          <div class="row q-col-gutter-sm">
            <q-input v-model="form.start" class="col" outlined dense type="time" label="Start" />
            <q-input v-model="form.end" class="col" outlined dense type="time" label="End" />
          </div>
          <q-input v-model="form.suburb" outlined dense label="Suburb" />
          <div class="row q-col-gutter-sm">
            <q-input
              v-model.number="form.kid_count" class="col" outlined dense type="number"
              label="How many kids" min="1"
            />
            <q-input
              v-model.number="form.child_age_min" class="col" outlined dense type="number"
              label="Youngest age" min="0"
            />
            <q-input
              v-model.number="form.child_age_max" class="col" outlined dense type="number"
              label="Oldest age" min="0"
            />
          </div>
          <q-input
            v-model.number="form.budget" outlined dense type="number" label="Budget (optional, $)"
          />
          <q-input
            v-model="form.notes" outlined dense type="textarea" autogrow maxlength="1000" counter
            label="Anything else? (optional)"
            hint="Theme, allergies to plan around, access notes — please don't include kids' names"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="Send enquiry"
            :loading="submitting" :disable="!formValid" @click="submit"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import StripePaymentPanel from '@/components/StripePaymentPanel.vue'
import { api, apiError } from '@/lib/api'
import { ageBand, dayLabel, money, timeRange } from '@/lib/format'
import { siteOrigin } from '@/lib/head'
import type {
  PartyBooking, PartyPackageDetail, PartyQuote, PartyQuoteRequest,
} from '@/lib/types'

const $q = useQuasar()

const loading = ref(true)
/** The just-accepted booking awaiting its deposit — the same shape instant-book produces. */
const pending = ref<PartyBooking | null>(null)
const confirming = ref(false)
const live = ref(false)
const publishableKey = ref('')
const returnUrl = computed(() => `${siteOrigin()}/parties/quotes`)
/** False when the `party_quotes` flag is off — every endpoint 404s, so we hide the feature. */
const available = ref(true)
const requests = ref<PartyQuoteRequest[]>([])
const providerOptions = ref<{ label: string; value: string }[]>([])
const showForm = ref(false)
const submitting = ref(false)
const busy = ref<string | null>(null)

const form = reactive({
  organisation_id: '',
  date: '',
  start: '10:00',
  end: '12:00',
  suburb: '',
  kid_count: 10,
  child_age_min: 5,
  child_age_max: 8,
  budget: null as number | null,
  notes: '',
})

const formValid = computed(
  () =>
    !!form.organisation_id && !!form.date && !!form.start && !!form.end && !!form.suburb &&
    form.kid_count >= 1 && form.child_age_max >= form.child_age_min,
)

function isOpen(quote: PartyQuote): boolean {
  return quote.status === 'sent' || quote.status === 'revised'
}

function canWithdraw(r: PartyQuoteRequest): boolean {
  return r.status === 'submitted' || r.status === 'quoted'
}

function statusLabel(status: PartyQuoteRequest['status']): string {
  return {
    submitted: 'Sent', quoted: 'Quoted', accepted: 'Booked',
    declined: 'Declined', withdrawn: 'Withdrawn', expired: 'Expired',
  }[status]
}

function statusColor(status: PartyQuoteRequest['status']): string {
  return {
    submitted: 'grey-7', quoted: 'primary', accepted: 'positive',
    declined: 'grey-6', withdrawn: 'grey-6', expired: 'grey-6',
  }[status]
}

async function load(): Promise<void> {
  loading.value = true
  try {
    requests.value = await api.partyQuotes.myRequests()
    available.value = true
  } catch (err) {
    // A 404 here means the feature flag is off, not that something broke.
    available.value = false
  } finally {
    loading.value = false
  }
  try {
    const cfg = await api.payments.config()
    live.value = cfg.live
    publishableKey.value = cfg.publishable_key ?? ''
  } catch {
    /* falls back to the dev deposit button */
  }
  try {
    const packages: PartyPackageDetail[] = await api.parties.allPackages()
    const seen = new Map<string, string>()
    for (const p of packages) seen.set(p.organisation_id, p.organisation_name)
    providerOptions.value = [...seen].map(([value, label]) => ({ label, value }))
  } catch {
    /* provider list is a convenience; the form still works if it fails */
  }
}

async function submit(): Promise<void> {
  submitting.value = true
  try {
    await api.partyQuotes.createRequest({
      organisation_id: form.organisation_id,
      starts_at: new Date(`${form.date}T${form.start}`).toISOString(),
      ends_at: new Date(`${form.date}T${form.end}`).toISOString(),
      suburb: form.suburb,
      kid_count: form.kid_count,
      child_age_min: form.child_age_min,
      child_age_max: form.child_age_max,
      budget_cents: form.budget ? Math.round(form.budget * 100) : null,
      notes: form.notes || null,
    })
    showForm.value = false
    $q.notify({ type: 'positive', message: 'Enquiry sent — the provider will reply with a quote.' })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not send the enquiry') })
  } finally {
    submitting.value = false
  }
}

function openRevision(quote: PartyQuote): void {
  $q.dialog({
    title: 'Ask for a change',
    message: "One revision per quote — say what you'd like adjusted.",
    prompt: { model: '', type: 'textarea', isValid: (v: string) => v.trim().length > 0 },
    cancel: true,
    ok: { label: 'Send', color: 'primary', unelevated: true, noCaps: true },
  }).onOk(async (message: string) => {
    try {
      await api.partyQuotes.requestRevision(quote.id, message)
      $q.notify({ type: 'info', message: 'Sent — the provider can reply with one revised quote.' })
      await load()
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err) })
    }
  })
}

async function accept(quote: PartyQuote): Promise<void> {
  busy.value = quote.id
  try {
    pending.value = await api.partyQuotes.accept(quote.id)
    $q.notify({ type: 'positive', message: 'Quote accepted — pay the deposit to lock the date in.' })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not accept the quote') })
    await load()
  } finally {
    busy.value = null
  }
}

async function payDepositDev(): Promise<void> {
  if (!pending.value) return
  confirming.value = true
  try {
    await api.parties.devConfirm(pending.value.id)
    pending.value = null
    $q.notify({ type: 'positive', message: 'Deposit paid — your party is booked 🎉' })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not take the deposit') })
  } finally {
    confirming.value = false
  }
}

function onDepositPaid(): void {
  pending.value = null
  $q.notify({ type: 'positive', message: 'Deposit paid — your party is booked 🎉' })
  void load()
}

function onDepositFailed(message: string): void {
  $q.notify({ type: 'negative', message })
}

function withdraw(r: PartyQuoteRequest): void {
  $q.dialog({
    title: 'Withdraw this enquiry?',
    message: `${r.organisation_name} will no longer be able to quote for it.`,
    cancel: true,
    ok: { label: 'Withdraw', color: 'negative', unelevated: true, noCaps: true },
  }).onOk(async () => {
    try {
      await api.partyQuotes.withdrawRequest(r.id)
      await load()
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err) })
    }
  })
}

onMounted(load)
</script>
