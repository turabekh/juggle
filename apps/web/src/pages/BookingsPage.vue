<template>
  <q-page class="jg-page" style="max-width: 780px">
    <h1 class="text-h4 q-mb-lg">My bookings</h1>

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
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import StarRating from '@/components/StarRating.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money, timeRange } from '@/lib/format'
import { recallSession, type SessionMemo } from '@/lib/sessionMemo'
import type { Booking } from '@/lib/types'

const $q = useQuasar()
const bookings = ref<Booking[]>([])
const loading = ref(true)

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
</style>
