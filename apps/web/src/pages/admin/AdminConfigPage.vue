<template>
  <q-page class="jg-adminpage">
    <header class="jg-adminpage__head">
      <div>
        <h1 class="jg-adminpage__title">Runtime configuration</h1>
        <p class="jg-muted q-mb-none">
          Operational levers — changes take effect immediately, no deploy. Versioned & audited.
        </p>
      </div>
    </header>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 4" :key="n" type="rect" height="76px" style="border-radius: 16px" />
    </div>

    <div v-else class="jg-settings">
      <div v-for="s in settings" :key="s.key" class="jg-card jg-setting">
        <div class="jg-setting__info">
          <div class="text-weight-600">{{ s.description }}</div>
          <div class="jg-faint text-caption">
            <code>{{ s.key }}</code> · allowed {{ s.minimum }}–{{ s.maximum }} · default {{ s.default }}
          </div>
        </div>
        <div class="jg-setting__edit">
          <q-input
            v-model.number="drafts[s.key]"
            dense
            outlined
            type="number"
            :min="s.minimum"
            :max="s.maximum"
            style="width: 120px"
          />
          <q-btn
            dense
            no-caps
            unelevated
            color="primary"
            label="Save"
            :disable="drafts[s.key] === s.value"
            :loading="busy === s.key"
            @click="save(s)"
          />
          <q-btn dense flat round icon="history" aria-label="History" @click="openHistory(s.key)" />
        </div>
      </div>
    </div>

    <q-dialog v-model="showHistory">
      <q-card style="min-width: 380px; border-radius: 18px">
        <q-card-section class="row items-center">
          <div class="text-h6">History · <code>{{ historyKey }}</code></div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-list separator>
          <q-item v-for="v in history" :key="v.version">
            <q-item-section>
              <q-item-label>
                v{{ v.version }}
                <q-badge v-if="v.is_current" color="positive" class="q-ml-sm">current</q-badge>
              </q-item-label>
              <q-item-label caption>
                {{ new Date(v.created_at).toLocaleString() }}
                <span v-if="v.note"> · {{ v.note }}</span>
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import type { SettingItem, SettingVersion } from '@/lib/types'

const $q = useQuasar()
const settings = ref<SettingItem[]>([])
const drafts = reactive<Record<string, number>>({})
const loading = ref(true)
const busy = ref<string | null>(null)

const showHistory = ref(false)
const historyKey = ref('')
const history = ref<SettingVersion[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    settings.value = await api.config.list()
    for (const s of settings.value) drafts[s.key] = s.value
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load settings') })
  } finally {
    loading.value = false
  }
}

async function save(s: SettingItem): Promise<void> {
  busy.value = s.key
  try {
    const updated = await api.config.update(s.key, drafts[s.key])
    s.value = updated.value
    $q.notify({ type: 'positive', message: `Updated ${s.key}` })
  } catch (err) {
    drafts[s.key] = s.value
    $q.notify({ type: 'negative', message: apiError(err, 'Value rejected') })
  } finally {
    busy.value = null
  }
}

async function openHistory(key: string): Promise<void> {
  historyKey.value = key
  history.value = []
  showHistory.value = true
  try {
    history.value = await api.config.history(key)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

onMounted(load)
</script>

<style scoped>
.jg-settings { display: flex; flex-direction: column; gap: 12px; }
.jg-setting {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
}
.jg-setting__edit { display: flex; align-items: center; gap: 8px; }
code { background: #eef0f5; padding: 1px 6px; border-radius: 6px; font-size: 12px; }
</style>
