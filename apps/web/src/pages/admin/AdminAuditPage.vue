<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Audit log</h1>
        <p class="jg-muted q-mb-none">Every consequential action, newest first. Impersonated actions record the true actor.</p>
      </div>
    </header>

    <div class="jg-audit-filters">
      <q-input v-model="filters.action" outlined dense clearable label="Action" style="width: 220px" @keyup.enter="load" @clear="load" />
      <q-input v-model="filters.entity_type" outlined dense clearable label="Entity type" style="width: 200px" @keyup.enter="load" @clear="load" />
      <q-btn unelevated no-caps color="primary" icon="filter_alt" label="Apply" @click="load" />
    </div>

    <q-table
      flat
      :rows="events"
      :columns="columns"
      row-key="id"
      :loading="loading"
      :rows-per-page-options="[0]"
      hide-pagination
      class="jg-card"
    >
      <template #body-cell-created="props">
        <q-td :props="props" class="jg-faint">{{ new Date(props.value).toLocaleString() }}</q-td>
      </template>
      <template #body-cell-action="props">
        <q-td :props="props"><code>{{ props.value }}</code></q-td>
      </template>
      <template #body-cell-actor="props">
        <q-td :props="props">
          <span v-if="props.row.impersonated_id" class="jg-pill jg-pill--warm">impersonation</span>
          <span class="jg-faint">{{ shortId(props.row.actor_id) }}</span>
        </q-td>
      </template>
      <template #body-cell-detail="props">
        <q-td :props="props" class="jg-faint">{{ summarise(props.row.detail) }}</q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center q-pa-lg jg-muted">No audit events.</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { AuditEvent } from '@/lib/types'

const $q = useQuasar()
const events = ref<AuditEvent[]>([])
const loading = ref(false)
const filters = reactive({ action: '', entity_type: '' })

const columns: QTableColumn<AuditEvent>[] = [
  { name: 'created', label: 'When', field: 'created_at', align: 'left' },
  { name: 'action', label: 'Action', field: 'action', align: 'left' },
  { name: 'actor', label: 'Actor', field: 'actor_id', align: 'left' },
  { name: 'entity', label: 'Entity', field: (r) => `${r.entity_type ?? ''} ${r.entity_id ?? ''}`, align: 'left' },
  { name: 'detail', label: 'Detail', field: 'detail', align: 'left' },
]

function shortId(id: string | null): string {
  return id ? id.slice(0, 8) : '—'
}
function summarise(detail: Record<string, unknown>): string {
  const entries = Object.entries(detail)
  if (!entries.length) return '—'
  return entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    events.value = await api.audit.list({
      action: filters.action || undefined,
      entity_type: filters.entity_type || undefined,
      limit: 200,
    })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-audit-filters { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
code { background: #eef0f5; padding: 1px 6px; border-radius: 6px; font-size: 12px; }
</style>
