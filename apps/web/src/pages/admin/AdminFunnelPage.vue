<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Funnel</h1>
        <p class="jg-muted q-mb-none">Product events over the last {{ days }} days (PRD §13).</p>
      </div>
      <q-select
        v-model="days" :options="[7, 30, 90, 365]" outlined dense
        style="min-width: 120px" label="Window (days)" @update:model-value="load"
      />
    </header>

    <div v-if="loading" class="q-gutter-md q-mt-md">
      <q-skeleton v-for="n in 4" :key="n" type="rect" height="46px" style="border-radius: 12px" />
    </div>

    <div v-else class="jg-card q-pa-lg">
      <div v-for="s in funnel?.stages ?? []" :key="s.event_type" class="jg-fnrow">
        <div class="jg-fnrow__label">{{ label(s.event_type) }}</div>
        <div class="jg-fnrow__bar">
          <div class="jg-fnrow__fill" :style="{ width: barWidth(s.count) }"></div>
        </div>
        <div class="jg-fnrow__count">{{ s.count.toLocaleString() }}</div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { FunnelOut } from '@/lib/types'

const $q = useQuasar()
const days = ref(30)
const loading = ref(false)
const funnel = ref<FunnelOut | null>(null)

const LABELS: Record<string, string> = {
  search_performed: 'Searches',
  listing_viewed: 'Listings viewed',
  checkout_started: 'Checkouts started',
  checkout_completed: 'Checkouts completed',
  booking_cancelled: 'Bookings cancelled',
  session_filled: 'Sessions filled',
  listing_published: 'Listings published',
  provider_signup: 'Provider signups',
}
function label(t: string): string {
  return LABELS[t] ?? t
}

function barWidth(count: number): string {
  const max = Math.max(1, ...(funnel.value?.stages ?? []).map((s) => s.count))
  return `${Math.round((count / max) * 100)}%`
}

async function load(): Promise<void> {
  loading.value = true
  try {
    funnel.value = await api.analytics.funnel(days.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load funnel') })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-fnrow {
  display: grid;
  grid-template-columns: 180px 1fr 64px;
  align-items: center;
  gap: 14px;
  padding: 8px 0;
}
.jg-fnrow__label { font-weight: 600; }
.jg-fnrow__bar {
  height: 22px;
  background: var(--jg-line);
  border-radius: 6px;
  overflow: hidden;
}
.jg-fnrow__fill {
  height: 100%;
  background: var(--jg-primary);
  border-radius: 6px;
  min-width: 2px;
  transition: width 0.3s ease;
}
.jg-fnrow__count { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
@media (max-width: 599px) {
  .jg-fnrow { grid-template-columns: 130px 1fr 48px; gap: 8px; }
}
</style>
