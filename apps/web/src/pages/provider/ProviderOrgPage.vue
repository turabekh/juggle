<template>
  <q-page class="jg-page" style="max-width: 860px">
    <q-btn flat dense no-caps icon="arrow_back" label="All organisations" :to="{ name: 'provider' }" class="jg-muted q-mb-md" />

    <template v-if="org">
      <header class="row items-center q-gutter-sm q-mb-xs">
        <h1 class="text-h4 q-my-none">{{ org.name }}</h1>
        <q-chip dense square :color="statusColor(org.status)" text-color="white" :label="org.status" />
      </header>
      <p v-if="org.status === 'pending'" class="jg-muted">
        Awaiting admin approval. You can set up venues and programs now.
      </p>
      <p v-else-if="org.status === 'suspended'" class="text-negative">
        This organisation is suspended and cannot publish listings.
      </p>

      <!-- Venues -->
      <section class="q-mt-lg">
        <div class="row items-center justify-between q-mb-sm">
          <h2 class="text-h6 q-my-none">Venues</h2>
          <q-btn flat dense no-caps color="primary" icon="add" label="Add venue" @click="showVenue = true" />
        </div>
        <div v-if="venues.length" class="jg-list">
          <div v-for="v in venues" :key="v.id" class="jg-card jg-listrow">
            <div>
              <div class="text-weight-600">{{ v.name }}</div>
              <div class="jg-faint text-caption">
                {{ [v.suburb, v.postcode].filter(Boolean).join(' ') || 'No address' }}
              </div>
            </div>
            <q-icon name="place" color="grey-6" />
          </div>
        </div>
        <div v-else class="jg-muted text-caption">No venues yet — add one to schedule sessions.</div>
      </section>

      <!-- Programs -->
      <section class="q-mt-xl">
        <div class="row items-center justify-between q-mb-sm">
          <h2 class="text-h6 q-my-none">Programs</h2>
          <q-btn flat dense no-caps color="primary" icon="add" label="New program" @click="showProgram = true" />
        </div>
        <div v-if="programs.length" class="jg-list">
          <router-link
            v-for="p in programs"
            :key="p.id"
            :to="{ name: 'provider-program', params: { id: p.id } }"
            class="jg-card jg-card--hover jg-listrow"
          >
            <div>
              <div class="text-weight-600">{{ p.title }}</div>
              <div class="jg-faint text-caption">{{ categoryMeta(p.category).label }}</div>
            </div>
            <div class="row items-center q-gutter-sm">
              <q-chip dense square :color="p.status === 'published' ? 'positive' : 'grey-5'" text-color="white" :label="p.status" />
              <q-icon name="chevron_right" color="grey-6" />
            </div>
          </router-link>
        </div>
        <EmptyState v-else icon="event_note" title="No programs yet" subtitle="Create a program, then add sessions to it." />
      </section>
    </template>

    <!-- Add venue dialog -->
    <q-dialog v-model="showVenue">
      <q-card style="min-width: 380px; border-radius: 18px">
        <q-card-section><div class="text-h6">Add venue</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="venueForm.name" outlined dense label="Venue name" autofocus />
          <div class="row q-col-gutter-md">
            <q-input v-model="venueForm.suburb" outlined dense label="Suburb" class="col" />
            <q-input v-model="venueForm.postcode" outlined dense label="Postcode" class="col" />
          </div>
          <div class="row q-col-gutter-md">
            <q-input v-model.number="venueForm.latitude" outlined dense type="number" label="Latitude" class="col" />
            <q-input v-model.number="venueForm.longitude" outlined dense type="number" label="Longitude" class="col" />
          </div>
          <div class="jg-faint text-caption">Coordinates enable distance search (optional).</div>
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add" :loading="saving" :disable="!venueForm.name" @click="addVenue" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- New program dialog -->
    <q-dialog v-model="showProgram">
      <q-card style="min-width: 380px; border-radius: 18px">
        <q-card-section><div class="text-h6">New program</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="programForm.title" outlined dense label="Title" autofocus />
          <q-select v-model="programForm.category" outlined dense :options="categoryOptions" emit-value map-options label="Category" />
          <q-input v-model="programForm.description" outlined dense type="textarea" autogrow label="Description" />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Create" :loading="saving" :disable="!programForm.title" @click="addProgram" />
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
import { CATEGORIES, categoryMeta } from '@/lib/format'
import type { Org, Program, Venue } from '@/lib/types'

const props = defineProps<{ id: string }>()
const $q = useQuasar()

const org = ref<Org | null>(null)
const venues = ref<Venue[]>([])
const programs = ref<Program[]>([])
const saving = ref(false)
const showVenue = ref(false)
const showProgram = ref(false)

const categoryOptions = CATEGORIES.map((c) => ({ label: c.label, value: c.value }))
const venueForm = reactive({ name: '', suburb: '', postcode: '', latitude: null as number | null, longitude: null as number | null })
const programForm = reactive({ title: '', category: 'art', description: '' })

function statusColor(s: string): string {
  return { pending: 'warning', approved: 'positive', suspended: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  try {
    org.value = await api.org.get(props.id)
    ;[venues.value, programs.value] = await Promise.all([
      api.catalog.venues(props.id),
      api.catalog.programs(props.id),
    ])
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function addVenue(): Promise<void> {
  saving.value = true
  try {
    await api.catalog.createVenue({
      organisation_id: props.id,
      name: venueForm.name,
      suburb: venueForm.suburb || null,
      postcode: venueForm.postcode || null,
      latitude: venueForm.latitude,
      longitude: venueForm.longitude,
    })
    showVenue.value = false
    Object.assign(venueForm, { name: '', suburb: '', postcode: '', latitude: null, longitude: null })
    venues.value = await api.catalog.venues(props.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

async function addProgram(): Promise<void> {
  saving.value = true
  try {
    await api.catalog.createProgram({
      organisation_id: props.id,
      title: programForm.title,
      category: programForm.category,
      description: programForm.description || null,
    })
    showProgram.value = false
    Object.assign(programForm, { title: '', category: 'art', description: '' })
    programs.value = await api.catalog.programs(props.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-list { display: flex; flex-direction: column; gap: 10px; }
.jg-listrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  text-decoration: none;
  color: inherit;
}
</style>
