<template>
  <q-page class="jg-page" style="max-width: 560px" :style="themeStyle">
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
        <div class="jg-party-hero__emoji">{{ theme.emoji }}</div>
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

      <!-- One page: enter your details, then tap a party to vote (no approval, no second step) -->
      <template v-else>
        <!-- Identity: collected once; a first vote tap submits it. After that, a compact summary. -->
        <section class="jg-card q-pa-lg q-mb-md">
          <template v-if="!inviteToken">
            <div class="text-weight-600 q-mb-xs">Your details</div>
            <div class="jg-faint text-caption q-mb-md">
              No account needed — add your name and email, then tap your favourite party below to vote.
            </div>
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
          </template>
          <div v-else class="row items-center q-gutter-md">
            <q-avatar color="grey-2" size="44px" style="font-size: 24px">
              {{ avatarEmoji(form.avatar_key) }}
            </q-avatar>
            <div class="col">
              <div class="text-weight-600">You're in{{ form.nickname ? `, ${form.nickname}` : '' }}! 🎉</div>
              <div class="jg-faint text-caption">Tap a party below to cast or change your vote.</div>
            </div>
          </div>
        </section>

        <section class="jg-card q-pa-lg q-mb-md">
          <div class="row items-center justify-between q-mb-sm">
            <div class="text-weight-600">Vote for the party</div>
            <span class="jg-faint text-caption">{{ countdown }}</span>
          </div>
          <div v-for="o in liveOptions" :key="o.id"
               class="jg-vote" :class="{ 'jg-vote--mine': o.id === myVote }"
               data-testid="vote-option">
            <div class="jg-vote__main" @click="voteOrRsvp(o.id, $event)">
              <div class="col">
                <div class="text-weight-500">
                  {{ optionTitle(o) }}
                  <q-badge v-if="o.is_favourite" color="amber-8" class="q-ml-xs">
                    ⭐ Birthday kid's pick
                  </q-badge>
                </div>
                <div class="jg-faint text-caption">{{ optionSub(o) }}</div>
                <q-linear-progress :value="voteFraction(o)" color="deep-purple-5"
                                   track-color="grey-3" size="7px" rounded class="q-mt-xs jg-bar" />
              </div>
              <div class="text-center q-ml-sm">
                <div class="text-weight-700 text-h6">{{ o.votes }}</div>
                <q-icon v-if="o.id === myVote" name="check_circle" color="positive" size="18px" />
              </div>
            </div>
            <div class="jg-reacts">
              <button v-for="e in REACTIONS" :key="e" type="button" class="jg-react"
                      :class="{ 'jg-react--on': myReactions.has(reactionKey(o.id, e)) }"
                      :disabled="!canVote" @click.stop="react(o.id, e)">
                {{ e }}<span v-if="o.reactions[e]" class="jg-react__n">{{ o.reactions[e] }}</span>
              </button>
            </div>
          </div>
          <div v-if="!inviteToken" class="jg-faint text-caption q-mt-sm">
            Add your name and email above, then tap a party to vote.
          </div>
        </section>

        <section class="jg-card q-pa-md q-mb-md">
          <div class="text-weight-600 q-mb-xs">Who's coming ({{ view.rsvp_count }})</div>
          <div class="row q-gutter-md">
            <div v-for="(b, i) in view.board" :key="i" class="text-center" style="width: 56px">
              <q-avatar color="grey-2" size="40px" style="font-size: 22px">
                {{ avatarEmoji(b.avatar_key) }}
              </q-avatar>
              <div v-if="b.nickname" class="jg-faint text-caption ellipsis">{{ b.nickname }}</div>
            </div>
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
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { confettiBurst } from '@/lib/confetti'
import { dayLabel, money, timeRange } from '@/lib/format'
import { useHead } from '@/lib/head'
import { planTheme } from '@/lib/planTheme'
import type { InviteSelfView, PlanOptionView, PublicPlanView } from '@/lib/types'

const props = defineProps<{ token: string }>()
const $q = useQuasar()
const route = useRoute()

// Private invite page — keep it out of search indexes (INV-13).
useHead(() => ({ title: "You're invited! · Juggle party vote", noindex: true }))

const REACTIONS = ['❤️', '🎉', '🔥', '😍', '👍', '🤩']
const theme = computed(() => planTheme(view.value?.theme))
const themeStyle = computed(() => theme.value.vars)
const myReactions = ref<Set<string>>(new Set())
const nowMs = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | undefined

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
  const ms = new Date(view.value.deadline_at).getTime() - nowMs.value
  if (ms <= 0) return 'Voting closed'
  const s = Math.floor(ms / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (d > 0) return `${d}d ${h}h left`
  if (h > 0) return `${h}h ${m}m left`
  return `${m}m ${String(sec).padStart(2, '0')}s left`
})
const reactionKey = (optionId: string, emoji: string): string => `${optionId}:${emoji}`

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

