<template>
  <q-page class="jg-page" style="max-width: 720px">
    <q-btn flat dense no-caps icon="arrow_back" label="All plans"
           :to="{ name: 'party-plans' }" class="jg-muted q-mb-md" />

    <div v-if="loading" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" /><span>Loading…</span>
    </div>

    <template v-else-if="plan">
      <div class="row items-center justify-between q-mb-md">
        <h1 class="text-h4 q-my-none">Party vote</h1>
        <q-chip dense square :color="statusColor" text-color="white" :label="statusLabel" />
      </div>

      <!-- ============ DRAFT: build the vote ============ -->
      <template v-if="plan.status === 'draft'">
        <section class="jg-card q-pa-lg q-mb-md">
          <div class="row items-center justify-between q-mb-sm">
            <div class="text-weight-600">Options ({{ liveOptions.length }}/4)</div>
            <div class="row q-gutter-xs">
              <q-btn flat dense no-caps size="sm" icon="add" label="Package"
                     :disable="liveOptions.length >= 4" @click="openAddPackage" />
              <q-btn flat dense no-caps size="sm" icon="edit" label="Custom"
                     :disable="liveOptions.length >= 4 || hasCustom" @click="showCustom = true" />
            </div>
          </div>
          <div v-if="liveOptions.length" class="jg-list">
            <div v-for="o in liveOptions" :key="o.id" class="jg-optrow">
              <q-radio v-model="favouriteId" :val="o.id" @update:model-value="saveFavourite"
                       :label="undefined" dense />
              <div class="col">
                <div class="text-weight-500">
                  {{ optionTitle(o) }}
                  <q-icon v-if="o.id === favouriteId" name="star" color="amber" size="16px" />
                </div>
                <div class="jg-faint text-caption">{{ optionSub(o) }}</div>
              </div>
              <q-btn flat dense round size="sm" icon="close" color="grey-7"
                     @click="removeOption(o.id)" />
            </div>
          </div>
          <div v-else class="jg-muted text-caption">
            Add 2–4 options (at least one bookable package). ⭐ marks the birthday kid's favourite —
            it breaks ties.
          </div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="text-weight-600 q-mb-sm">Theme</div>
          <div class="row q-gutter-sm">
            <q-btn v-for="t in PLAN_THEMES" :key="t.key" no-caps unelevated
                   :color="plan.theme === t.key ? 'primary' : 'grey-3'"
                   :text-color="plan.theme === t.key ? 'white' : 'dark'"
                   :label="`${t.emoji} ${t.label}`" @click="setTheme(t.key)" />
          </div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="text-weight-600 q-mb-sm">Voting deadline</div>
          <div class="row items-end q-gutter-sm">
            <q-input v-model="deadlineInput" type="datetime-local" outlined dense stack-label
                     label="Votes close" style="max-width: 250px" />
            <q-btn no-caps unelevated color="primary" label="Save" :loading="saving"
                   :disable="!deadlineInput" @click="saveDeadline" />
          </div>
          <div v-for="w in plan.deadline_warnings" :key="w" class="text-orange-8 text-caption q-mt-sm">
            ⚠️ {{ w }}
          </div>
        </section>

        <q-btn unelevated color="primary" no-caps size="lg" class="full-width"
               label="Open voting &amp; get share link" :loading="saving"
               :disable="!canOpen" @click="openVoting" />
      </template>

      <!-- ============ OPEN: share, tally, approvals ============ -->
      <template v-else-if="plan.status === 'open'">
        <section class="jg-card q-pa-lg q-mb-md">
          <div class="row items-center justify-between q-mb-sm">
            <div class="text-weight-600">Party readiness</div>
            <span class="text-weight-700">{{ Math.round(readiness.pct * 100) }}%</span>
          </div>
          <q-linear-progress :value="readiness.pct" color="positive" track-color="grey-3"
                             size="10px" rounded class="q-mb-sm" />
          <div class="row q-gutter-sm">
            <span v-for="s in readiness.steps" :key="s.label" class="text-caption"
                  :class="s.done ? 'text-positive' : 'jg-muted'">
              {{ s.done ? '✓' : '○' }} {{ s.label }}
            </span>
          </div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="text-weight-600 q-mb-xs">Share this link to collect votes</div>
          <div class="row items-center q-gutter-sm">
            <q-input :model-value="shareUrl" readonly outlined dense class="col" />
            <q-btn no-caps unelevated color="primary" icon="content_copy" label="Copy"
                   @click="copyShare" />
          </div>
          <div class="jg-faint text-caption q-mt-sm">
            Voting closes {{ plan.deadline_at ? dayLabel(plan.deadline_at) : '' }}.
            <q-btn flat dense no-caps size="sm" label="Extend 48h" :loading="saving" @click="extend" />
          </div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="text-weight-600 q-mb-sm">Live results</div>
          <div v-for="o in liveOptions" :key="o.id" class="q-mb-sm">
            <div class="row items-center justify-between">
              <span>{{ optionTitle(o) }} <q-icon v-if="o.is_favourite" name="star" color="amber" size="14px" /></span>
              <span class="text-weight-600">{{ o.votes }}</span>
            </div>
            <q-linear-progress :value="voteFraction(o)" color="primary" track-color="grey-3"
                               size="8px" rounded class="q-mt-xs" />
          </div>
          <div class="jg-faint text-caption q-mt-sm">{{ plan.rsvp_yes_headcount }} guests coming</div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="text-weight-600 q-mb-sm">Guests</div>
          <div v-if="!plan.invites.length" class="jg-muted text-caption">No RSVPs yet.</div>
          <div v-for="inv in plan.invites" :key="inv.id" class="jg-optrow">
            <div class="col">
              <div class="text-weight-500">
                {{ inv.nickname || inv.parent_name }}
                <q-chip v-if="inv.status !== 'approved'" dense square size="sm"
                        color="grey-5" text-color="white" :label="inv.status" />
              </div>
              <div class="jg-faint text-caption">
                {{ inv.attending ? `Coming · ${inv.kid_count} kids` : 'Not coming' }}
              </div>
            </div>
            <div class="row q-gutter-xs">
              <q-btn v-if="inv.status === 'pending'" flat dense no-caps size="sm" color="positive"
                     label="Approve" @click="setInvite(inv.id, 'approve')" />
              <q-btn v-if="inv.status !== 'blocked'" flat dense round size="sm" icon="block"
                     color="grey-7" @click="setInvite(inv.id, 'block')" />
            </div>
          </div>
        </section>
      </template>

      <!-- ============ DEPOSIT HAND-OFF (after confirm; plan is already 'booked') ============ -->
      <section v-else-if="depositPending" class="jg-card q-pa-lg q-mb-md">
        <div class="text-weight-600 q-mb-sm">Pay the deposit to lock it in</div>
        <div class="jg-faint text-caption q-mb-md">Deposit due now: {{ money(plan.deposit_cents || 0) }}</div>
        <StripePaymentPanel
          v-if="live && plan.deposit_client_secret && plan.deposit_payment_id"
          :publishable-key="publishableKey"
          :client-secret="plan.deposit_client_secret"
          :payment-id="plan.deposit_payment_id"
          :amount-cents="plan.deposit_cents || 0"
          :return-url="returnUrl"
          @paid="onDepositPaid" @pending="onDepositPaid" @failed="onDepositFailed"
        />
        <q-btn v-else unelevated color="primary" no-caps size="lg" class="full-width"
               :loading="saving" :label="`Pay deposit ${money(plan.deposit_cents || 0)}`"
               @click="payDepositDev" />
      </section>

      <!-- ============ RESOLVED: pick winner & book ============ -->
      <template v-else-if="plan.status === 'resolved'">
        <section class="jg-card q-pa-lg q-mb-md">
          <div v-if="plan.winning_option_id && winner">
            <div class="text-h6 q-mb-xs">🎉 The winner is</div>
            <div class="text-weight-600">{{ optionTitle(winner) }}</div>
            <div class="jg-faint text-caption">{{ optionSub(winner) }}</div>
          </div>
          <div v-else>
            <div class="text-h6 q-mb-xs">It's a tie — you choose!</div>
          </div>

          <q-separator class="q-my-md" />
          <div class="text-weight-600 q-mb-sm">Confirm the booking</div>
          <q-select v-model="confirmOptionId" :options="packageOptionChoices" emit-value map-options
                    outlined dense label="Party to book" class="q-mb-sm" />
          <q-input v-model.number="confirmHeadcount" type="number" outlined dense min="1"
                   label="Number of guests" style="max-width: 200px" class="q-mb-md"
                   :hint="`Suggested: ${plan.rsvp_yes_headcount} (from RSVPs)`" />
          <q-banner v-if="!bookableOptions.length" dense class="bg-orange-1 text-orange-9 q-mb-md">
            The winning option is a custom idea — book something similar from the marketplace.
          </q-banner>
          <q-btn unelevated color="primary" no-caps size="lg" class="full-width"
                 label="Confirm &amp; pay deposit" :loading="saving"
                 :disable="!confirmOptionId" @click="confirm" />
        </section>
      </template>

      <!-- ============ BOOKED / CLOSED ============ -->
      <template v-else>
        <section class="jg-card q-pa-lg">
          <div v-if="plan.status === 'booked'" class="row items-center q-gutter-sm">
            <q-icon name="check_circle" color="positive" size="28px" />
            <div>
              <div class="text-h6">Party booked 🎉</div>
              <div class="jg-faint text-caption">Your guests will be told the final plan.</div>
            </div>
          </div>
          <div v-else class="jg-muted">This plan has closed.</div>
        </section>
      </template>
    </template>

    <!-- Add package option dialog -->
    <q-dialog v-model="showAddPkg">
      <q-card style="min-width: 400px; border-radius: 18px">
        <q-card-section><div class="text-h6">Add a party option</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-select v-model="pkgSel" :options="packageChoices" emit-value map-options outlined dense
                    label="Party package" :loading="!packages.length"
                    @update:model-value="loadSlots">
            <template #no-option>
              <q-item><q-item-section class="jg-muted">
                No party packages available yet.
              </q-item-section></q-item>
            </template>
          </q-select>
          <q-select v-model="slotSel" :options="slotChoices" emit-value map-options outlined dense
                    label="Date &amp; time" :disable="!pkgSel || noSlotsForPackage"
                    :loading="slotsLoading" />
          <q-banner v-if="noSlotsForPackage" dense class="bg-orange-1 text-orange-9">
            This package has no upcoming dates. Add dates to it from
            <b>For providers → your org → Party packages → Add slots</b>, then come back — or pick a
            different package.
          </q-banner>
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add" :loading="saving"
                 :disable="!pkgSel || !slotSel" @click="addPackage" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Custom option dialog -->
    <q-dialog v-model="showCustom">
      <q-card style="min-width: 380px; border-radius: 18px">
        <q-card-section><div class="text-h6">Custom option</div></q-card-section>
        <q-card-section>
          <q-input v-model="customText" outlined dense autofocus maxlength="80"
                   label="e.g. Backyard party at ours" />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add" :loading="saving"
                 :disable="!customText.trim()" @click="addCustom" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import StripePaymentPanel from '@/components/StripePaymentPanel.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money, timeRange } from '@/lib/format'
