<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Feature flags</h1>
        <p class="jg-muted q-mb-none">Toggle features, roll out by percentage, or target specific users/orgs.</p>
      </div>
      <q-btn unelevated no-caps color="primary" icon="add" label="New flag" @click="openCreate" />
    </header>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 3" :key="n" type="rect" height="96px" style="border-radius: 16px" />
    </div>

    <div v-else-if="flags.length" class="jg-flags">
      <div v-for="f in flags" :key="f.key" class="jg-card jg-flag">
        <div class="jg-flag__main">
          <div class="row items-center q-gutter-sm">
            <code>{{ f.key }}</code>
            <q-badge v-if="f.enabled" color="positive">on</q-badge>
            <q-badge v-else color="grey-6">off</q-badge>
          </div>
          <div class="jg-faint text-caption q-mt-xs">
            {{ f.description || 'No description' }} · {{ f.rollout_percentage }}% rollout
            <span v-if="targetCount(f)"> · {{ targetCount(f) }} targeted</span>
          </div>
        </div>
        <div class="jg-flag__actions">
          <q-toggle
            :model-value="f.enabled"
            color="primary"
            @update:model-value="(v) => toggle(f, v)"
          />
          <q-btn dense flat no-caps icon="edit" label="Edit" @click="openEdit(f)" />
        </div>
      </div>
    </div>

    <EmptyState v-else icon="flag" title="No feature flags yet" subtitle="Create one to start gating features.">
      <q-btn unelevated no-caps color="primary" label="New flag" @click="openCreate" />
    </EmptyState>

    <q-dialog v-model="showEditor">
      <q-card style="min-width: 400px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">{{ editing ? 'Edit flag' : 'New flag' }}</div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="form.key" outlined dense label="Key" :readonly="editing" />
          <q-input v-model="form.description" outlined dense label="Description" />
          <q-toggle v-model="form.enabled" label="Enabled" color="primary" />
          <div>
            <div class="text-caption jg-muted">Rollout: {{ form.rollout_percentage }}%</div>
            <q-slider v-model="form.rollout_percentage" :min="0" :max="100" :step="5" color="primary" />
          </div>
          <q-input
            v-model="targetingText"
            outlined
            dense
            type="textarea"
            autogrow
            label='Targeting JSON (optional)'
            hint='e.g. {"user_ids": ["..."], "org_ids": ["..."]}'
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Save" :loading="saving" :disable="!form.key" @click="save" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import type { Flag } from '@/lib/types'

const $q = useQuasar()
const flags = ref<Flag[]>([])
const loading = ref(true)
const saving = ref(false)
const showEditor = ref(false)
const editing = ref(false)
const targetingText = ref('')

const form = reactive({
  key: '',
  description: '',
  enabled: false,
  rollout_percentage: 0,
})

function targetCount(f: Flag): number {
  const t = f.targeting ?? {}
  const users = Array.isArray(t.user_ids) ? t.user_ids.length : 0
  const orgs = Array.isArray(t.org_ids) ? t.org_ids.length : 0
  return users + orgs
}

async function load(): Promise<void> {
  loading.value = true
  try {
    flags.value = await api.flags.list()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = false
  Object.assign(form, { key: '', description: '', enabled: false, rollout_percentage: 0 })
  targetingText.value = ''
  showEditor.value = true
}

function openEdit(f: Flag): void {
  editing.value = true
  Object.assign(form, {
    key: f.key,
    description: f.description ?? '',
    enabled: f.enabled,
    rollout_percentage: f.rollout_percentage,
  })
  targetingText.value = f.targeting ? JSON.stringify(f.targeting, null, 2) : ''
  showEditor.value = true
}

async function toggle(f: Flag, enabled: boolean): Promise<void> {
  try {
    const updated = await api.flags.upsert(f.key, {
      enabled,
      rollout_percentage: f.rollout_percentage,
      targeting: f.targeting,
      description: f.description,
    })
    Object.assign(f, updated)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function save(): Promise<void> {
  let targeting: Record<string, unknown> | null = null
  if (targetingText.value.trim()) {
    try {
      targeting = JSON.parse(targetingText.value)
    } catch {
      $q.notify({ type: 'negative', message: 'Targeting must be valid JSON' })
      return
    }
  }
  saving.value = true
  try {
    await api.flags.upsert(form.key, {
      enabled: form.enabled,
      rollout_percentage: form.rollout_percentage,
      targeting,
      description: form.description || null,
    })
    showEditor.value = false
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-flags { display: flex; flex-direction: column; gap: 12px; }
.jg-flag {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
}
.jg-flag__actions { display: flex; align-items: center; gap: 6px; }
code { background: #eef0f5; padding: 1px 6px; border-radius: 6px; font-size: 12.5px; font-weight: 600; }
</style>
