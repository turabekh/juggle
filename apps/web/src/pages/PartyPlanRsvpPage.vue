<template>
  <q-page class="jg-page" style="max-width: 560px">
    <div v-if="loading" class="jg-card q-pa-lg row items-center q-gutter-md">
      <q-spinner color="primary" size="24px" /><span>Loading the party…</span>
    </div>

    <EmptyState
      v-else-if="!view"
      icon="celebration"
      title="Party not found"
      subtitle="This invite link may have expired."
    >
      <q-btn unelevated color="primary" no-caps label="Explore parties" :to="{ name: 'parties' }" />
    </EmptyState>

    <template v-else>
      <div class="jg-party-hero q-mb-lg">
        <div class="jg-party-hero__emoji">🎉</div>
        <h1 class="jg-party-hero__title">You're invited!</h1>
        <p class="jg-party-hero__sub">Help pick the party — vote for your favourite below.</p>
      </div>

      <!-- Reveal (resolved) -->
      <section v-if="view.status !== 'open'" class="jg-card q-pa-lg q-mb-md text-center">
        <template v-if="view.is_tie">
          <div class="text-h5 q-mb-xs">It's a tie! 🤝</div>
          <div class="jg-muted">The host is choosing the final party.</div>
        </template>
        <template v-else-if="winner">
          <div class="text-h5 q-mb-xs">🎊 The winner is</div>
          <div class="text-h6 text-weight-700">{{ optionTitle(winner) }}</div>
          <div v-if="winner.starts_at" class="jg-muted q-mt-xs">
            {{ dayLabel(winner.starts_at) }} · {{ winner.venue_name }}
          </div>
        </template>
        <template v-else>
          <div class="text-h6">Voting has closed</div>
        </template>
        <q-btn class="q-mt-md" unelevated color="primary" no-caps
               label="Plan your own party 🎈" :to="{ name: 'parties', query: { from: 'party-vote' } }" />
      </section>

      <!-- RSVP gate: no identity yet -->
      <section v-else-if="!inviteToken" class="jg-card q-pa-lg q-mb-md">
        <div class="text-weight-600 q-mb-md">RSVP to vote</div>
        <q-input v-model="form.parent_name" outlined dense label="Your name" class="q-mb-sm"
                 data-testid="rsvp-name" />
        <q-input v-model="form.email" outlined dense type="email" label="Email" class="q-mb-sm"
                 data-testid="rsvp-email" />
        <q-input v-model.number="form.kid_count" outlined dense type="number" min="0" max="50"
                 label="How many kids are you bringing?" class="q-mb-sm" style="max-width: 260px"
                 data-testid="rsvp-kids" />
        <q-input v-model="form.nickname" outlined dense label="Display name (optional)"
                 hint="Shown on the guest board — no kids' names please" class="q-mb-sm" maxlength="80" />
        <div class="q-mb-sm">
          <div class="jg-faint text-caption q-mb-xs">Pick an avatar</div>
          <div class="row q-gutter-xs">
            <q-btn v-for="a in AVATARS" :key="a.key" round dense
                   :color="form.avatar_key === a.key ? 'primary' : 'grey-3'"
                   :text-color="form.avatar_key === a.key ? 'white' : 'dark'"
                   :label="a.emoji" @click="form.avatar_key = a.key" />
          </div>
        </div>
        <q-input v-model="form.website" class="jg-hp" tabindex="-1" autocomplete="off"
                 aria-hidden="true" label="Leave blank" />
        <q-toggle v-model="form.marketing_opt_in" color="primary" class="q-mt-sm"
                  label="Email me great kids' activities (optional)" />
        <q-btn class="full-width q-mt-md" unelevated color="primary" no-caps size="lg"
               :loading="saving" :disable="!form.parent_name || !form.email"
               label="RSVP &amp; vote" data-testid="rsvp-submit" @click="submitRsvp" />
      </section>

      <!-- Voting -->
      <template v-else>
        <q-banner v-if="mine?.status === 'pending'" dense class="bg-amber-1 text-amber-9 q-mb-md">
          Thanks for your RSVP! The host will approve you shortly — then you can vote.
        </q-banner>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="row items-center justify-between q-mb-sm">
            <div class="text-weight-600">Vote for the party</div>
            <span class="jg-faint text-caption">{{ countdown }}</span>
          </div>
          <div v-for="o in liveOptions" :key="o.id"
               class="jg-vote" :class="{ 'jg-vote--mine': o.id === myVote }"
               data-testid="vote-option" @click="vote(o.id)">
            <div class="col">
              <div class="text-weight-500">
                {{ optionTitle(o) }}
                <q-icon v-if="o.is_favourite" name="star" color="amber" size="14px" />
              </div>
              <div class="jg-faint text-caption">{{ optionSub(o) }}</div>
              <q-linear-progress :value="voteFraction(o)" color="primary" track-color="grey-3"
                                 size="6px" rounded class="q-mt-xs" />
            </div>
            <div class="text-center q-ml-sm">
              <div class="text-weight-700">{{ o.votes }}</div>
              <q-icon v-if="o.id === myVote" name="check_circle" color="positive" size="18px" />
            </div>
          </div>
          <div v-if="!canVote" class="jg-faint text-caption q-mt-sm">
            {{ mine?.status === 'pending' ? 'Voting unlocks once the host approves you.'
               : 'Voting is closed.' }}
          </div>
        </section>

        <section class="jg-card q-pa-md q-mb-md">
          <div class="text-weight-600 q-mb-xs">Who's coming ({{ view.rsvp_count }})</div>
          <div class="row q-gutter-xs">
            <q-avatar v-for="(b, i) in view.board" :key="i" color="grey-3" size="34px">
              {{ avatarEmoji(b.avatar_key) }}
            </q-avatar>
            <span v-if="!view.board.length" class="jg-muted text-caption">Be the first!</span>
          </div>
        </section>

        <div class="text-center">
          <q-btn flat no-caps color="primary" label="Plan your own party 🎈"
                 :to="{ name: 'parties', query: { from: 'party-vote' } }" />
        </div>
      </template>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { dayLabel, money, timeRange } from '@/lib/format'
