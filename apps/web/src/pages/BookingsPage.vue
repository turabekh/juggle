<template>
  <q-page class="jg-page" style="max-width: 780px">
    <h1 class="text-h4 q-mb-lg">My bookings</h1>

    <!-- Waitlist (PRD §7.7) -->
    <section v-if="waitlist.length" class="q-mb-xl">
      <h2 class="text-h6 q-mb-sm">Waitlist</h2>
      <div class="jg-bookings">
        <div
          v-for="w in waitlist"
          :key="w.id"
          class="jg-card jg-bookrow"
          :class="{ 'jg-offer': w.status === 'offered' }"
        >
          <div>
            <div class="text-weight-600">{{ w.program_title }}</div>
            <div class="jg-muted text-caption">
              <q-icon name="event" size="14px" /> {{ dayLabel(w.starts_at) }}
            </div>
            <div
              v-if="w.status === 'offered'"
              class="text-positive text-caption text-weight-600 q-mt-xs"
            >
              <q-icon name="celebration" size="14px" /> Seat available — claim by
              {{ deadline(w.offer_expires_at) }}
            </div>
            <div v-else class="jg-faint text-caption q-mt-xs">
              #{{ w.position }} in the queue
            </div>
          </div>
          <div class="column items-end q-gutter-xs">
            <q-btn
              v-if="w.status === 'offered'"
              unelevated dense no-caps size="sm" color="positive"
              icon="confirmation_number" label="Claim seat" @click="openClaim(w)"
            />
            <q-btn
              flat dense no-caps size="sm" color="grey-7" label="Leave" @click="leave(w)"
            />
          </div>
        </div>
      </div>
    </section>

    <div v-if="loading" class="q-gutter-md">
      <q-skeleton v-for="n in 3" :key="n" type="rect" height="90px" style="border-radius: 16px" />
    </div>

    <div v-else-if="bookings.length" class="jg-bookings">
      <div v-for="b in bookings" :key="b.id" class="jg-card jg-bookrow">
        <div>
          <div class="text-weight-600">{{ title(b.session_id) }}</div>
          <div class="jg-muted text-caption" v-if="memo(b.session_id)">
            <q-icon name="event" size="14px" />
            {{ dayLabel(memo(b.session_id)!.startsAt) }} ·
            {{ timeRange(memo(b.session_id)!.startsAt, memo(b.session_id)!.endsAt) }}
          </div>
          <div class="jg-faint text-caption q-mt-xs">
            {{ b.children.length }} {{ b.children.length === 1 ? 'child' : 'children' }} ·
            {{ money(b.unit_price_cents * b.children.length) }}
          </div>
          <div v-if="b.status === 'confirmed'" class="jg-faint text-caption q-mt-xs">
            <q-icon name="mark_email_read" size="14px" /> Confirmation emailed
          </div>
        </div>
        <div class="column items-end q-gutter-xs">
          <q-chip
            :color="statusColor(b.status)"
            text-color="white"
            :label="statusLabel(b.status)"
            class="text-weight-600 q-ma-none"
          />
          <q-btn
            v-if="b.status === 'confirmed' && b.payment_id"
            flat dense no-caps size="sm" color="primary" icon="event"
            label="Add to calendar" @click="downloadIcs(b.payment_id)"
          />
          <q-btn
            v-if="reviewable.has(b.id)"
            unelevated dense no-caps size="sm" color="primary" icon="rate_review"
            label="Leave a review" @click="openReview(b.id)"
          />
        </div>
      </div>
    </div>

    <EmptyState
      v-else
      icon="confirmation_number"
      title="No bookings yet"
      subtitle="When you book an activity, it'll show up here."
    >
      <q-btn unelevated color="primary" no-caps label="Find activities" :to="{ name: 'discover' }" />
    </EmptyState>

    <!-- Claim waitlist seat dialog -->
    <q-dialog v-model="showClaim">
      <q-card style="min-width: 380px; max-width: 460px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Claim your seat</div>
          <div class="jg-faint text-caption">{{ claimEntry?.program_title }}</div>
        </q-card-section>
        <q-card-section>
          <div v-if="!children.length" class="jg-muted">
            Add a child from any listing first, then come back to claim.
          </div>
          <q-option-group
            v-else v-model="claimChildId" type="radio" color="primary"
            :options="claimChildOptions"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated color="positive" no-caps label="Book seat"
            :loading="claiming" :disable="!claimChildId" @click="submitClaim"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Leave a review dialog -->
    <q-dialog v-model="showReview">
      <q-card style="min-width: 380px; max-width: 460px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">How was it?</div>
          <div class="jg-faint text-caption">
            Your review is verified against your booking and checked before it goes live.
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <StarRating v-model="reviewForm.rating" editable size="30px" />
          <q-input
            v-model="reviewForm.body"
            outlined type="textarea" autogrow
            label="Tell other parents about it"
            hint="Please don't include your child's name."
            :rules="[(v) => !!v.trim() || 'Add a few words']"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated color="primary" no-caps label="Submit review"
            :loading="submitting"
            :disable="reviewForm.rating < 1 || !reviewForm.body.trim()"
            @click="submitReview"
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
import StarRating from '@/components/StarRating.vue'
import { api, apiError } from '@/lib/api'
import { ageAt, dayLabel, money, timeRange } from '@/lib/format'
import { recallSession, type SessionMemo } from '@/lib/sessionMemo'
import type { Booking, Child, WaitlistEntry } from '@/lib/types'

