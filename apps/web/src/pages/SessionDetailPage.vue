<template>
  <q-page class="jg-page">
    <q-btn flat dense no-caps icon="arrow_back" label="Back to results" :to="{ name: 'discover' }" class="jg-muted q-mb-md" />

    <div v-if="loading" class="jg-detail">
      <div>
        <q-skeleton type="text" width="30%" />
        <q-skeleton type="text" width="70%" height="34px" class="q-mt-sm" />
        <q-skeleton type="rect" height="120px" class="q-mt-lg" />
      </div>
      <q-skeleton type="rect" height="280px" />
    </div>

    <div v-else-if="session" class="jg-detail">
      <!-- Main -->
      <div>
        <span class="jg-pill"><q-icon :name="cat.icon" size="15px" /> {{ cat.label }}</span>
        <h1 class="text-h4 q-mt-sm q-mb-xs">{{ session.title }}</h1>
        <div class="jg-muted text-subtitle1">by {{ session.organisation_name }}</div>

        <div class="jg-detail__facts jg-card q-mt-lg">
          <div class="jg-fact">
            <q-icon name="event" color="primary" />
            <div>
              <div class="jg-fact__label">Date</div>
              <div class="jg-fact__value">{{ fullDay(session.starts_at) }}</div>
            </div>
          </div>
          <div class="jg-fact">
            <q-icon name="schedule" color="primary" />
            <div>
              <div class="jg-fact__label">Time</div>
              <div class="jg-fact__value">{{ timeRange(session.starts_at, session.ends_at) }}</div>
            </div>
          </div>
          <div class="jg-fact">
            <q-icon name="cake" color="primary" />
            <div>
              <div class="jg-fact__label">Ages</div>
              <div class="jg-fact__value">{{ session.age_min }}–{{ session.age_max }} years</div>
            </div>
          </div>
          <div class="jg-fact">
            <q-icon name="place" color="primary" />
            <div>
              <div class="jg-fact__label">Where</div>
              <div class="jg-fact__value">
                {{ session.venue_name }}<template v-if="session.suburb">, {{ session.suburb }}</template>
              </div>
            </div>
          </div>
        </div>

        <div v-if="session.description" class="q-mt-lg">
          <h2 class="text-h6">About</h2>
          <p class="jg-muted" style="white-space: pre-line">{{ session.description }}</p>
        </div>

        <div class="q-mt-lg jg-tags">
          <span class="jg-pill jg-pill--muted">
            {{ session.session_type === 'half_day' ? 'Half day' : 'Full day' }}
          </span>
          <span class="jg-pill jg-pill--muted">
            {{ session.drop_off ? 'Drop-off' : 'Parent stays' }}
          </span>
        </div>

        <!-- Reviews (PRD §7.6) -->
        <section v-if="reviews" class="q-mt-xl">
          <div class="row items-center q-gutter-sm q-mb-md">
            <h2 class="text-h6 q-my-none">Reviews</h2>
            <template v-if="reviews.summary.count">
              <StarRating :model-value="Math.round(reviews.summary.average ?? 0)" size="18px" />
              <span class="text-weight-600">{{ reviews.summary.average?.toFixed(1) }}</span>
              <span class="jg-faint">
                · {{ reviews.summary.count }}
                {{ reviews.summary.count === 1 ? 'review' : 'reviews' }}
              </span>
            </template>
          </div>

          <div v-if="reviews.items.length" class="jg-reviews">
            <article v-for="r in reviews.items" :key="r.id" class="jg-card jg-review">
              <div class="row items-center q-gutter-sm">
                <StarRating :model-value="r.rating" size="15px" />
                <span class="text-weight-600">{{ r.author_label }}</span>
                <span class="jg-faint text-caption">· {{ dayLabel(r.created_at) }}</span>
                <span class="jg-badge"><q-icon name="verified" size="13px" /> Verified booking</span>
              </div>
              <p class="q-mt-sm q-mb-none" style="white-space: pre-line">{{ r.body }}</p>
              <div v-if="r.provider_reply" class="jg-review__reply">
                <div class="jg-faint text-caption text-weight-600">
                  <q-icon name="storefront" size="13px" /> Response from {{ session.organisation_name }}
                </div>
                <p class="q-mt-xs q-mb-none" style="white-space: pre-line">{{ r.provider_reply }}</p>
              </div>
            </article>
          </div>
          <p v-else class="jg-muted">No reviews yet — be the first after you attend.</p>
        </section>
      </div>

      <!-- Booking panel -->
      <aside class="jg-book jg-card">
        <div class="jg-book__price">
          {{ money(session.price_cents) }} <span class="jg-faint">/ child</span>
        </div>
        <div
          class="jg-book__seats"
          :class="seatsLeft <= 3 && seatsLeft > 0 ? 'text-secondary' : seatsLeft === 0 ? 'text-negative' : 'jg-muted'"
        >
          <q-icon name="event_seat" size="16px" />
          {{ seatsLeft > 0 ? `${seatsLeft} of ${session.capacity} seats left` : 'Sold out' }}
        </div>

        <q-separator class="q-my-md" />

        <template v-if="!auth.isAuthed">
          <p class="jg-muted">Sign in to add your kids and book.</p>
          <q-btn
            unelevated
            color="primary"
            no-caps
            class="full-width"
            label="Sign in to book"
            :to="{ name: 'login', query: { redirect: route.fullPath } }"
          />
        </template>

        <template v-else>
          <div class="text-weight-600 q-mb-sm">Who's coming?</div>

          <div v-if="children.length === 0" class="jg-muted q-mb-sm">
            Add a child to get started.
          </div>
          <div v-else class="jg-kidlist">
            <label
              v-for="child in children"
              :key="child.id"
              class="jg-kid"
              :class="{ 'jg-kid--off': !fits(child) }"
            >
              <q-checkbox
                v-model="selectedChildIds"
                :val="child.id"
                :disable="!fits(child)"
                color="primary"
                dense
              />
              <div class="jg-kid__body">
                <div class="text-weight-600">{{ child.first_name }}</div>
                <div class="jg-faint">
                  {{ ageAt(child.date_of_birth, session.starts_at) }} yrs
                  <span v-if="!fits(child)">· outside age range</span>
                </div>
              </div>
            </label>
          </div>

          <q-btn
            flat
            dense
            no-caps
            color="primary"
            icon="add"
            label="Add a child"
            class="q-mt-xs"
            @click="showAddChild = true"
          />

          <q-btn
            unelevated
            color="primary"
            no-caps
            class="full-width q-mt-md"
            :disable="selectedChildIds.length === 0 || seatsLeft < selectedChildIds.length"
            :loading="holding"
            :label="addLabel"
            @click="addToCart"
          />
          <div v-if="seatsLeft < selectedChildIds.length" class="text-negative text-caption q-mt-xs">
            Only {{ seatsLeft }} seat(s) left.
          </div>
        </template>
      </aside>
    </div>

    <EmptyState
      v-else
      icon="sentiment_dissatisfied"
      title="This activity isn't available"
      subtitle="It may have been unpublished or sold out."
    >
      <q-btn unelevated color="primary" no-caps label="Browse activities" :to="{ name: 'discover' }" />
    </EmptyState>

    <!-- Add child dialog -->
    <q-dialog v-model="showAddChild">
      <q-card style="min-width: 340px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Add a child</div>
          <div class="jg-faint text-caption">First name and date of birth only.</div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="newChild.first_name" outlined dense label="First name" autofocus />
          <q-input v-model="newChild.date_of_birth" outlined dense type="date" label="Date of birth" stack-label />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            no-caps
            label="Add child"
            :loading="savingChild"
            :disable="!newChild.first_name || !newChild.date_of_birth"
            @click="saveChild"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StarRating from '@/components/StarRating.vue'
