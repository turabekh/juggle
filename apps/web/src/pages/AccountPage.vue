<template>
  <q-page class="jg-page" style="max-width: 640px">
    <h1 class="text-h4 q-mb-xs">My kids</h1>
    <p class="jg-muted q-mb-lg">
      We keep this minimal — first name and date of birth only. No surnames, no photos.
    </p>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 2" :key="n" type="rect" height="64px" style="border-radius: 14px" />
    </div>

    <div v-else class="jg-kids">
      <div v-for="child in children" :key="child.id" class="jg-card jg-kidrow">
        <q-avatar color="primary" text-color="white" size="42px">
          {{ child.first_name.slice(0, 1).toUpperCase() }}
        </q-avatar>
        <div>
          <div class="text-weight-600">{{ child.first_name }}</div>
          <div class="jg-faint text-caption">
            {{ ageAt(child.date_of_birth, nowIso) }} years old
          </div>
        </div>
      </div>

      <button class="jg-card jg-addkid" @click="showAddChild = true">
        <q-icon name="add" size="22px" color="primary" />
        <span>Add a child</span>
      </button>
    </div>

    <q-dialog v-model="showAddChild">
      <q-card style="min-width: 340px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Add a child</div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="newChild.first_name" outlined dense label="First name" autofocus />
          <q-input v-model="newChild.date_of_birth" outlined dense type="date" label="Date of birth" stack-label />
          <q-input
            v-model="newChild.medical_notes"
            outlined
            dense
            type="textarea"
            autogrow
            label="Allergies / medical notes (optional)"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            no-caps
            label="Add child"
            :loading="saving"
            :disable="!newChild.first_name || !newChild.date_of_birth"
            @click="saveChild"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import { api, apiError } from '@/lib/api'
import { ageAt } from '@/lib/format'
import type { Child } from '@/lib/types'

const $q = useQuasar()
const children = ref<Child[]>([])
const loading = ref(true)
const showAddChild = ref(false)
const saving = ref(false)
const nowIso = new Date().toISOString()
const newChild = reactive({ first_name: '', date_of_birth: '', medical_notes: '' })

async function load(): Promise<void> {
  loading.value = true
  try {
    children.value = await api.children.list()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load your kids') })
  } finally {
    loading.value = false
  }
}

async function saveChild(): Promise<void> {
  saving.value = true
  try {
    const created = await api.children.create({
      first_name: newChild.first_name,
      date_of_birth: newChild.date_of_birth,
      medical_notes: newChild.medical_notes || null,
    })
    children.value.push(created)
    showAddChild.value = false
    newChild.first_name = ''
    newChild.date_of_birth = ''
    newChild.medical_notes = ''
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not add child') })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-kids { display: flex; flex-direction: column; gap: 12px; }
.jg-kidrow { display: flex; align-items: center; gap: 14px; padding: 14px 18px; }
.jg-addkid {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  border-style: dashed;
  color: var(--jg-primary);
  font-weight: 600;
  cursor: pointer;
  background: transparent;
}
</style>