import { useHead } from '@/lib/head'
import type { InviteSelfView, PlanOptionView, PublicPlanView } from '@/lib/types'

const props = defineProps<{ token: string }>()
const $q = useQuasar()

// Private invite page — keep it out of search indexes (INV-13).
useHead(() => ({ title: "You're invited! · Juggle party vote", noindex: true }))

const AVATARS = [
  { key: 'dino', emoji: '🦖' }, { key: 'rocket', emoji: '🚀' }, { key: 'unicorn', emoji: '🦄' },
  { key: 'star', emoji: '⭐' }, { key: 'cat', emoji: '🐱' }, { key: 'dog', emoji: '🐶' },
  { key: 'robot', emoji: '🤖' }, { key: 'fox', emoji: '🦊' }, { key: 'panda', emoji: '🐼' },
  { key: 'owl', emoji: '🦉' }, { key: 'dragon', emoji: '🐲' }, { key: 'balloon', emoji: '🎈' },
]
const avatarEmoji = (key: string | null): string =>
  AVATARS.find((a) => a.key === key)?.emoji ?? '🎈'

const loading = ref(true)
const saving = ref(false)
const view = ref<PublicPlanView | null>(null)
const mine = ref<InviteSelfView | null>(null)
const inviteToken = ref<string | null>(null)
const myVote = ref<string | null>(null)  // client-only memory; the server never reveals the choice
let poller: ReturnType<typeof setInterval> | undefined

const form = ref({
  parent_name: '', email: '', attending: true, kid_count: 1,
  nickname: '', avatar_key: 'balloon', marketing_opt_in: false, website: '',
})

const INVITE_KEY = computed(() => `juggle.plan.invite.${props.token}`)
const VOTE_KEY = computed(() => `juggle.plan.vote.${props.token}`)

