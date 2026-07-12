<template>
  <q-page>
    <!-- Hero -->
    <section class="jg-hero">
      <div class="jg-hero__inner">
        <div class="jg-eyebrow" style="color: #fff; opacity: 0.85">Perth · School holidays</div>
        <h1 class="jg-hero__title">Find the good stuff for the holidays</h1>
        <p class="jg-hero__sub">
          Art, sport, STEM and more — with live availability. Book everything in one go.
        </p>

        <div class="jg-searchbar">
          <q-input
            v-model="filters.suburb"
            dense
            borderless
            placeholder="Suburb or postcode"
            class="jg-searchbar__field"
            @keyup.enter="runSearch"
          >
            <template #prepend><q-icon name="place" /></template>
          </q-input>
          <div class="jg-searchbar__divider" />
          <q-input
            v-model="filters.date_from"
            dense
            borderless
            type="date"
            class="jg-searchbar__field jg-searchbar__field--date"
          >
            <template #prepend><q-icon name="event" /></template>
          </q-input>
          <q-btn
            unelevated
            color="primary"
            icon="search"
            label="Search"
            no-caps
            class="jg-searchbar__go"
            @click="runSearch"
          />
        </div>
        <div class="jg-hero__nearme">
          <q-btn
            flat
            dense
            no-caps
            color="white"
            icon="my_location"
            :loading="locating"
            :label="filters.lat ? 'Using your location' : 'Use my location'"
            @click="useMyLocation"
          />
        </div>
      </div>
    </section>

    <div class="jg-page">
      <!-- Category chips -->
      <div class="jg-cats">
        <button
          class="jg-cat"
          :class="{ 'jg-cat--on': filters.category === null }"
          @click="setCategory(null)"
        >
          <q-icon name="apps" size="18px" /> All
        </button>
        <button
          v-for="c in CATEGORIES"
          :key="c.value"
          class="jg-cat"
          :class="{ 'jg-cat--on': filters.category === c.value }"
          @click="setCategory(c.value)"
        >
          <q-icon :name="c.icon" size="18px" /> {{ c.label }}
        </button>
      </div>

      <!-- Secondary filters -->
      <div class="jg-filters jg-card">
        <div class="jg-filters__item">
          <span class="jg-filters__label">Child age</span>
          <q-input
            v-model.number="ageModel"
            dense
            outlined
            type="number"
            min="0"
            max="18"
            placeholder="Any"
            style="width: 90px"
            @update:model-value="debouncedSearch"
          />
        </div>
        <div class="jg-filters__item">
          <span class="jg-filters__label">Max price</span>
          <q-input
            v-model.number="priceDollars"
            dense
            outlined
            type="number"
            min="0"
            prefix="$"
            placeholder="Any"
            style="width: 110px"
            @update:model-value="debouncedSearch"
          />
        </div>
        <div class="jg-filters__item">
          <span class="jg-filters__label">Day type</span>
          <q-select
            v-model="filters.session_type"
            dense
            outlined
            clearable
            :options="dayTypeOptions"
            emit-value
            map-options
            placeholder="Any"
            style="width: 140px"
            @update:model-value="runSearch"
          />
        </div>
        <div class="jg-filters__item">
          <span class="jg-filters__label">When</span>
          <div class="row items-center q-gutter-xs">
            <q-chip
              v-for="opt in whenOptions"
              :key="opt.value ?? 'any'"
              clickable
              dense
              :color="filters.when === opt.value ? 'primary' : 'grey-3'"
              :text-color="filters.when === opt.value ? 'white' : 'dark'"
              :label="opt.label"
              @click="setWhen(opt.value)"
            />
          </div>
        </div>
        <q-space />
        <q-toggle
          v-model="filters.available_only"
          label="Available only"
          color="primary"
          @update:model-value="runSearch"
        />
      </div>

      <!-- Results -->
      <div class="jg-results-head">
        <h2 class="text-h6 q-my-none">
          {{ loading ? 'Searching…' : `${results.length} ${results.length === 1 ? 'activity' : 'activities'}` }}
        </h2>
        <span v-if="filters.lat" class="jg-pill">Nearest first</span>
      </div>

      <div v-if="loading" class="jg-grid">
        <div v-for="n in 6" :key="n" class="jg-card q-pa-md">
          <q-skeleton type="text" width="40%" />
          <q-skeleton type="text" width="80%" class="q-mt-sm" />
          <q-skeleton type="text" width="60%" />
          <q-skeleton type="rect" height="42px" class="q-mt-md" />
        </div>
      </div>

      <div v-else-if="results.length" class="jg-grid">
        <SessionCard v-for="card in results" :key="card.session_id" :card="card" />
      </div>

      <EmptyState
        v-else
        icon="search_off"
        title="No activities match yet"
        subtitle="Try widening the date, clearing a filter, or searching a different suburb."
      >
        <q-btn unelevated color="primary" no-caps label="Clear filters" @click="resetFilters" />
      </EmptyState>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import SessionCard from '@/components/SessionCard.vue'
