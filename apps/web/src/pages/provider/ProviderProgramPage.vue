<template>
  <q-page class="jg-page" style="max-width: 900px">
    <q-btn
      v-if="program"
      flat dense no-caps icon="arrow_back" label="Back to organisation"
      :to="{ name: 'provider-org', params: { id: program.organisation_id } }"
      class="jg-muted q-mb-md"
    />

    <template v-if="program">
      <header class="row items-center justify-between q-mb-lg">
        <div>
          <div class="row items-center q-gutter-sm">
            <span class="jg-pill"><q-icon :name="categoryMeta(program.category).icon" size="15px" /> {{ categoryMeta(program.category).label }}</span>
            <q-chip dense square :color="program.status === 'published' ? 'positive' : 'grey-5'" text-color="white" :label="program.status" />
          </div>
          <h1 class="text-h4 q-mt-sm q-mb-none">{{ program.title }}</h1>
        </div>
        <q-btn
          v-if="program.status !== 'published'"
          unelevated no-caps color="primary" icon="publish" label="Publish"
          :loading="publishing" @click="publish"
        />
      </header>

      <div class="row items-center justify-between q-mb-sm">
        <h2 class="text-h6 q-my-none">Sessions</h2>
        <q-btn unelevated no-caps color="primary" icon="add" label="Add session" :disable="!venues.length" @click="showSession = true" />
      </div>
      <div v-if="!venues.length" class="jg-muted text-caption q-mb-md">
        Add a venue on the organisation page before scheduling sessions.
      </div>

      <div v-if="sessions.length" class="jg-list">
        <div v-for="s in sessions" :key="s.id" class="jg-card jg-srow" :class="{ 'jg-srow--cancelled': s.status === 'cancelled' }">
          <div class="jg-srow__info">
            <div class="text-weight-600">
              {{ dayLabel(s.starts_at) }} · {{ timeRange(s.starts_at, s.ends_at) }}
            </div>
            <div class="jg-faint text-caption">
              {{ venueName(s.venue_id) }} · {{ money(s.price_cents) }} · ages {{ s.age_min }}–{{ s.age_max }}
            </div>
          </div>
          <div class="jg-srow__stat">
            <div class="text-weight-600">{{ s.seats_taken }}/{{ s.capacity }}</div>
            <div class="jg-faint text-caption">booked</div>
            <div
              v-if="waitlistLabel(s.id)"
              class="text-primary text-caption text-weight-600 q-mt-xs"
            >
              <q-icon name="hourglass_top" size="13px" /> {{ waitlistLabel(s.id) }}
            </div>
          </div>
          <div class="jg-srow__actions">
            <template v-if="s.status === 'cancelled'">
              <q-chip dense square color="grey-6" text-color="white" label="cancelled" />
            </template>
            <template v-else>
              <q-btn flat dense no-caps color="primary" icon="groups" label="Roster" @click="openRoster(s)" />
              <q-btn flat dense no-caps color="primary" icon="campaign" label="Message" @click="openBroadcast(s)" />
              <q-btn flat dense no-caps color="negative" icon="cancel" label="Cancel" @click="confirmCancel(s)" />
            </template>
          </div>
        </div>
      </div>
      <EmptyState v-else icon="event_busy" title="No sessions yet" subtitle="Add a session to open it for bookings." />
    </template>

    <!-- Add session dialog -->
    <q-dialog v-model="showSession">
      <q-card style="min-width: 420px; border-radius: 18px">
        <q-card-section><div class="text-h6">Add session</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-select v-model="sessionForm.venue_id" outlined dense :options="venueOptions" emit-value map-options label="Venue" />
          <div class="row q-col-gutter-md">
            <q-input v-model="sessionForm.starts_at" outlined dense type="datetime-local" label="Starts" stack-label class="col" />
            <q-input v-model="sessionForm.ends_at" outlined dense type="datetime-local" label="Ends" stack-label class="col" />
          </div>
          <div class="row q-col-gutter-md">
            <q-input v-model.number="sessionForm.capacity" outlined dense type="number" label="Capacity" class="col" />
            <q-input v-model.number="sessionForm.price" outlined dense type="number" prefix="$" label="Price / child" class="col" />
          </div>
          <div class="row q-col-gutter-md">
            <q-input v-model.number="sessionForm.age_min" outlined dense type="number" label="Min age" class="col" />
            <q-input v-model.number="sessionForm.age_max" outlined dense type="number" label="Max age" class="col" />
          </div>
          <div class="row q-col-gutter-md items-center">
            <q-select v-model="sessionForm.session_type" outlined dense :options="dayTypeOptions" emit-value map-options label="Day type" class="col" />
            <q-toggle v-model="sessionForm.drop_off" label="Drop-off" color="primary" class="col" />
          </div>
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add session" :loading="saving" :disable="!sessionValid" @click="addSession" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Roster dialog -->
    <q-dialog v-model="showRoster">
      <q-card style="min-width: 520px; border-radius: 18px">
        <q-card-section class="row items-center">
          <div class="text-h6">Roster ({{ roster?.count ?? 0 }})</div>
          <q-space />
          <q-btn flat dense no-caps icon="download" label="CSV" :disable="!roster?.count" @click="downloadCsv" />
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-list separator>
          <q-item v-for="r in roster?.rows ?? []" :key="r.booking_id">
            <q-item-section>
              <q-item-label>{{ r.child_first_name }} · {{ r.age }} yrs</q-item-label>
              <q-item-label caption>
                <span v-if="r.medical_notes">⚕ {{ r.medical_notes }} · </span>
                {{ r.emergency_contact_name || 'no emergency contact' }}
                <span v-if="r.emergency_contact_phone"> ({{ r.emergency_contact_phone }})</span>
              </q-item-label>
            </q-item-section>
          </q-item>
          <q-item v-if="roster && roster.count === 0">
            <q-item-section class="jg-muted">No bookings yet.</q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-dialog>

    <!-- Broadcast (message families) dialog -->
    <q-dialog v-model="showBroadcast">
      <q-card style="min-width: 460px; max-width: 540px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Message families</div>
          <div class="jg-faint text-caption">
            Sent to every family with a confirmed booking on this session.
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-select
            v-model="broadcastTemplate" outlined dense emit-value map-options
            :options="templateOptions" label="Template"
            @update:model-value="applyTemplate"
          />
          <q-input v-model="broadcastForm.subject" outlined dense label="Subject" />
          <q-input
            v-model="broadcastForm.body" outlined type="textarea" autogrow
            label="Message" :rules="[(v) => !!v.trim() || 'Write a short message']"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" icon="send" label="Send to families"
            :loading="sending"
            :disable="!broadcastForm.subject.trim() || !broadcastForm.body.trim()"
            @click="sendBroadcast"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { categoryMeta, dayLabel, money, timeRange } from '@/lib/format'