const $q = useQuasar()
const bookings = ref<Booking[]>([])
const loading = ref(true)

// --- Waitlist (PRD §7.7) ---
const waitlist = ref<WaitlistEntry[]>([])
const children = ref<Child[]>([])
const showClaim = ref(false)
const claiming = ref(false)
const claimEntry = ref<WaitlistEntry | null>(null)
const claimChildId = ref<string | null>(null)

const claimChildOptions = computed(() =>
  children.value.map((c) => ({
    label: claimEntry.value
      ? `${c.first_name} (${ageAt(c.date_of_birth, claimEntry.value.starts_at)} yrs)`
      : c.first_name,
    value: c.id,
  })),
)

function deadline(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-AU', {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

async function loadWaitlist(): Promise<void> {
  try {
    waitlist.value = await api.waitlist.mine()
  } catch {
    /* non-fatal */
  }
}

async function openClaim(entry: WaitlistEntry): Promise<void> {
  claimEntry.value = entry
  claimChildId.value = null
  showClaim.value = true
  if (!children.value.length) {
    try {
      children.value = await api.children.list()
    } catch {
      /* non-fatal */
    }
  }
}

async function submitClaim(): Promise<void> {
  if (!claimEntry.value || !claimChildId.value) return
  claiming.value = true
  try {
    const order = await api.booking.checkout(`claim-${claimEntry.value.id}`, [
      { hold_id: claimEntry.value.offer_hold_id as string, children: [{ child_id: claimChildId.value }] },
    ])
    await api.booking.confirm(order.payment_id)
    showClaim.value = false
    $q.notify({ type: 'positive', message: 'Seat claimed — see you there!' })
    await Promise.all([reload(), loadWaitlist()])
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not claim the seat') })
  } finally {
    claiming.value = false
  }
}

async function leave(entry: WaitlistEntry): Promise<void> {
  try {
    await api.waitlist.leave(entry.id)
    waitlist.value = waitlist.value.filter((w) => w.id !== entry.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function reload(): Promise<void> {
  bookings.value = await api.booking.list()
}

// Booking ids the guardian can review (confirmed + session finished + unreviewed).
const reviewable = ref<Set<string>>(new Set())
const showReview = ref(false)
const submitting = ref(false)
const reviewForm = reactive({ bookingId: '', rating: 0, body: '' })

function openReview(bookingId: string): void {
  Object.assign(reviewForm, { bookingId, rating: 0, body: '' })
  showReview.value = true
}

async function submitReview(): Promise<void> {
  submitting.value = true
  try {
    await api.reviews.submit({
      booking_id: reviewForm.bookingId,
      rating: reviewForm.rating,
      body: reviewForm.body.trim(),
    })
    reviewable.value.delete(reviewForm.bookingId)
    showReview.value = false
    $q.notify({ type: 'positive', message: 'Thanks! Your review will appear once approved.' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not submit review') })
  } finally {
    submitting.value = false
  }
}

function memo(id: string): SessionMemo | null {
  return recallSession(id)
}
function title(id: string): string {
  return memo(id)?.title ?? 'Activity'
}

async function downloadIcs(paymentId: string): Promise<void> {
  try {
    const text = await api.booking.calendarIcs(paymentId)
    const url = URL.createObjectURL(new Blob([text], { type: 'text/calendar' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'juggle-bookings.ics'
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

const STATUS: Record<string, { label: string; color: string }> = {
  confirmed: { label: 'Confirmed', color: 'positive' },
  pending: { label: 'Pending', color: 'warning' },
  cancelled: { label: 'Cancelled', color: 'grey-6' },
  refunded: { label: 'Refunded', color: 'grey-7' },
}
function statusLabel(s: string): string {
  return STATUS[s]?.label ?? s
}
function statusColor(s: string): string {
  return STATUS[s]?.color ?? 'grey'
}

onMounted(async () => {
  await loadWaitlist()
  try {
    bookings.value = await api.booking.list()
    try {
      const rb = await api.reviews.reviewable()
      reviewable.value = new Set(rb.map((r) => r.booking_id))
    } catch {
      /* non-fatal — the review CTA just won't show */
    }
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load bookings') })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-bookings { display: flex; flex-direction: column; gap: 12px; }
.jg-bookrow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 18px;
}
.jg-offer {
  border-color: var(--jg-positive, #21ba45);
  box-shadow: 0 0 0 1px var(--jg-positive, #21ba45) inset;
}
</style>
