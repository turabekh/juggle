<template>
  <q-page class="jg-page" style="max-width: 860px">
    <header class="row items-center justify-between q-mb-lg">
      <div>
        <div class="jg-eyebrow">Provider console</div>
        <h1 class="text-h4 q-my-none">Your organisations</h1>
      </div>
      <q-btn unelevated no-caps color="primary" icon="add" label="New organisation" @click="showCreate = true" />
    </header>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 2" :key="n" type="rect" height="84px" style="border-radius: 16px" />
    </div>

    <div v-else-if="orgs.length" class="jg-orgs">
      <router-link
        v-for="org in orgs"
        :key="org.id"
        :to="{ name: 'provider-org', params: { id: org.id } }"
        class="jg-card jg-card--hover jg-orgrow"
      >
        <div>
          <div class="text-weight-600">{{ org.name }}</div>
          <div class="jg-faint text-caption">{{ org.slug }}</div>
        </div>
        <div class="row items-center q-gutter-sm">
          <q-chip dense square :color="statusColor(org.status)" text-color="white" :label="org.status" />
          <q-icon name="chevron_right" color="grey-6" />
        </div>
      </router-link>
    </div>

    <EmptyState
      v-else
      icon="storefront"
      title="Run holiday programs?"
      subtitle="Create your organisation to list sessions and manage bookings."
    >
      <q-btn unelevated no-caps color="primary" label="Create organisation" @click="showCreate = true" />
    </EmptyState>

    <q-dialog v-model="showCreate">
      <q-card style="min-width: 360px; border-radius: 18px">
        <q-card-section><div class="text-h6">New organisation</div></q-card-section>
        <q-card-section>
          <q-input v-model="newName" outlined dense label="Organisation name" autofocus @keyup.enter="create" />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Create" :loading="creating" :disable="!newName" @click="create" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import type { Org } from '@/lib/types'

const emit = defineEmits<{ 'orgs-changed': [] }>()

const $q = useQuasar()
const router = useRouter()
const orgs = ref<Org[]>([])
const loading = ref(true)
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)

function statusColor(s: string): string {
  return { pending: 'warning', approved: 'positive', suspended: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    orgs.value = await api.org.mine()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
}

async function create(): Promise<void> {
  creating.value = true
  try {
    const org = await api.org.create(newName.value)
    showCreate.value = false
    newName.value = ''
    emit('orgs-changed') // refresh the sidebar org list in ProviderLayout
    router.push({ name: 'provider-org', params: { id: org.id } })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-orgs { display: flex; flex-direction: column; gap: 12px; }
.jg-orgrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  text-decoration: none;
  color: inherit;
}
</style>
