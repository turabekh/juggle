<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Impersonation</h1>
        <p class="jg-muted q-mb-none">
          See exactly what a user sees, or act on their behalf. Time-boxed and fully audited.
        </p>
      </div>
    </header>

    <div class="jg-card q-pa-lg jg-imp-start">
      <div class="text-weight-600 q-mb-md">Start a support session</div>
      <div class="jg-imp-form">
        <q-select
          v-model="form.targetUserId"
          outlined
          dense
          use-input
          input-debounce="300"
          :options="userOptions"
          option-value="id"
          option-label="email"
          emit-value
          map-options
          clearable
          label="Find user by email"
          hint="Type at least 2 characters"
          class="col"
          @filter="searchUsers"
        >
          <template #option="scope">
            <q-item v-bind="scope.itemProps">
              <q-item-section>
                <q-item-label>{{ scope.opt.email }}</q-item-label>
                <q-item-label caption>{{ scope.opt.full_name || '—' }}</q-item-label>
              </q-item-section>
            </q-item>
          </template>
          <template #no-option>
            <q-item><q-item-section class="jg-muted">No matches</q-item-section></q-item>
          </template>
        </q-select>
        <q-select
          v-model="form.mode"
          outlined
          dense
          :options="modeOptions"
          emit-value
          map-options
          label="Mode"
          style="width: 200px"
        />
      </div>
      <q-input v-model="form.reason" outlined dense label="Reason (recommended)" class="q-mt-md" />
      <div class="row items-center q-mt-md q-gutter-sm">
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="support_agent"
          label="Start session"
          :loading="starting"
          :disable="!form.targetUserId"
          @click="start"
        />
        <div v-if="pendingToken" class="jg-imp-created">
          <q-icon name="check_circle" color="positive" />
          Session ready ({{ pendingToken.mode === 'view_as' ? 'view only' : 'can act' }})
          <q-btn dense no-caps unelevated color="dark" label="Enter session" icon="login" @click="enter" />
        </div>
      </div>
      <div class="jg-faint text-caption q-mt-sm">
        view-as is read-only; act-as can perform actions as the user. Both are blocked from
        sensitive actions and are recorded in the audit log.
      </div>
    </div>

    <div class="text-weight-600 q-mt-xl q-mb-sm">Active sessions</div>
    <q-table
      flat
      :rows="sessions"
      :columns="columns"
      row-key="id"
      :loading="loading"
      :rows-per-page-options="[0]"
      hide-pagination
      class="jg-card"
    >
      <template #body-cell-mode="props">
        <q-td :props="props">
          <q-chip dense square :color="props.value === 'act_as' ? 'secondary' : 'grey-6'" text-color="white" :label="props.value" />
        </q-td>
      </template>
      <template #body-cell-expires="props">
        <q-td :props="props" class="jg-faint">{{ new Date(props.value).toLocaleTimeString() }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" class="text-right">
          <q-btn dense no-caps flat color="negative" label="End" @click="end(props.row.id)" />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center q-pa-lg jg-muted">No active sessions.</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import { api, apiError } from '@/lib/api'
import type { ImpersonationSession, ImpersonationToken, UserSummary } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'

const $q = useQuasar()
const router = useRouter()
const auth = useAuthStore()

const sessions = ref<ImpersonationSession[]>([])
const loading = ref(false)
const starting = ref(false)
const pendingToken = ref<ImpersonationToken | null>(null)

const form = reactive({ targetUserId: '', mode: 'view_as' as 'view_as' | 'act_as', reason: '' })
const userOptions = ref<UserSummary[]>([])

async function searchUsers(
  val: string,
  update: (fn: () => void) => void,
  abort: () => void,
): Promise<void> {
  if (val.length < 2) {
    update(() => {
      userOptions.value = []
    })
    return
  }
  try {
    const users = await api.admin.users(val)
    update(() => {
      userOptions.value = users
    })
  } catch {
    abort()
  }
}
const modeOptions = [
  { label: 'View as (read-only)', value: 'view_as' },
  { label: 'Act as (full)', value: 'act_as' },
]

const columns: QTableColumn<ImpersonationSession>[] = [
  { name: 'target', label: 'Target user', field: 'target_id', align: 'left' },
  { name: 'mode', label: 'Mode', field: 'mode', align: 'left' },
  { name: 'reason', label: 'Reason', field: (r) => r.reason ?? '—', align: 'left' },
  { name: 'expires', label: 'Expires', field: 'expires_at', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

async function load(): Promise<void> {
  loading.value = true
  try {
    sessions.value = await api.admin.impersonations()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
}

async function start(): Promise<void> {
  starting.value = true
  try {
    pendingToken.value = await api.admin.startImpersonation(
      form.targetUserId,
      form.mode,
      form.reason || undefined,
    )
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not start session') })
  } finally {
    starting.value = false
  }
}

async function enter(): Promise<void> {
  if (!pendingToken.value) return
  await auth.enterImpersonation(pendingToken.value.token)
  pendingToken.value = null
  router.push({ name: 'discover' })
}

async function end(id: string): Promise<void> {
  try {
    await api.admin.endImpersonation(id)
    $q.notify({ type: 'positive', message: 'Session ended' })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

onMounted(load)
</script>

<style scoped>
.jg-imp-form { display: flex; gap: 12px; align-items: flex-start; }

@media (max-width: 599px) {
  /* The user search plus a fixed 200px Mode select overflowed the viewport. */
  .jg-imp-form { flex-direction: column; }
  .jg-imp-form > :deep(.q-field) { width: 100% !important; }
}
.jg-imp-created {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--jg-ink-soft);
}
</style>