const liveOptions = computed(() => view.value?.options.filter((o) => !o.voided) ?? [])
const winner = computed(() =>
  view.value?.options.find((o) => o.id === view.value?.winner_option_id),
)
const canVote = computed(() => view.value?.is_open && mine.value?.status === 'approved')
const countdown = computed(() => {
  if (!view.value?.deadline_at) return ''
  const ms = new Date(view.value.deadline_at).getTime() - Date.now()
  if (ms <= 0) return 'Voting closed'
  const h = Math.floor(ms / 3_600_000)
  return h >= 24 ? `${Math.floor(h / 24)} days left` : `${h}h left`
})

function optionTitle(o: PlanOptionView): string {
  return o.kind === 'custom' ? o.custom_text || 'Custom' : o.package_name || 'Party'
}
function optionSub(o: PlanOptionView): string {
  if (o.kind === 'custom') return 'A custom idea'
  const when = o.starts_at && o.ends_at ? `${dayLabel(o.starts_at)} · ${timeRange(o.starts_at, o.ends_at)}` : ''
  const price = o.per_head_price_cents ? ` · ${money(o.per_head_price_cents)}/head` : ''
  return `${when}${price}${o.available === false ? ' · sold out' : ''}`
}
function voteFraction(o: PlanOptionView): number {
  const total = liveOptions.value.reduce((n, x) => n + x.votes, 0)
  return total > 0 ? o.votes / total : 0
}

async function refresh(): Promise<void> {
  if (inviteToken.value) {
    try {
      mine.value = await api.partyPlanner.inviteSelf(inviteToken.value)
      view.value = mine.value.plan
      return
    } catch {
      inviteToken.value = null // token invalid → fall back to public view
    }
  }
  view.value = await api.partyPlanner.publicPlan(props.token)
}

async function submitRsvp(): Promise<void> {
  saving.value = true
  try {
    const res = await api.partyPlanner.openRsvp(props.token, {
      parent_name: form.value.parent_name,
      email: form.value.email,
      attending: form.value.attending,
      kid_count: form.value.kid_count,
      nickname: form.value.nickname || null,
      avatar_key: form.value.avatar_key,
      marketing_opt_in: form.value.marketing_opt_in,
    })
    inviteToken.value = res.invite_token
    localStorage.setItem(INVITE_KEY.value, res.invite_token)
    await refresh()
    $q.notify({ type: 'positive', message: 'RSVP received — now cast your vote!' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not RSVP') })
  } finally {
    saving.value = false
  }
}

async function vote(optionId: string): Promise<void> {
  if (!canVote.value || !inviteToken.value) return
  try {
    mine.value = await api.partyPlanner.vote(inviteToken.value, optionId)
    view.value = mine.value.plan
    myVote.value = optionId
    localStorage.setItem(VOTE_KEY.value, optionId)
    $q.notify({ type: 'positive', message: 'Vote counted ✓' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not record your vote') })
  }
}

onMounted(async () => {
  inviteToken.value = localStorage.getItem(INVITE_KEY.value)
  myVote.value = localStorage.getItem(VOTE_KEY.value)
  try {
    await refresh()
  } catch {
    view.value = null
  } finally {
    loading.value = false
  }
  poller = setInterval(() => {
    if (view.value?.is_open) void refresh()
  }, 10_000)
})
onUnmounted(() => clearInterval(poller))
</script>

<style scoped>
.jg-party-hero {
  text-align: center;
  padding: 20px;
  background: linear-gradient(120% 140% at 15% 0%, #fff4e6 0%, #ffe9f2 100%);
  border-radius: 18px;
}
.jg-party-hero__emoji { font-size: 40px; }
.jg-party-hero__title { font-size: 28px; margin: 4px 0; }
.jg-party-hero__sub { color: var(--jg-ink-soft); margin: 0; }
.jg-vote {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--jg-line);
  border-radius: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 120ms ease, background 120ms ease;
}
.jg-vote:hover { border-color: var(--jg-primary); }
.jg-vote--mine { border-color: var(--jg-primary); background: rgba(25, 118, 210, 0.06); }
.jg-hp { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
</style>
