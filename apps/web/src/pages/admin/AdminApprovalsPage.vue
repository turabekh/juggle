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
            dense
            no-caps
            flat
            color="primary"
            icon="fact_check"
            label="Review"
            class="q-mr-sm"
            @click="openReview(props.row)"
          />
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

    <!-- Verification review dialog -->
    <q-dialog v-model="showReview">
      <q-card style="min-width: 520px; max-width: 600px; border-radius: 18px">
        <q-card-section class="row items-center">
          <div>
            <div class="text-h6">{{ review?.name }}</div>
            <div class="jg-faint text-caption">ABN: {{ review?.abn || '— not provided —' }}</div>
          </div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>

        <q-card-section>
          <div class="text-weight-600 q-mb-sm">Working with Children checks</div>
          <div v-if="review?.wwcc.length" class="jg-vlist">
            <div v-for="w in review.wwcc" :key="w.id" class="jg-vrow">
              <div>
                <div class="text-weight-500">{{ w.staff_name }}</div>
                <div class="jg-faint text-caption">{{ w.wwcc_number }} · exp {{ w.expiry_date }}</div>
              </div>
              <div class="row items-center q-gutter-xs">
                <q-chip dense square :color="vColor(w.status)" text-color="white" :label="w.status" />
                <q-btn dense flat round icon="check" color="positive" @click="verifyWwcc(w.id, 'verified')" />
                <q-btn dense flat round icon="close" color="negative" @click="verifyWwcc(w.id, 'rejected')" />
              </div>
            </div>
          </div>
          <div v-else class="jg-faint text-caption">None submitted.</div>

          <div class="text-weight-600 q-mt-lg q-mb-sm">Public liability insurance</div>
          <div v-if="review?.insurance.length" class="jg-vlist">
            <div v-for="d in review.insurance" :key="d.id" class="jg-vrow">
              <div>
                <a :href="d.file_ref" target="_blank" class="jg-link ellipsis" style="max-width: 300px; display: inline-block">{{ d.file_ref }}</a>
                <div class="jg-faint text-caption">{{ d.expiry_date ? `exp ${d.expiry_date}` : 'no expiry' }}</div>
              </div>
              <div class="row items-center q-gutter-xs">
                <q-chip dense square :color="vColor(d.status)" text-color="white" :label="d.status" />
                <q-btn dense flat round icon="check" color="positive" @click="verifyInsurance(d.id, 'verified')" />
                <q-btn dense flat round icon="close" color="negative" @click="verifyInsurance(d.id, 'rejected')" />
              </div>
            </div>
          </div>
          <div v-else class="jg-faint text-caption">None submitted.</div>
        </q-card-section>

        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Close" v-close-popup />
          <q-btn
            v-if="review && review.status !== 'approved'"
            unelevated no-caps color="positive" label="Approve provider"
            @click="approveFromReview"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { OrgAdmin, OrgStatus, OrgVerifications, VerificationStatus } from '@/lib/types'

const $q = useQuasar()
const status = ref<OrgStatus>('pending')
const orgs = ref<OrgAdmin[]>([])
const loading = ref(false)
const busy = ref<string | null>(null)

const showReview = ref(false)
const review = ref<OrgVerifications | null>(null)

function vColor(s: string): string {
  return { pending: 'warning', verified: 'positive', rejected: 'negative', expired: 'grey-6' }[s] ?? 'grey'
}

async function openReview(org: OrgAdmin): Promise<void> {
  review.value = null
  showReview.value = true
  try {
    review.value = await api.admin.orgVerifications(org.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function verifyWwcc(id: string, s: VerificationStatus): Promise<void> {
  try {
    await api.admin.verifyWwcc(id, s)
    if (review.value) review.value = await api.admin.orgVerifications(review.value.organisation_id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function verifyInsurance(id: string, s: VerificationStatus): Promise<void> {
  try {
    await api.admin.verifyInsurance(id, s)
    if (review.value) review.value = await api.admin.orgVerifications(review.value.organisation_id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function approveFromReview(): Promise<void> {
  if (!review.value) return
  try {
    await api.admin.approveOrg(review.value.organisation_id)
    $q.notify({ type: 'positive', message: `Approved ${review.value.name}` })
    showReview.value = false
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

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
