<template>
  <q-page class="jg-page" style="max-width: 900px">
    <header class="q-mb-lg">
      <div class="jg-eyebrow">✨ Holiday planner</div>
      <h1 class="text-h4 q-my-none">Plan the whole break in one go</h1>
      <p class="jg-muted q-mt-sm">
        Tell us your kids' ages, when, and what they're into — we'll build a day-by-day plan from
        live, bookable sessions.
      </p>
    </header>

    <!-- Brief -->
    <section class="jg-card q-pa-lg q-mb-lg">
      <div class="row q-col-gutter-md">
        <div class="col-12 col-sm-6">
          <div class="jg-label">Kids' ages</div>
          <q-select
            v-model="ages"
            multiple
            use-chips
            outlined
            dense
            :options="ageOptions"
            hint="Pick one or more"
          />
        </div>
        <div class="col-6 col-sm-3">
          <div class="jg-label">From</div>
          <q-input v-model="dateFrom" outlined dense type="date" />
        </div>
        <div class="col-6 col-sm-3">
          <div class="jg-label">To</div>
          <q-input v-model="dateTo" outlined dense type="date" />
        </div>
        <div class="col-12 col-sm-6">
          <div class="jg-label">Suburb (optional)</div>
          <q-input v-model="suburb" outlined dense placeholder="e.g. Scarborough" />
        </div>
        <div class="col-12 col-sm-6">
          <div class="jg-label">Total budget (optional)</div>
          <q-input v-model.number="budget" outlined dense type="number" prefix="$" placeholder="Any" />
        </div>
      </div>

      <div class="jg-label q-mt-md">Interests</div>
      <div class="jg-cats">
        <button
          v-for="c in CATEGORIES"
          :key="c.value"
          type="button"
          class="jg-cat"
          :class="{ 'jg-cat--on': interests.includes(c.value) }"
          @click="toggleInterest(c.value)"
        >
          <q-icon :name="c.icon" size="16px" /> {{ c.label }}
        </button>
      </div>

      <div class="jg-label q-mt-md">When</div>
      <q-btn-toggle
        v-model="dayType"
        no-caps
        unelevated
        toggle-color="primary"
        color="grey-2"
        text-color="grey-8"
        :options="[
          { value: 'any', label: 'Any day' },
          { value: 'weekday', label: 'Weekdays' },
          { value: 'weekend', label: 'Weekends' },
        ]"
      />

      <q-btn
        unelevated
        color="primary"
        no-caps
        size="lg"
        class="q-mt-lg"
        icon="auto_awesome"
        label="Build my plan"
        :loading="loading"
        :disable="!ages.length || !dateFrom || !dateTo"
        @click="build"
      />
    </section>

    <!-- Result -->
    <section v-if="plan">
      <div v-if="plan.days.length" class="jg-summary jg-card q-pa-md q-mb-md">
        <q-icon name="auto_awesome" color="primary" size="20px" />
        <span>{{ plan.summary }}</span>
        <q-space />
        <span class="jg-total">{{ money(plan.total_cents) }} total</span>
      </div>

      <div v-if="plan.days.length && auth.isAuthed" class="q-mb-lg">
        <q-btn
          v-if="!addedToCart"
          unelevated
          color="primary"
          no-caps
          icon="add_shopping_cart"
          label="Add whole plan to cart"
          :loading="addingAll"
          @click="addWholePlan"
        />
        <q-btn
          v-else
          outline
          color="primary"
          no-caps
          icon="shopping_cart"
          label="View cart"
          :to="{ name: 'cart' }"
        />
        <span class="jg-muted text-caption q-ml-sm">
          Holds a seat per matching child for every session — you can adjust before checkout.
        </span>
      </div>
      <div v-else-if="plan.days.length && !auth.isAuthed" class="jg-muted text-caption q-mb-lg">
        <q-icon name="info" size="16px" /> Sign in and add your kids to book this plan in one tap.
      </div>

      <div v-for="day in plan.days" :key="day.day" class="q-mb-lg">
        <div class="jg-dayhead">{{ longDay(day.day) }}</div>
        <div class="q-gutter-sm">
          <router-link
            v-for="item in day.items"
            :key="item.session.session_id"
            :to="{ name: 'session', params: { id: item.session.session_id } }"
            class="jg-plan-item jg-card jg-card--hover"
          >
            <div class="jg-plan-item__cat">
              <q-icon :name="categoryMeta(item.session.category).icon" size="20px" />
            </div>
            <div class="jg-plan-item__body">
              <div class="row items-center no-wrap">
                <div class="text-weight-600 ellipsis">{{ item.session.title }}</div>
                <q-space />
                <div class="text-weight-700">{{ money(item.session.price_cents) }}</div>
              </div>
              <div class="jg-muted text-caption">
                {{ item.session.organisation_name }} ·
                {{ timeRange(item.session.starts_at, item.session.ends_at) }}
                <template v-if="item.session.suburb"> · {{ item.session.suburb }}</template>
              </div>
              <div class="jg-reason">“{{ item.reason }}”</div>
            </div>
            <q-icon name="chevron_right" color="grey-6" class="self-center" />
          </router-link>
        </div>
      </div>

      <EmptyState
        v-if="!plan.days.length"
        icon="event_busy"
        title="No plan yet"
        :subtitle="plan.summary"
      />
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { ageAt, CATEGORIES, categoryMeta, money, timeRange } from '@/lib/format'
import type { Child, PlanOut } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'

