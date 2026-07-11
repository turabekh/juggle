<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Operations</h1>
        <p class="jg-muted q-mb-none">
          Background maintenance — normally a worker runs this every few minutes
          (<code>make worker-loop</code>). Run one tick on demand here.
        </p>
      </div>
      <q-btn
        unelevated no-caps color="primary" icon="play_arrow" label="Run maintenance now"
        :loading="running" @click="run"
      />
    </header>

    <div v-if="last" class="jg-ops">
      <div class="jg-card jg-ops__tile">
        <div class="jg-ops__num">{{ last.reminders_sent }}</div>
        <div class="jg-ops__label">Reminders sent</div>
        <div class="jg-faint text-caption">T-48h / T-3h pre-session emails</div>
      </div>
      <div class="jg-card jg-ops__tile">
        <div class="jg-ops__num">{{ last.waitlist_offers_made }}</div>
        <div class="jg-ops__label">Waitlist offers made</div>
        <div class="jg-faint text-caption">
          {{ last.waitlist_offers_expired }} expired ·
          {{ last.waitlist_sessions_processed }} queues checked
        </div>
      </div>
      <div class="jg-card jg-ops__tile">
        <div class="jg-ops__num">{{ last.holds_reclaimed }}</div>
        <div class="jg-ops__label">Seat holds reclaimed</div>
        <div class="jg-faint text-caption">expired holds returned to inventory</div>
      </div>
    </div>

    <div v-else class="jg-card q-pa-xl text-center jg-muted">
      Run a tick to see what maintenance did.
    </div>

    <p class="jg-faint text-caption q-mt-lg">
      Payout release is a separate manual action on the Payouts page.
    </p>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { JobSummary } from '@/lib/types'

const $q = useQuasar()
const running = ref(false)
const last = ref<JobSummary | null>(null)

async function run(): Promise<void> {
  running.value = true
  try {
    last.value = await api.scheduler.run()
    $q.notify({ type: 'positive', message: 'Maintenance tick complete.' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not run maintenance') })
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.jg-ops {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 720px) {
  .jg-ops { grid-template-columns: 1fr; }
}
.jg-ops__tile { padding: 18px 20px; }
.jg-ops__num { font-size: 30px; font-weight: 700; line-height: 1.1; }
.jg-ops__label { font-weight: 600; margin-top: 2px; }
</style>
