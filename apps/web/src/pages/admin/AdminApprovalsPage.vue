<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Provider approvals</h1>
        <p class="jg-muted q-mb-none">Approve providers before they can publish, or suspend them.</p>
      </div>
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
      <q-tab name="pending" label="Pending" />
      <q-tab name="approved" label="Approved" />
      <q-tab name="suspended" label="Suspended" />
    </q-tabs>

    <q-table
      flat
      :rows="orgs"
      :columns="columns"
      row-key="id"
      :loading="loading"
      :rows-per-page-options="[0]"
      hide-pagination
      class="jg-adminpage__table jg-card"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip dense square :color="statusColor(props.value)" text-color="white" :label="props.value" />
        </q-td>
      </template>
      <template #body-cell-reliability="props">
        <q-td :props="props">{{ (props.value * 100).toFixed(0) }}%</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="props.row.status !== 'approved'"
            dense
            no-caps
            unelevated
            color="positive"
            label="Approve"
            :loading="busy === props.row.id"
            @click="approve(props.row)"
          />
          <q-btn
            v-if="props.row.status !== 'suspended'"
            dense
            no-caps
            flat
            color="negative"
            label="Suspend"
            class="q-ml-sm"
            :loading="busy === props.row.id"
            @click="suspend(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center q-pa-lg jg-muted">No {{ status }} providers.</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { OrgAdmin, OrgStatus } from '@/lib/types'

const $q = useQuasar()
const status = ref<OrgStatus>('pending')
const orgs = ref<OrgAdmin[]>([])
const loading = ref(false)
const busy = ref<string | null>(null)

const columns: QTableColumn<OrgAdmin>[] = [
  { name: 'name', label: 'Provider', field: 'name', align: 'left' },
  { name: 'slug', label: 'Slug', field: 'slug', align: 'left' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'reliability', label: 'Reliability', field: 'reliability_score', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

function statusColor(s: string): string {
  return { pending: 'warning', approved: 'positive', suspended: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    orgs.value = await api.admin.orgs(status.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load providers') })
  } finally {
    loading.value = false
  }
}

async function approve(org: OrgAdmin): Promise<void> {
  busy.value = org.id
  try {
    await api.admin.approveOrg(org.id)
    $q.notify({ type: 'positive', message: `Approved ${org.name}` })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    busy.value = null
  }
}

async function suspend(org: OrgAdmin): Promise<void> {
  busy.value = org.id
  try {
    await api.admin.suspendOrg(org.id)
    $q.notify({ type: 'warning', message: `Suspended ${org.name}` })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    busy.value = null
  }
}

onMounted(load)
</script>