import { api, apiError } from '@/lib/api'
import { CATEGORIES } from '@/lib/format'
import { useHead } from '@/lib/head'
import type { Category, SearchCard, SearchFilters } from '@/lib/types'

const $q = useQuasar()

useHead(() => ({
  title: "Kids' school-holiday activities & birthday parties in Perth | Juggle",
  description:
    "Find and book kids' holiday programs and birthday parties near you — search " +
    'by suburb, date and age with live seat availability, all in one cart.',
  canonical: `${window.location.origin}/`,
}))

const dayTypeOptions = [
  { label: 'Half day', value: 'half_day' },
  { label: 'Full day', value: 'full_day' },
]

function blankFilters(): SearchFilters {
  return {
    lat: null,
    lng: null,
    radius_km: 25,
    suburb: null,
    date_from: null,
    date_to: null,
    child_age: null,
    category: null,
    price_max_cents: null,
    session_type: null,
    when: null,
    available_only: true,
  }
}

const whenOptions: { label: string; value: SearchFilters['when'] }[] = [
  { label: 'Any day', value: null },
  { label: 'Weekend', value: 'weekend' },
  { label: 'After school', value: 'after_school' },
  { label: 'Weekday', value: 'weekday' },
]

const filters = reactive<SearchFilters>(blankFilters())
const results = ref<SearchCard[]>([])
const loading = ref(false)
const locating = ref(false)

// Friendlier bound models (age can be empty; price shown in dollars).
const ageModel = ref<number | null>(null)
const priceDollars = ref<number | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | undefined

function setWhen(value: SearchFilters['when']): void {
  filters.when = value
  void runSearch()
}

async function runSearch(): Promise<void> {
  filters.child_age = ageModel.value === null || Number.isNaN(ageModel.value) ? null : ageModel.value
  filters.price_max_cents =
    priceDollars.value === null || Number.isNaN(priceDollars.value)
      ? null
      : Math.round(priceDollars.value * 100)
  loading.value = true
  try {
    const res = await api.search.sessions(filters)
    results.value = res.items
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Search failed') })
  } finally {
    loading.value = false
  }
}

function debouncedSearch(): void {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, 350)
}

function setCategory(cat: Category | null): void {
  filters.category = cat
  runSearch()
}

function resetFilters(): void {
  Object.assign(filters, blankFilters())
  ageModel.value = null
  priceDollars.value = null
  runSearch()
}

function useMyLocation(): void {
  if (!navigator.geolocation) {
    $q.notify({ type: 'warning', message: 'Location is not available on this device' })
    return
  }
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      filters.lat = pos.coords.latitude
      filters.lng = pos.coords.longitude
      locating.value = false
      runSearch()
    },
    () => {
      locating.value = false
      $q.notify({ type: 'warning', message: 'Could not get your location' })
    },
  )
}

onMounted(runSearch)
</script>

<style scoped>
.jg-hero {
  background: radial-gradient(120% 140% at 15% 0%, #4f83f0 0%, #3b6fe0 45%, #2f57c7 100%);
  color: #fff;
  padding: 8px 20px 40px;
}
.jg-hero__inner {
  max-width: var(--jg-maxw);
  margin: 0 auto;
  padding-top: 34px;
}
.jg-hero__title {
  color: #fff;
  font-size: clamp(28px, 5vw, 44px);
  line-height: 1.05;
  margin: 8px 0 6px;
}
.jg-hero__sub {
  color: rgba(255, 255, 255, 0.9);
  font-size: 16px;
  margin: 0 0 22px;
  max-width: 520px;
}
.jg-searchbar {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  border-radius: 999px;
  padding: 6px 6px 6px 16px;
  box-shadow: var(--jg-shadow-lg);
  max-width: 640px;
}
.jg-searchbar__field { flex: 1 1 auto; color: var(--jg-ink); }
.jg-searchbar__field--date { max-width: 190px; }
.jg-searchbar__divider { width: 1px; height: 26px; background: var(--jg-line); }
.jg-searchbar__go { border-radius: 999px; padding: 8px 22px; }
.jg-hero__nearme { margin-top: 12px; }

.jg-cats {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 4px 2px 10px;
  margin-bottom: 8px;
}
.jg-cat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  border: 1px solid var(--jg-line);
  background: #fff;
  color: var(--jg-ink-soft);
  border-radius: 999px;
  padding: 8px 15px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 140ms ease;
}
.jg-cat:hover { border-color: #cfd6e6; }
.jg-cat--on {
  background: var(--jg-primary);
  border-color: var(--jg-primary);
  color: #fff;
}

.jg-filters {
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 14px 18px;
  flex-wrap: wrap;
}
.jg-filters__item { display: flex; align-items: center; gap: 10px; }
.jg-filters__label { font-size: 13px; font-weight: 600; color: var(--jg-ink-soft); }

.jg-results-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 26px 0 14px;
}
.jg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}
</style>
