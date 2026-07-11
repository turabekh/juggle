<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Users</h1>
        <p class="jg-muted q-mb-none">
          Lookup, booking history, data-deletion, and duplicate-account merge (PRD §10.2).
        </p>
      </div>
    </header>

    <q-input
      v-model="query" outlined dense clearable label="Search by email or name"
      debounce="300" class="jg-adminpage__tabs" style="max-width: 420px"
      @update:model-value="search"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div class="row q-col-gutter-md q-mt-sm">
      <!-- Results -->
      <div class="col-12 col-md-5">
        <q-list bordered class="jg-card">
          <q-item
            v-for="u in results" :key="u.id" clickable
            :active="selected?.id === u.id" active-class="jg-adminnav__active"
            @click="select(u)"
          >
            <q-item-section>
              <q-item-label>{{ u.full_name || '—' }}</q-item-label>
              <q-item-label caption>{{ u.email }}</q-item-label>
            </q-item-section>
            <q-item-section side v-if="u.is_admin">
              <q-badge color="primary" label="admin" />
            </q-item-section>
          </q-item>
          <q-item v-if="query && !results.length && !searching">
            <q-item-section class="jg-muted">No users found.</q-item-section>
          </q-item>
        </q-list>
      </div>

      <!-- Selected user -->
      <div class="col-12 col-md-7">
        <div v-if="selected" class="jg-card q-pa-lg">
          <div class="text-h6">{{ selected.full_name || selected.email }}</div>
          <div class="jg-faint text-caption">{{ selected.email }}</div>
          <div class="q-mt-md">
            <q-icon name="confirmation_number" size="16px" />
            {{ bookings.length }} booking{{ bookings.length === 1 ? '' : 's' }}
          </div>

          <template v-if="!selected.is_admin">
            <q-separator class="q-my-md" />
            <div class="text-weight-600 q-mb-sm">Duplicate-account merge</div>
            <p class="jg-muted text-caption">
              Merge another (duplicate) account <b>into</b> this one — its kids, bookings and
              waitlist move here and the duplicate is deactivated.
            </p>
            <q-btn
              flat no-caps color="primary" icon="merge" label="Merge a duplicate into this account"
              @click="openMerge"
            />

            <q-separator class="q-my-md" />
            <q-btn
              flat no-caps color="negative" icon="delete_forever" label="Delete account (APP)"
              @click="confirmDelete"
            />
          </template>
          <div v-else class="jg-faint text-caption q-mt-md">
            Admin account — protected from deletion and merge.
          </div>
        </div>
        <div v-else class="jg-card q-pa-xl text-center jg-muted">
          Search and select a user to manage.
        </div>
      </div>
    </div>

    <!-- Merge dialog: pick the duplicate (source) to fold into the selected user -->
    <q-dialog v-model="showMerge">
      <q-card style="min-width: 460px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Merge a duplicate</div>
          <div class="jg-faint text-caption">
            The account you pick will be merged into
            <b>{{ selected?.email }}</b> and deactivated.
          </div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="mergeQuery" outlined dense clearable label="Find the duplicate account"
            debounce="300" @update:model-value="searchMerge"
          />
          <q-list separator class="q-mt-sm">
            <q-item
              v-for="u in mergeResults.filter((r) => r.id !== selected?.id && !r.is_admin)"
              :key="u.id" clickable :active="mergeSource?.id === u.id"
              active-class="jg-adminnav__active" @click="mergeSource = u"
            >
              <q-item-section>
                <q-item-label>{{ u.full_name || '—' }}</q-item-label>
                <q-item-label caption>{{ u.email }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" icon="merge" label="Merge"
            :loading="merging" :disable="!mergeSource" @click="doMerge"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { Booking, UserSummary } from '@/lib/types'

const $q = useQuasar()
const query = ref('')
const results = ref<UserSummary[]>([])
const searching = ref(false)
const selected = ref<UserSummary | null>(null)
const bookings = ref<Booking[]>([])

const showMerge = ref(false)
const mergeQuery = ref('')
const mergeResults = ref<UserSummary[]>([])
const mergeSource = ref<UserSummary | null>(null)
const merging = ref(false)

async function search(): Promise<void> {
  if (!query.value) {
    results.value = []
    return
  }
  searching.value = true
  try {
    results.value = await api.admin.users(query.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    searching.value = false
  }
}

async function select(u: UserSummary): Promise<void> {
  selected.value = u
  bookings.value = []
  try {
    bookings.value = await api.admin.userBookings(u.id)
  } catch {
    /* non-fatal */
  }
}

function openMerge(): void {
  mergeQuery.value = ''
  mergeResults.value = []
  mergeSource.value = null
  showMerge.value = true
}

async function searchMerge(): Promise<void> {
  mergeResults.value = mergeQuery.value ? await api.admin.users(mergeQuery.value) : []
}

async function doMerge(): Promise<void> {
  if (!selected.value || !mergeSource.value) return
  merging.value = true
  try {
    await api.admin.mergeUsers(mergeSource.value.id, selected.value.id)
    showMerge.value = false
    $q.notify({ type: 'positive', message: 'Accounts merged.' })
    await select(selected.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not merge accounts') })
  } finally {
    merging.value = false
  }
}

function confirmDelete(): void {
  if (!selected.value) return
  const user = selected.value
  $q.dialog({
    title: 'Delete this account?',
    message: `Permanently removes ${user.email} and their kids' details (APP data-deletion).`,
    cancel: true,
    ok: { label: 'Delete', color: 'negative', unelevated: true, noCaps: true },
  }).onOk(async () => {
    try {
      await api.admin.deleteUser(user.id)
      $q.notify({ type: 'info', message: 'Account deleted.' })
      selected.value = null
      await search()
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err) })
    }
  })
}
</script>