import { PLAN_THEMES } from '@/lib/planTheme'
import type { PartyPackageDetail, PlanOptionView, PlanView } from '@/lib/types'

const props = defineProps<{ id: string }>()
const $q = useQuasar()

const plan = ref<PlanView | null>(null)
const loading = ref(true)
const saving = ref(false)
const live = ref(false)
const publishableKey = ref('')

const showAddPkg = ref(false)
const showCustom = ref(false)
const customText = ref('')
const packages = ref<PartyPackageDetail[]>([])
const pkgSel = ref<string | null>(null)
const slotSel = ref<string | null>(null)
const slotChoices = ref<{ label: string; value: string }[]>([])
const slotsLoading = ref(false)
const noSlotsForPackage = computed(
  () => !!pkgSel.value && !slotsLoading.value && slotChoices.value.length === 0,
)
const deadlineInput = ref('')
const favouriteId = ref<string | null>(null)
const depositPending = ref(false)
const confirmOptionId = ref<string | null>(null)
const confirmHeadcount = ref<number | null>(null)

const returnUrl = computed(() => `${window.location.origin}/parties/plans/${props.id}`)
const liveOptions = computed(() => plan.value?.options.filter((o) => !o.voided) ?? [])
const hasCustom = computed(() => liveOptions.value.some((o) => o.kind === 'custom'))
const canOpen = computed(
  () =>
    liveOptions.value.length >= 2 &&
    liveOptions.value.some((o) => o.kind === 'package') &&
    !!plan.value?.deadline_at,
)
const bookableOptions = computed(() =>
  liveOptions.value.filter((o) => o.kind === 'package' && o.available),
)
const packageOptionChoices = computed(() =>
  bookableOptions.value.map((o) => ({ label: optionTitle(o), value: o.id })),
)
const winner = computed(() =>
  plan.value?.options.find((o) => o.id === plan.value?.winning_option_id),
)
const shareUrl = computed(() =>
  plan.value?.share_token
    ? `${window.location.origin}/parties/plan/${plan.value.share_token}`
    : '',
)
const packageChoices = computed(() =>
  packages.value.map((p) => ({ label: `${p.name} — ${p.organisation_name}`, value: p.id })),
)

const STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: 'Draft', color: 'grey-6' },
  open: { label: 'Voting open', color: 'primary' },
  resolved: { label: 'Ready to book', color: 'deep-orange' },
  booked: { label: 'Booked', color: 'positive' },
  expired_unbooked: { label: 'Closed', color: 'grey-5' },
}
const statusLabel = computed(() => STATUS[plan.value?.status ?? '']?.label ?? '')
const statusColor = computed(() => STATUS[plan.value?.status ?? '']?.color ?? 'grey')

// Host readiness — REAL counts only (INV-12), never fabricated.
const readiness = computed(() => {
  const p = plan.value
  if (!p) return { pct: 0, steps: [] as { label: string; done: boolean }[] }
  const approved = p.invites.filter((i) => i.status === 'approved')
  const votes = liveOptions.value.reduce((n, o) => n + o.votes, 0)
  const steps = [
    { label: 'Options added', done: liveOptions.value.length >= 2 },
    { label: 'Voting open', done: !!p.share_token },
    { label: 'First guest RSVP’d', done: approved.length >= 1 },
    { label: 'First vote cast', done: votes >= 1 },
  ]
  return { pct: steps.filter((s) => s.done).length / steps.length, steps }
})

function optionTitle(o: PlanOptionView): string {
  return o.kind === 'custom' ? o.custom_text || 'Custom' : o.package_name || 'Party'
}
function optionSub(o: PlanOptionView): string {
  if (o.kind === 'custom') return 'Custom idea (not bookable here)'
  const price = o.per_head_price_cents ? `${money(o.per_head_price_cents)}/head · ` : ''
  const when = o.starts_at && o.ends_at ? `${dayLabel(o.starts_at)} ${timeRange(o.starts_at, o.ends_at)}` : ''
  const avail = o.available === false ? ' · sold out' : ''
  return `${price}${o.venue_name ?? ''} · ${when}${avail}`
}
function voteFraction(o: PlanOptionView): number {
  const total = liveOptions.value.reduce((n, x) => n + x.votes, 0)
  return total > 0 ? o.votes / total : 0
}

