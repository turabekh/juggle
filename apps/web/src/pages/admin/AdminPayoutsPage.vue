<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Payouts</h1>
        <p class="jg-muted q-mb-none">Provider earnings become due a few days after each session.</p>
      </div>
      <q-btn
        unelevated no-caps color="primary" icon="payments" label="Run due payouts"
        :loading="running" @click="run"
      />
    </header>

    <q-tabs
      v-model="status"
      class="jg-adminpage__tabs"
      active-color="primary"
      indicator-color="primary"
      align="left"
      no-caps
      @update:model-value="load"
    >
      <q-tab name="scheduled" label="Scheduled" />
      <q-tab name="held" label="Held" />
      <q-tab name="paid" label="Paid" />
    </q-tabs>

    <q-table
      flat
      :rows="payouts"
      :columns="columns"
      row-key="id"
      :loading="loading"
      :rows-per-page-options="[0]"
      hide-pagination
      class="jg-card"
    >
      <template #body-cell-amount="props">
        <q-td :props="props" class="text-weight-600">{{ money(props.value) }}</q-td>
      </template>
      <template #body-cell-scheduled="props">
        <q-td :props="props" class="jg-faint">
          {{ props.value ? new Date(props.value).toLocaleDateString() : '—' }}
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip dense square :color="color(props.value)" text-color="white" :label="props.value" />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="props.row.status === 'scheduled'"
            dense no-caps flat color="warning" label="Hold" @click="hold(props.row.id)"
          />
          <q-btn
            v-if="props.row.status === 'held'"
            dense no-caps flat color="primary" label="Release" @click="release(props.row.id)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center q-pa-lg jg-muted">No {{ status }} payouts.</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import { money } from '@/lib/format'
import type { Payout, PayoutStatus } from '@/lib/types'

const $q = useQuasar()
const status = ref<PayoutStatus>('scheduled')
const payouts = ref<Payout[]>([])
const loading = ref(false)
const running = ref(false)

const columns: QTableColumn<Payout>[] = [
  { name: 'org', label: 'Organisation', field: 'organisation_id', align: 'left', format: (v) => String(v).slice(0, 8) },
  { name: 'amount', label: 'Amount', field: 'amount_cents', align: 'left' },
  { name: 'scheduled', label: 'Due', field: 'scheduled_for', align: 'left' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

function color(s: string): string {
  return { scheduled: 'primary', paid: 'positive', held: 'warning', reversed: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    payouts.value = await api.admin.payouts(status.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
}

async function run(): Promise<void> {
  running.value = true
  try {
    const res = await api.admin.runPayouts()
    $q.notify({
      type: 'positive',
      message: `Released ${res.released} payout(s) — ${money(res.total_cents)}`,
    })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    running.value = false
  }
}

async function hold(id: string): Promise<void> {
  await api.admin.holdPayout(id).catch((err) => $q.notify({ type: 'negative', message: apiError(err) }))
  await load()
}
async function release(id: string): Promise<void> {
  await api.admin.releasePayout(id).catch((err) => $q.notify({ type: 'negative', message: apiError(err) }))
  await load()
}

onMounted(load)
</script>
