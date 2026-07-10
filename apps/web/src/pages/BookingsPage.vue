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
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money, timeRange } from '@/lib/format'
import { recallSession, type SessionMemo } from '@/lib/sessionMemo'
import type { Booking } from '@/lib/types'

const $q = useQuasar()
const bookings = ref<Booking[]>([])
const loading = ref(true)

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