async function reload(): Promise<void> {
  plan.value = await api.partyPlanner.getPlan(props.id)
  favouriteId.value = plan.value.ranking[0] ?? null
  if (plan.value.deadline_at && !deadlineInput.value) {
    deadlineInput.value = plan.value.deadline_at.slice(0, 16)
  }
  if (plan.value.status === 'resolved') {
    confirmOptionId.value = plan.value.winning_option_id ?? bookableOptions.value[0]?.id ?? null
    confirmHeadcount.value = plan.value.rsvp_yes_headcount || null
  }
}

function openAddPackage(): void {
  pkgSel.value = null
  slotSel.value = null
  slotChoices.value = []
  showAddPkg.value = true
}

async function loadSlots(packageId: string): Promise<void> {
  slotSel.value = null
  slotChoices.value = []
  slotsLoading.value = true
  try {
    const slots = await api.parties.slots(packageId)
    slotChoices.value = slots.map((s) => ({
      label: `${dayLabel(s.starts_at)} · ${timeRange(s.starts_at, s.ends_at)}`,
      value: s.id,
    }))
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    slotsLoading.value = false
  }
}

async function guard(fn: () => Promise<PlanView>): Promise<void> {
  saving.value = true
  try {
    plan.value = await fn()
    favouriteId.value = plan.value.ranking[0] ?? favouriteId.value
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

async function addPackage(): Promise<void> {
  if (!pkgSel.value || !slotSel.value) return
  await guard(() => api.partyPlanner.addPackageOption(props.id, pkgSel.value!, slotSel.value!))
  showAddPkg.value = false
}
async function addCustom(): Promise<void> {
  await guard(() => api.partyPlanner.addCustomOption(props.id, customText.value.trim()))
  customText.value = ''
  showCustom.value = false
}
async function removeOption(optionId: string): Promise<void> {
  await guard(() => api.partyPlanner.removeOption(props.id, optionId))
}
async function saveFavourite(fav: string | null): Promise<void> {
  if (!fav) return
  const ordered = [fav, ...liveOptions.value.map((o) => o.id).filter((i) => i !== fav)]
  await guard(() => api.partyPlanner.setRanking(props.id, ordered))
}
async function saveDeadline(): Promise<void> {
  await guard(() => api.partyPlanner.setDeadline(props.id, new Date(deadlineInput.value).toISOString()))
}
async function setTheme(themeKey: string): Promise<void> {
  await guard(() => api.partyPlanner.setTheme(props.id, themeKey))
}
async function openVoting(): Promise<void> {
  await guard(() => api.partyPlanner.openPlan(props.id))
}
async function extend(): Promise<void> {
  await guard(() => api.partyPlanner.extend(props.id))
}
async function setInvite(inviteId: string, action: 'approve' | 'remove' | 'block'): Promise<void> {
  await guard(() => api.partyPlanner.setInvite(props.id, inviteId, action))
}

async function copyShare(): Promise<void> {
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    $q.notify({ type: 'positive', message: 'Link copied' })
  } catch {
    $q.notify({ type: 'info', message: shareUrl.value })
  }
}

async function confirm(): Promise<void> {
  if (!confirmOptionId.value) return
  saving.value = true
  try {
    plan.value = await api.partyPlanner.confirm(props.id, {
      option_id: confirmOptionId.value,
      headcount: confirmHeadcount.value ?? undefined,
    })
    depositPending.value = true
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

async function payDepositDev(): Promise<void> {
  if (!plan.value?.booking_id) return
  saving.value = true
  try {
    await api.parties.devConfirm(plan.value.booking_id)
    depositPending.value = false
    await reload()
    $q.notify({ type: 'positive', message: 'Deposit paid — party booked 🎉' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}
async function onDepositPaid(): Promise<void> {
  depositPending.value = false
  await reload()
  $q.notify({ type: 'positive', message: 'Deposit paid — party booked 🎉' })
}
function onDepositFailed(msg: string): void {
  $q.notify({ type: 'negative', message: msg })
}

onMounted(async () => {
  try {
    const cfg = await api.payments.config()
    live.value = cfg.live && !!cfg.publishable_key
    publishableKey.value = cfg.publishable_key ?? ''
  } catch {
    live.value = false
  }
  try {
    packages.value = await api.parties.allPackages()
    await reload()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-optrow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--jg-line);
}
.jg-optrow:last-child {
  border-bottom: none;
}
</style>