import type { CatalogSession, Program, RosterOut, SessionWaitlist, Venue } from '@/lib/types'

const props = defineProps<{ id: string }>()
const $q = useQuasar()

const program = ref<Program | null>(null)
const sessions = ref<CatalogSession[]>([])
const venues = ref<Venue[]>([])
const publishing = ref(false)
const saving = ref(false)
const showSession = ref(false)
const showRoster = ref(false)
const roster = ref<RosterOut | null>(null)
const waitlistCounts = ref<Record<string, SessionWaitlist>>({})
let rosterSessionId = ''

// --- Broadcast / message families (PRD §8.5) ---
const TEMPLATES = [
  {
    key: 'what_to_bring',
    label: 'What to bring',
    subject: 'What to bring',
    body: 'Please pack a hat, sunscreen, a labelled water bottle, and morning tea. See you soon!',
  },
  {
    key: 'reminder',
    label: 'Friendly reminder',
    subject: 'See you soon!',
    body: 'Just a reminder that your session is coming up. Drop-off is at the venue at the listed start time.',
  },
  { key: 'update', label: 'An update', subject: 'An update about your session', body: '' },
  { key: 'custom', label: 'Custom message', subject: '', body: '' },
]
const templateOptions = TEMPLATES.map((t) => ({ label: t.label, value: t.key }))
const showBroadcast = ref(false)
const sending = ref(false)
const broadcastTemplate = ref('what_to_bring')
const broadcastForm = reactive({ subject: '', body: '' })
let broadcastSessionId = ''

function applyTemplate(key: string): void {
  const t = TEMPLATES.find((x) => x.key === key)
  if (t) Object.assign(broadcastForm, { subject: t.subject, body: t.body })
}

function openBroadcast(s: CatalogSession): void {
  broadcastSessionId = s.id
  broadcastTemplate.value = 'what_to_bring'
  applyTemplate('what_to_bring')
  showBroadcast.value = true
}

async function sendBroadcast(): Promise<void> {
  sending.value = true
  try {
    const res = await api.comms.broadcast(broadcastSessionId, {
      subject: broadcastForm.subject.trim(),
      body: broadcastForm.body.trim(),
      template_key: broadcastTemplate.value,
    })
    showBroadcast.value = false
    $q.notify({
      type: 'positive',
      message: `Sent to ${res.recipient_count} ${res.recipient_count === 1 ? 'family' : 'families'}.`,
    })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not send message') })
  } finally {
    sending.value = false
  }
}