const $q = useQuasar()
const router = useRouter()
const auth = useAuthStore()
const cart = useCartStore()

const ageOptions = computed(() => Array.from({ length: 16 }, (_, i) => i + 2))
const ages = ref<number[]>([])
const dateFrom = ref('')
const dateTo = ref('')
const suburb = ref('')
const budget = ref<number | null>(null)
const interests = ref<string[]>([])
const dayType = ref<'any' | 'weekday' | 'weekend'>('any')

const loading = ref(false)
const plan = ref<PlanOut | null>(null)
const addingAll = ref(false)
const addedToCart = ref(false)

function toggleInterest(value: string): void {
  const i = interests.value.indexOf(value)
  if (i === -1) interests.value.push(value)
  else interests.value.splice(i, 1)
}

function longDay(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

async function build(): Promise<void> {
  loading.value = true
  addedToCart.value = false
  try {
    plan.value = await api.planner.plan({
      ages: ages.value,
      date_from: dateFrom.value,
      date_to: dateTo.value,
      suburb: suburb.value || null,
      budget_cents: budget.value ? Math.round(budget.value * 100) : null,
      categories: interests.value.length ? interests.value : null,
      day_type: dayType.value === 'any' ? null : dayType.value,
    })
  } catch (err) {
    plan.value = null
    $q.notify({ type: 'negative', message: apiError(err, 'Could not build a plan') })
  } finally {
    loading.value = false
  }
}

/** Children whose age at the session start falls in the session's age range. */
function matchingChildren(item: PlanOut['days'][number]['items'][number], kids: Child[]): Child[] {
  const s = item.session
  return kids.filter((c) => {
    const age = ageAt(c.date_of_birth, s.starts_at)
    return age >= s.age_min && age <= s.age_max
  })
}

/**
 * Hold a seat for every matching child across every session in the plan and add
 * each to the cart. Reuses the same session→hold→cart rails as the detail page —
 * no new money code. Sessions with no age-matching child are skipped.
 */
async function addWholePlan(): Promise<void> {
  if (!plan.value) return
  addingAll.value = true
  try {
    let kids: Child[]
    try {
      kids = await api.children.list()
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err, 'Could not load your kids') })
      return
    }
    if (kids.length === 0) {
      $q.notify({ type: 'warning', message: 'Add a child to your profile first, then add the plan.' })
      return
    }

    const items = plan.value.days.flatMap((d) => d.items)
    let added = 0
    let skipped = 0
    let failed = 0
    for (const item of items) {
      const matched = matchingChildren(item, kids)
      if (matched.length === 0) {
        skipped += 1
        continue
      }
      try {
        const hold = await api.inventory.hold(item.session.session_id, matched.length)
        cart.add({
          holdId: hold.id,
          sessionId: item.session.session_id,
          title: item.session.title,
          orgName: item.session.organisation_name,
          venueName: item.session.venue_name,
          startsAt: item.session.starts_at,
          endsAt: item.session.ends_at,
          priceCents: item.session.price_cents,
          childIds: matched.map((c) => c.id),
        })
        added += 1
      } catch {
        failed += 1 // seats may have gone since the plan was built — skip and continue
      }
    }

    if (added === 0) {
      $q.notify({
        type: 'warning',
        message: skipped
          ? "None of the plan's sessions matched your kids' ages."
          : 'Could not hold seats — they may have just sold out.',
      })
      return
    }
    addedToCart.value = true
    const extras = [
      skipped ? `${skipped} skipped (age)` : '',
      failed ? `${failed} unavailable` : '',
    ].filter(Boolean)
    $q.notify({
      type: 'positive',
      message: `Added ${added} session${added === 1 ? '' : 's'} to cart`
        + (extras.length ? ` · ${extras.join(', ')}` : ''),
      actions: [{ label: 'View cart', color: 'white', handler: () => router.push({ name: 'cart' }) }],
    })
  } finally {
    addingAll.value = false
  }
}
</script>

<style scoped>
.jg-label { font-size: 13px; font-weight: 600; color: var(--jg-ink-soft); margin-bottom: 6px; }
.jg-cats { display: flex; flex-wrap: wrap; gap: 8px; }
.jg-cat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--jg-line);
  background: #fff;
  color: var(--jg-ink-soft);
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
}
.jg-cat--on { background: var(--jg-primary-tint); border-color: var(--jg-primary); color: var(--jg-primary); }
.jg-summary { display: flex; align-items: center; gap: 10px; font-size: 14.5px; }
.jg-total { font-weight: 700; }
.jg-dayhead {
  font-family: 'Fraunces', serif;
  font-weight: 700;
  font-size: 18px;
  margin-bottom: 8px;
}
.jg-plan-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  text-decoration: none;
  color: inherit;
}
.jg-plan-item__cat {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--jg-primary-tint);
  color: var(--jg-primary);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.jg-plan-item__body { flex: 1; min-width: 0; }
.jg-reason { font-size: 13px; color: var(--jg-ink-soft); font-style: italic; margin-top: 4px; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
