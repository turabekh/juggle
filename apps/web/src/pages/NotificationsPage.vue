<template>
  <q-page class="jg-page" style="max-width: 720px">
    <h1 class="text-h4 q-mb-lg">Notifications</h1>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 3" :key="n" type="rect" height="72px" style="border-radius: 14px" />
    </div>

    <div v-else-if="notes.length" class="jg-notes">
      <div v-for="n in notes" :key="n.id" class="jg-card jg-note">
        <div class="jg-note__icon" :class="`jg-note__icon--${n.kind}`">
          <q-icon :name="iconFor(n.kind)" size="20px" />
        </div>
        <div class="jg-note__body">
          <div class="text-weight-600">{{ n.subject }}</div>
          <div class="jg-faint text-caption">
            emailed to {{ n.to_email }} · {{ when(n.created_at) }}
          </div>
        </div>
      </div>
    </div>

    <EmptyState
      v-else
      icon="notifications_none"
      title="Nothing here yet"
      subtitle="Booking confirmations and updates will show up here."
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
import type { Notification } from '@/lib/types'

const $q = useQuasar()
const notes = ref<Notification[]>([])
const loading = ref(true)

function iconFor(kind: string): string {
  return { booking_confirmation: 'celebration', session_cancellation: 'event_busy' }[kind] ?? 'mail'
}
function when(iso: string): string {
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

onMounted(async () => {
  try {
    notes.value = await api.notifications.list()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-notes { display: flex; flex-direction: column; gap: 12px; }
.jg-note { display: flex; align-items: center; gap: 14px; padding: 14px 18px; }
.jg-note__icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--jg-primary-tint);
  color: var(--jg-primary);
  flex-shrink: 0;
}
.jg-note__icon--session_cancellation { background: #fdecec; color: #d8532f; }
</style>