const dayTypeOptions = [
  { label: 'Half day', value: 'half_day' },
  { label: 'Full day', value: 'full_day' },
]
const venueOptions = computed(() => venues.value.map((v) => ({ label: v.name, value: v.id })))

const sessionForm = reactive({
  venue_id: '',
  starts_at: '',
  ends_at: '',
  capacity: 12,
  price: 50,
  age_min: 5,
  age_max: 12,
  session_type: 'full_day' as 'half_day' | 'full_day',
  drop_off: true,
})

const sessionValid = computed(
  () =>
    sessionForm.venue_id &&
    sessionForm.starts_at &&
    sessionForm.ends_at &&
    sessionForm.capacity > 0 &&
    sessionForm.age_min <= sessionForm.age_max,
)

function venueName(id: string): string {
  return venues.value.find((v) => v.id === id)?.name ?? 'Venue'
}

function waitlistLabel(sessionId: string): string {
  const c = waitlistCounts.value[sessionId]
  if (!c) return ''
  const parts = []
  if (c.offered) parts.push(`${c.offered} offered`)
  if (c.waiting) parts.push(`${c.waiting} waiting`)
  return parts.join(' · ')
}

async function loadWaitlistCounts(): Promise<void> {
  // Only full sessions can have a queue — fetch counts just for those.
  const full = sessions.value.filter((s) => s.seats_taken >= s.capacity && s.status !== 'cancelled')
  await Promise.all(
    full.map((s) =>
      api.waitlist
        .sessionCounts(s.id)
        .then((c) => {
          waitlistCounts.value[s.id] = c
        })
        .catch(() => {
          /* non-fatal */
        }),
    ),
  )
}

async function load(): Promise<void> {
  try {
    program.value = await api.catalog.program(props.id)
    ;[sessions.value, venues.value] = await Promise.all([
      api.catalog.programSessions(props.id),
      api.catalog.venues(program.value.organisation_id),
    ])
    await loadWaitlistCounts()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function publish(): Promise<void> {
  publishing.value = true
  try {
    program.value = await api.catalog.publishProgram(props.id)
    $q.notify({ type: 'positive', message: 'Program published — now searchable' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not publish') })
  } finally {
    publishing.value = false
  }
}

async function addSession(): Promise<void> {
  saving.value = true
  try {
    await api.catalog.createSession(props.id, {
      venue_id: sessionForm.venue_id,
      starts_at: new Date(sessionForm.starts_at).toISOString(),
      ends_at: new Date(sessionForm.ends_at).toISOString(),
      capacity: sessionForm.capacity,
      price_cents: Math.round(sessionForm.price * 100),
      age_min: sessionForm.age_min,
      age_max: sessionForm.age_max,
      session_type: sessionForm.session_type,
      drop_off: sessionForm.drop_off,
    })
    showSession.value = false
    sessions.value = await api.catalog.programSessions(props.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not add session') })
  } finally {
    saving.value = false
  }
}

async function openRoster(s: CatalogSession): Promise<void> {
  rosterSessionId = s.id
  roster.value = null
  showRoster.value = true
  try {
    roster.value = await api.roster.forSession(s.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function downloadCsv(): Promise<void> {
  try {
    const text = await api.roster.csv(rosterSessionId)
    const blob = new Blob([text], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `roster-${rosterSessionId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

function confirmCancel(s: CatalogSession): void {
  $q.dialog({
    title: 'Cancel this session?',
    message: 'All bookings will be cancelled and paid families refunded. This cannot be undone.',
    cancel: true,
    ok: { label: 'Cancel session', color: 'negative', unelevated: true, noCaps: true },
  }).onOk(async () => {
    try {
      const res = await api.booking.cancelSession(s.id)
      $q.notify({
        type: 'positive',
        message: `Cancelled — ${res.refunded_payments} payment(s) refunded`,
      })
      sessions.value = await api.catalog.programSessions(props.id)
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err) })
    }
  })
}

onMounted(load)
</script>

<style scoped>
.jg-list { display: flex; flex-direction: column; gap: 10px; }
.jg-srow {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 18px;
  padding: 14px 18px;
}
.jg-srow--cancelled { opacity: 0.6; }
.jg-srow__stat { text-align: center; min-width: 60px; }
.jg-srow__actions { display: flex; gap: 4px; }
@media (max-width: 599px) {
  .jg-srow { grid-template-columns: 1fr; gap: 8px; }
}
</style>
