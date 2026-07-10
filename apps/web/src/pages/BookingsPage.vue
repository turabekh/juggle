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
        </div>
        <q-chip
          :color="statusColor(b.status)"
          text-color="white"
          :label="statusLabel(b.status)"
          class="text-weight-600"
        />
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