import { api, apiError } from '@/lib/api'
import { ageAt, categoryMeta, dayLabel, money, timeRange } from '@/lib/format'
import { rememberSession } from '@/lib/sessionMemo'
import type { Child, ReviewList, SessionDetail } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'

const props = defineProps<{ id: string }>()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const cart = useCartStore()

const session = ref<SessionDetail | null>(null)
const reviews = ref<ReviewList | null>(null)
const loading = ref(true)
const children = ref<Child[]>([])
const selectedChildIds = ref<string[]>([])
const holding = ref(false)
const seatsLive = ref<number | null>(null)

const showAddChild = ref(false)
const savingChild = ref(false)
const newChild = reactive({ first_name: '', date_of_birth: '' })

const cat = computed(() => categoryMeta(session.value?.category ?? 'other'))
const seatsLeft = computed(() => seatsLive.value ?? session.value?.seats_remaining ?? 0)
const addLabel = computed(() =>
  selectedChildIds.value.length > 1
    ? `Add ${selectedChildIds.value.length} seats to cart`
    : 'Add to cart',
)

function fullDay(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function fits(child: Child): boolean {
  if (!session.value) return false
  const age = ageAt(child.date_of_birth, session.value.starts_at)
  return age >= session.value.age_min && age <= session.value.age_max
}

async function loadChildren(): Promise<void> {
  if (!auth.isAuthed) return
  try {
    children.value = await api.children.list()
  } catch {
    /* non-fatal */
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    session.value = await api.catalog.session(props.id)
    rememberSession(session.value.id, {
      title: session.value.title,
      orgName: session.value.organisation_name,
      startsAt: session.value.starts_at,
      endsAt: session.value.ends_at,
    })
    const avail = await api.inventory.availability(props.id)
    seatsLive.value = avail.seats_remaining
    try {
      reviews.value = await api.reviews.forProgram(session.value.program_id)
    } catch {
      reviews.value = null // non-fatal — reviews are supplementary
    }
  } catch {
    session.value = null
  } finally {
    loading.value = false
  }
  await loadChildren()
}

async function saveChild(): Promise<void> {
  savingChild.value = true
  try {
    const created = await api.children.create({
      first_name: newChild.first_name,
      date_of_birth: newChild.date_of_birth,
    })
    children.value.push(created)
    if (fits(created)) selectedChildIds.value.push(created.id)
    showAddChild.value = false
    newChild.first_name = ''
    newChild.date_of_birth = ''
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not add child') })
  } finally {
    savingChild.value = false
  }
}

async function addToCart(): Promise<void> {
  if (!session.value) return
  holding.value = true
  try {
    const hold = await api.inventory.hold(session.value.id, selectedChildIds.value.length)
    cart.add({
      holdId: hold.id,
      sessionId: session.value.id,
      title: session.value.title,
      orgName: session.value.organisation_name,
      venueName: session.value.venue_name,
      startsAt: session.value.starts_at,
      endsAt: session.value.ends_at,
      priceCents: session.value.price_cents,
      childIds: [...selectedChildIds.value],
    })
    $q.notify({
      type: 'positive',
      message: 'Added to cart',
      actions: [{ label: 'View cart', color: 'white', handler: () => router.push({ name: 'cart' }) }],
    })
    selectedChildIds.value = []
    const avail = await api.inventory.availability(session.value.id)
    seatsLive.value = avail.seats_remaining
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not hold seats') })
  } finally {
    holding.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-detail {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 32px;
  align-items: start;
}
@media (max-width: 899px) {
  .jg-detail { grid-template-columns: 1fr; }
}
.jg-detail__facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  padding: 20px;
}
.jg-fact { display: flex; gap: 12px; align-items: flex-start; }
.jg-fact .q-icon { margin-top: 2px; }
.jg-fact__label { font-size: 12px; color: var(--jg-ink-faint); font-weight: 600; }
.jg-fact__value { font-weight: 600; }
.jg-tags { display: flex; gap: 8px; }

.jg-book {
  padding: 20px;
  position: sticky;
  top: 84px;
}
.jg-book__price { font-size: 24px; font-weight: 700; }
.jg-book__seats { margin-top: 4px; font-weight: 600; font-size: 13.5px; }
.jg-kidlist { display: flex; flex-direction: column; gap: 8px; }
.jg-kid {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--jg-line);
  border-radius: 12px;
  padding: 6px 10px;
  cursor: pointer;
}
.jg-kid--off { opacity: 0.55; }
.jg-kid__body { line-height: 1.15; }

.jg-reviews { display: flex; flex-direction: column; gap: 12px; }
.jg-review { padding: 16px 18px; }
.jg-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--jg-primary);
  background: var(--jg-primary-tint);
  border-radius: 999px;
  padding: 1px 8px;
}
.jg-review__reply {
  margin-top: 12px;
  padding: 10px 12px;
  border-left: 3px solid var(--jg-line);
  background: #fafbfd;
  border-radius: 0 10px 10px 0;
}
</style>
