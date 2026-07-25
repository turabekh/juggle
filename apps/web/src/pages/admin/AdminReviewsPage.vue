<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Review moderation</h1>
        <p class="jg-muted q-mb-none">
          Verified-booking reviews wait here before they go public (PRD §7.6).
        </p>
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
      <q-tab name="published" label="Published" />
      <q-tab name="rejected" label="Rejected" />
    </q-tabs>

    <div v-if="loading" class="q-gutter-md q-mt-md">
      <q-skeleton v-for="n in 3" :key="n" type="rect" height="120px" style="border-radius: 16px" />
    </div>

    <div v-else-if="reviews.length" class="jg-list q-mt-md">
      <article v-for="r in reviews" :key="r.id" class="jg-card q-pa-md">
        <div class="row items-center q-gutter-sm">
          <StarRating :model-value="r.rating" size="16px" />
          <span class="text-weight-600">{{ r.author_label }}</span>
          <span class="jg-faint text-caption">· {{ r.program_title }} · {{ dayLabel(r.created_at) }}</span>
          <q-space />
          <q-chip dense square :color="statusColor(r.status)" text-color="white" :label="r.status" />
        </div>
        <p class="q-mt-sm q-mb-none" style="white-space: pre-line">{{ r.body }}</p>
        <div v-if="r.rejection_reason" class="jg-faint text-caption q-mt-xs">
          Rejected: {{ r.rejection_reason }}
        </div>
        <div v-if="r.status === 'pending'" class="row justify-end q-gutter-sm q-mt-sm">
          <q-btn
            flat dense no-caps color="negative" icon="block" label="Reject"
            :loading="busy === r.id" @click="openReject(r)"
          />
          <q-btn
            unelevated dense no-caps color="positive" icon="check" label="Approve"
            :loading="busy === r.id" @click="moderate(r, true)"
          />
        </div>
      </article>
    </div>

    <div v-else class="jg-card q-pa-xl text-center jg-muted q-mt-md">
      No {{ status }} reviews.
    </div>

    <!-- Reject reason dialog -->
    <q-dialog v-model="showReject">
      <q-card style="min-width: min(380px, 92vw); border-radius: 18px">
        <q-card-section><div class="text-h6">Reject review</div></q-card-section>
        <q-card-section>
          <q-input
            v-model="rejectReason" outlined type="textarea" autogrow autofocus
            label="Reason (internal)" hint="Recorded in the audit trail."
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="negative" label="Reject review"
            @click="confirmReject"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import StarRating from '@/components/StarRating.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel } from '@/lib/format'
import type { Review, ReviewStatus } from '@/lib/types'

const $q = useQuasar()
const status = ref<ReviewStatus>('pending')
const reviews = ref<Review[]>([])
const loading = ref(false)
const busy = ref<string | null>(null)

const showReject = ref(false)
const rejectReason = ref('')
const rejectTarget = ref<Review | null>(null)

function statusColor(s: string): string {
  return { pending: 'warning', published: 'positive', rejected: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    reviews.value = await api.reviews.moderationQueue(status.value)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load reviews') })
  } finally {
    loading.value = false
  }
}

async function moderate(r: Review, approve: boolean, reason?: string): Promise<void> {
  busy.value = r.id
  try {
    await api.reviews.moderate(r.id, approve, reason)
    $q.notify({ type: approve ? 'positive' : 'warning', message: approve ? 'Published' : 'Rejected' })
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    busy.value = null
  }
}

function openReject(r: Review): void {
  rejectTarget.value = r
  rejectReason.value = ''
  showReject.value = true
}

async function confirmReject(): Promise<void> {
  if (!rejectTarget.value) return
  showReject.value = false
  await moderate(rejectTarget.value, false, rejectReason.value.trim() || undefined)
}

onMounted(load)
</script>
