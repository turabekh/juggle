<template>
  <q-page class="jg-page" style="max-width: 720px">
    <div class="row items-center justify-between q-mb-lg">
      <h1 class="text-h4 q-my-none">Party plans</h1>
      <q-btn
        unelevated color="primary" no-caps icon="add" label="New plan"
        :loading="creating" @click="createPlan"
      />
    </div>
    <p class="jg-muted q-mb-lg">
      Can't decide? Set up a vote — pick a few party options, share a link, and let the guests
      choose. The winning option books in one tap.
    </p>

    <div v-if="loading" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" /><span>Loading…</span>
    </div>

    <div v-else-if="plans.length" class="jg-list">
      <router-link
        v-for="p in plans" :key="p.id"
        :to="{ name: 'party-plan-manage', params: { id: p.id } }"
        class="jg-card q-pa-md jg-plan-row"
      >
        <div>
          <div class="text-weight-600">{{ planTitle(p) }}</div>
          <div class="jg-faint text-caption">
            {{ p.options.filter((o) => !o.voided).length }} options ·
            {{ p.invites.length }} invited
            <template v-if="p.deadline_at"> · votes close {{ dayLabel(p.deadline_at) }}</template>
          </div>
        </div>
        <q-chip dense square :color="statusColor(p.status)" text-color="white" :label="statusLabel(p.status)" />
      </router-link>
    </div>

    <EmptyState
      v-else
      icon="how_to_vote"
      title="No party plans yet"
      subtitle="Start a vote to let your guests pick the party."
    >
      <q-btn unelevated color="primary" no-caps label="New plan" :loading="creating" @click="createPlan" />
    </EmptyState>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel } from '@/lib/format'
import type { PlanView } from '@/lib/types'

const $q = useQuasar()
const router = useRouter()
const plans = ref<PlanView[]>([])
const loading = ref(true)
const creating = ref(false)

function planTitle(p: PlanView): string {
  const first = p.options.find((o) => o.kind === 'package' && o.package_name)
  return first?.package_name ? `${first.package_name} + more` : 'Untitled party vote'
}

const STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: 'Draft', color: 'grey-6' },
  open: { label: 'Voting open', color: 'primary' },
  resolved: { label: 'Ready to book', color: 'deep-orange' },
  booked: { label: 'Booked', color: 'positive' },
  expired_unbooked: { label: 'Closed', color: 'grey-5' },
}
const statusLabel = (s: string): string => STATUS[s]?.label ?? s
const statusColor = (s: string): string => STATUS[s]?.color ?? 'grey'

async function createPlan(): Promise<void> {
  creating.value = true
  try {
    const plan = await api.partyPlanner.createPlan()
    void router.push({ name: 'party-plan-manage', params: { id: plan.id } })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  try {
    plans.value = await api.partyPlanner.listPlans()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-plan-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-decoration: none;
  color: var(--jg-ink);
}
</style>