async function submitRsvp(): Promise<boolean> {
  if (!form.value.parent_name || !form.value.email) {
    $q.notify({ type: 'warning', message: 'Add your name and email to vote' })
    return false
  }
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
    return true
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not RSVP') })
    return false
  } finally {
    saving.value = false
  }
}

// One-step RSVP-and-vote: a first tap on a party auto-creates the RSVP (name + email required)
// then records the vote — no host approval, no separate submit step.
async function voteOrRsvp(optionId: string, event?: MouseEvent): Promise<void> {
  if (view.value?.status !== 'open' || saving.value) return
  if (!inviteToken.value && !(await submitRsvp())) return
  await vote(optionId, event)
}

async function vote(optionId: string, event?: MouseEvent): Promise<void> {
  if (!canVote.value || !inviteToken.value) return
  try {
    mine.value = await api.partyPlanner.vote(inviteToken.value, optionId)
    view.value = mine.value.plan
    myVote.value = optionId
    localStorage.setItem(VOTE_KEY.value, optionId)
    if (event) confettiBurst(event.clientX, event.clientY)
    $q.notify({ type: 'positive', message: 'Vote counted ✓' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not record your vote') })
  }
}

const REACT_KEY = computed(() => `juggle.plan.reacts.${props.token}`)

async function react(optionId: string, emoji: string): Promise<void> {
  if (!canVote.value || !inviteToken.value) return
  const key = reactionKey(optionId, emoji)
  try {
    mine.value = await api.partyPlanner.react(inviteToken.value, optionId, emoji)
    view.value = mine.value.plan
    if (myReactions.value.has(key)) myReactions.value.delete(key)
    else myReactions.value.add(key)
    localStorage.setItem(REACT_KEY.value, JSON.stringify([...myReactions.value]))
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not react') })
  }
}

onMounted(async () => {
  // An emailed invite link carries ?invite=<token> so the guest lands pre-recognised.
  const fromLink = typeof route.query.invite === 'string' ? route.query.invite : null
  if (fromLink) localStorage.setItem(INVITE_KEY.value, fromLink)
  inviteToken.value = fromLink ?? localStorage.getItem(INVITE_KEY.value)
  myVote.value = localStorage.getItem(VOTE_KEY.value)
  try {
    myReactions.value = new Set(JSON.parse(localStorage.getItem(REACT_KEY.value) ?? '[]'))
  } catch {
    myReactions.value = new Set()
  }
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
  ticker = setInterval(() => (nowMs.value = Date.now()), 1000)
})
onUnmounted(() => {
  clearInterval(poller)
  clearInterval(ticker)
})
</script>

<style scoped>
.jg-party-hero {
  text-align: center;
  padding: 24px 20px;
  background: linear-gradient(120% 140% at 15% 0%, var(--pt-from, #fff4e6) 0%, var(--pt-to, #ffe9f2) 100%);
  border-radius: 18px;
}
.jg-party-hero__emoji { font-size: 46px; animation: jg-bob 2.4s ease-in-out infinite; }
.jg-party-hero__title { font-size: 28px; margin: 4px 0; }
.jg-party-hero__sub { color: var(--jg-ink-soft); margin: 0; }
@keyframes jg-bob {
  0%, 100% { transform: translateY(0) rotate(-3deg); }
  50% { transform: translateY(-6px) rotate(3deg); }
}
.jg-vote {
  border: 1px solid var(--jg-line);
  border-radius: 14px;
  margin-bottom: 10px;
  transition: border-color 120ms ease, background 120ms ease, box-shadow 120ms ease;
}
.jg-vote__main { display: flex; align-items: center; gap: 10px; padding: 12px; cursor: pointer; }
.jg-vote:hover { border-color: var(--pt-accent, var(--jg-primary)); }
.jg-vote--mine {
  border-color: var(--pt-accent, var(--jg-primary));
  background: color-mix(in srgb, var(--pt-accent, #7b1fa2) 8%, transparent);
  box-shadow: 0 2px 12px color-mix(in srgb, var(--pt-accent, #7b1fa2) 18%, transparent);
}
.jg-bar :deep(.q-linear-progress__model) { transition: width 500ms cubic-bezier(.2,.7,.3,1); }
.jg-reacts { display: flex; gap: 6px; padding: 0 12px 10px; flex-wrap: wrap; }
.jg-react {
  border: 1px solid var(--jg-line);
  background: #fff;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 15px;
  cursor: pointer;
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}
.jg-react:hover:not(:disabled) { transform: scale(1.15); }
.jg-react:disabled { opacity: 0.45; cursor: default; }
.jg-react--on { border-color: var(--pt-accent, var(--jg-primary)); background: color-mix(in srgb, var(--pt-accent, #7b1fa2) 12%, #fff); }
.jg-react__n { font-size: 12px; font-weight: 600; margin-left: 3px; color: var(--jg-ink-soft); }
.jg-hp { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
</style>
