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

      <!-- Compliance & verification -->
      <section class="jg-card q-pa-lg q-mt-lg">
        <div class="text-h6 q-mb-xs">Compliance &amp; verification</div>
        <p class="jg-muted text-caption q-mb-md">
          Required for parent trust. Our team verifies these before you go live.
        </p>

        <div class="jg-comp-abn">
          <q-input v-model="abnDraft" outlined dense label="ABN" style="max-width: 260px" />
          <q-btn unelevated no-caps color="primary" label="Save ABN" :disable="abnDraft === (org.abn ?? '')" :loading="savingAbn" @click="saveAbn" />
        </div>

        <div class="row q-col-gutter-lg q-mt-md">
          <div class="col-12 col-sm-6">
            <div class="row items-center justify-between q-mb-xs">
              <span class="text-weight-600">Working with Children (WWCC)</span>
              <q-btn flat dense no-caps color="primary" icon="add" label="Add" @click="showWwcc = true" />
            </div>
            <div v-if="wwcc.length" class="jg-vlist">
              <div v-for="w in wwcc" :key="w.id" class="jg-vrow">
                <div>
                  <div class="text-weight-500">{{ w.staff_name }}</div>
                  <div class="jg-faint text-caption">
                  {{ w.wwcc_number }} · exp {{ w.expiry_date }}
                  <span v-if="expiryWarn(w.expiry_date)" :class="expiryWarn(w.expiry_date)!.cls">
                    · {{ expiryWarn(w.expiry_date)!.text }}
                  </span>
                </div>
                </div>
                <q-chip dense square :color="vColor(w.status)" text-color="white" :label="w.status" />
              </div>
            </div>
            <div v-else class="jg-faint text-caption">No staff checks added.</div>
          </div>

          <div class="col-12 col-sm-6">
            <div class="row items-center justify-between q-mb-xs">
              <span class="text-weight-600">Public liability insurance</span>
              <q-btn flat dense no-caps color="primary" icon="add" label="Add" @click="showInsurance = true" />
            </div>
            <div v-if="insurance.length" class="jg-vlist">
              <div v-for="d in insurance" :key="d.id" class="jg-vrow">
                <div>
                  <div class="text-weight-500 ellipsis" style="max-width: 220px">{{ d.file_ref }}</div>
                  <div class="jg-faint text-caption">
                    {{ d.expiry_date ? `exp ${d.expiry_date}` : 'no expiry' }}
                    <span v-if="expiryWarn(d.expiry_date)" :class="expiryWarn(d.expiry_date)!.cls">
                      · {{ expiryWarn(d.expiry_date)!.text }}
                    </span>
                  </div>
                </div>
                <q-chip dense square :color="vColor(d.status)" text-color="white" :label="d.status" />
              </div>
            </div>
            <div v-else class="jg-faint text-caption">No certificate added.</div>
          </div>
        </div>
      </section>

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

      <!-- Earnings -->
      <section class="q-mt-xl">
        <div class="row items-center justify-between q-mb-sm">
          <h2 class="text-h6 q-my-none">Earnings</h2>
          <span v-if="scheduledTotal > 0" class="jg-pill">{{ money(scheduledTotal) }} upcoming</span>
        </div>

        <!-- Stripe Connect payouts setup (PRD §8.4 · F-PAY-1) -->
        <div class="jg-card q-pa-md q-mb-md">
          <div class="row items-center justify-between q-col-gutter-sm">
            <div class="col">
              <div class="row items-center q-gutter-sm">
                <span class="text-weight-600">Stripe payouts</span>
                <q-chip
                  v-if="connect" dense square :color="connectDisplay.color"
                  text-color="white" :label="connectDisplay.label"
                />
              </div>
              <div class="jg-faint text-caption q-mt-xs">{{ connectDisplay.hint }}</div>
            </div>
            <q-btn
              v-if="connectDisplay.needsSetup"
              unelevated no-caps color="primary"
              :label="connectDisplay.ctaLabel"
              :loading="connecting" @click="startConnect"
            />
          </div>
        </div>

        <div v-if="payouts.length" class="jg-list">
          <div v-for="p in payouts" :key="p.id" class="jg-card jg-listrow">
            <div>
              <div class="text-weight-600">{{ money(p.amount_cents) }}</div>
              <div class="jg-faint text-caption">
                {{ p.status === 'paid' ? 'Paid' : p.scheduled_for ? `Due ${dayLabel(p.scheduled_for)}` : 'Scheduled' }}
              </div>
            </div>
            <q-chip dense square :color="payoutColor(p.status)" text-color="white" :label="p.status" />
          </div>
        </div>
        <div v-else class="jg-muted text-caption">
          Earnings appear here after families book. You're paid a few days after each session.
        </div>
      </section>

      <!-- Tax invoices (PRD §8.4 · F-PAY-6) -->
      <section v-if="orders.length" class="q-mt-xl">
        <h2 class="text-h6 q-mb-sm">Tax invoices</h2>
        <div class="jg-list">
          <button
            v-for="o in orders"
            :key="o.payment_id"
            type="button"
            class="jg-card jg-card--hover jg-listrow jg-invrow"
            @click="openInvoice(o.payment_id)"
          >
            <div>
              <div class="text-weight-600">
                {{ money(o.commission_cents + o.commission_gst_cents) }} commission + GST
              </div>
              <div class="jg-faint text-caption">
                {{ dayLabel(o.ordered_at) }} ·
                {{ o.session_count }} {{ o.session_count === 1 ? 'session' : 'sessions' }} ·
                {{ money(o.gross_cents) }} gross
              </div>
            </div>
            <q-icon name="receipt_long" color="grey-6" />
          </button>
        </div>
      </section>

      <!-- Insights (PRD §8.6) -->
      <section v-if="analytics" class="q-mt-xl">
        <h2 class="text-h6 q-mb-sm">Insights</h2>
        <div class="jg-stats">
          <div class="jg-card jg-stat">
            <div class="jg-stat__num">{{ (analytics.fill_rate * 100).toFixed(0) }}%</div>
            <div class="jg-stat__label">Seats filled</div>
            <div class="jg-faint text-caption">
              {{ analytics.booked_total }}/{{ analytics.capacity_total }} seats
            </div>
          </div>
          <div class="jg-card jg-stat">
            <div class="jg-stat__num">{{ money(analytics.revenue_cents) }}</div>
            <div class="jg-stat__label">Bookings revenue</div>
            <div class="jg-faint text-caption">
              {{ analytics.bookings }} {{ analytics.bookings === 1 ? 'booking' : 'bookings' }}
            </div>
          </div>
          <div class="jg-card jg-stat">
            <div class="jg-stat__num">{{ analytics.families.total }}</div>
            <div class="jg-stat__label">Families</div>
            <div class="jg-faint text-caption">
              {{ analytics.families.returning }} returning · {{ analytics.families.new }} new
            </div>
          </div>
        </div>

        <div v-if="analytics.programs.length" class="jg-list q-mt-md">
          <div v-for="p in analytics.programs" :key="p.program_id" class="jg-card jg-listrow">
            <div>
              <div class="text-weight-600">{{ p.title }}</div>
              <div class="jg-faint text-caption">
                {{ p.booked_total }}/{{ p.capacity_total }} seats ·
                {{ (p.fill_rate * 100).toFixed(0) }}% full
              </div>
            </div>
            <div class="text-weight-600">{{ money(p.revenue_cents) }}</div>
          </div>
        </div>
      </section>

      <!-- Reviews (PRD §7.6) -->
      <section class="q-mt-xl">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <h2 class="text-h6 q-my-none">Reviews</h2>
          <template v-if="reviews.length">
            <StarRating :model-value="Math.round(avgRating)" size="17px" />
            <span class="text-weight-600">{{ avgRating.toFixed(1) }}</span>
            <span class="jg-faint text-caption">· {{ reviews.length }}</span>
          </template>
        </div>
        <div v-if="reviews.length" class="jg-list">
          <article v-for="r in reviews" :key="r.id" class="jg-card q-pa-md">
            <div class="row items-center q-gutter-sm">
              <StarRating :model-value="r.rating" size="15px" />
              <span class="text-weight-600">{{ r.author_label }}</span>
              <span class="jg-faint text-caption">· {{ r.program_title }} · {{ dayLabel(r.created_at) }}</span>
            </div>
            <p class="q-mt-sm q-mb-none" style="white-space: pre-line">{{ r.body }}</p>
            <div v-if="r.provider_reply" class="jg-review__reply">
              <div class="jg-faint text-caption text-weight-600">Your reply</div>
              <p class="q-mt-xs q-mb-none" style="white-space: pre-line">{{ r.provider_reply }}</p>
            </div>
            <q-btn
              v-else flat dense no-caps size="sm" color="primary" icon="reply"
              label="Reply" class="q-mt-sm" @click="openReply(r.id)"
            />
          </article>
        </div>
        <div v-else class="jg-muted text-caption">
          Reviews from families appear here once they've attended and a moderator approves them.
        </div>
      </section>

      <!-- Questions (PRD §7.2) -->
      <section class="q-mt-xl">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <h2 class="text-h6 q-my-none">Questions</h2>
          <q-badge v-if="unansweredCount" color="warning" :label="`${unansweredCount} to answer`" />
        </div>
        <div v-if="questions.length" class="jg-list">
          <article v-for="q in questions" :key="q.id" class="jg-card q-pa-md">
            <div class="text-weight-600">{{ q.body }}</div>
            <div class="jg-faint text-caption">asked by {{ q.asker_label }}</div>
            <div v-if="q.answer" class="jg-review__reply">
              <div class="jg-faint text-caption text-weight-600">Your answer</div>
              <p class="q-mt-xs q-mb-none" style="white-space: pre-line">{{ q.answer }}</p>
            </div>
            <q-btn
              v-else flat dense no-caps size="sm" color="primary" icon="reply"
              label="Answer" class="q-mt-sm" @click="openAnswer(q.id)"
            />
          </article>
        </div>
        <div v-else class="jg-muted text-caption">
          Parent questions on your listings show up here to answer.
        </div>
      </section>
    </template>

    <!-- Tax invoice detail -->
    <q-dialog v-model="showInvoice">
      <q-card style="min-width: 480px; max-width: 680px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Tax invoice</div>
          <div v-if="invoice" class="jg-faint text-caption">
            {{ invoice.invoice_number }} · issued {{ dayLabel(invoice.issued_at) }}
          </div>
        </q-card-section>
        <q-card-section v-if="invoice" class="q-pt-none">
          <div class="row justify-between q-mb-md">
            <div>
              <div class="jg-faint text-caption">From (supplier)</div>
              <div class="text-weight-600">{{ invoice.supplier.name }}</div>
              <div class="jg-faint text-caption">ABN {{ invoice.supplier.abn || '—' }}</div>
            </div>
            <div class="text-right">
              <div class="jg-faint text-caption">To</div>
              <div class="text-weight-600">{{ invoice.recipient.name }}</div>
              <div class="jg-faint text-caption">ABN {{ invoice.recipient.abn || '—' }}</div>
            </div>
          </div>
          <q-markup-table flat dense class="jg-inv">
            <thead>
              <tr>
                <th class="text-left">Session</th>
                <th class="text-right">Gross</th>
                <th class="text-right">Commission</th>
                <th class="text-right">GST</th>
                <th class="text-right">Net</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in invoice.lines" :key="l.session_id">
                <td class="text-left">
                  {{ l.session_title }}
                  <div class="jg-faint text-caption">{{ dayLabel(l.starts_at) }}</div>
                </td>
                <td class="text-right">{{ money(l.gross_cents) }}</td>
                <td class="text-right">{{ money(l.commission_cents) }}</td>
                <td class="text-right">{{ money(l.commission_gst_cents) }}</td>
                <td class="text-right">{{ money(l.net_cents) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="text-weight-700">
                <td class="text-left">Total</td>
                <td class="text-right">{{ money(invoice.totals.gross_cents) }}</td>
                <td class="text-right">{{ money(invoice.totals.commission_cents) }}</td>
                <td class="text-right">{{ money(invoice.totals.commission_gst_cents) }}</td>
                <td class="text-right">{{ money(invoice.totals.net_cents) }}</td>
              </tr>
            </tfoot>
          </q-markup-table>
          <p class="jg-faint text-caption q-mt-md q-mb-none">
            Issued by {{ invoice.supplier.name }} for the marketplace commission (a taxable
            supply). GST shown is on the commission only.
          </p>
        </q-card-section>
        <q-card-section v-else class="row justify-center q-py-lg">
          <q-spinner color="primary" size="24px" />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Close" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Answer a question dialog -->
    <q-dialog v-model="showAnswer">
      <q-card style="min-width: 400px; border-radius: 18px">
        <q-card-section><div class="text-h6">Answer this question</div></q-card-section>
        <q-card-section>
          <q-input
            v-model="answerForm.text" outlined type="textarea" autogrow autofocus
            label="Your answer" hint="Shown publicly on the listing."
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="Post answer"
            :loading="saving" :disable="!answerForm.text.trim()" @click="postAnswer"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Reply to review dialog -->
    <q-dialog v-model="showReply">
      <q-card style="min-width: 400px; border-radius: 18px">
        <q-card-section><div class="text-h6">Reply to review</div></q-card-section>
        <q-card-section>
          <q-input
            v-model="replyForm.text" outlined type="textarea" autogrow autofocus
            label="Your response" hint="Shown publicly beneath the review."
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="Post reply"
            :loading="saving" :disable="!replyForm.text.trim()" @click="postReply"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

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

    <!-- Add WWCC dialog -->
    <q-dialog v-model="showWwcc">
      <q-card style="min-width: 360px; border-radius: 18px">
        <q-card-section><div class="text-h6">Add WWCC record</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="wwccForm.staff_name" outlined dense label="Staff member name" autofocus />
          <q-input v-model="wwccForm.wwcc_number" outlined dense label="WWCC number" />
          <q-input v-model="wwccForm.expiry_date" outlined dense type="date" label="Expiry date" stack-label />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add" :loading="saving" :disable="!wwccValid" @click="addWwcc" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Add insurance dialog -->
    <q-dialog v-model="showInsurance">
      <q-card style="min-width: 360px; border-radius: 18px">
        <q-card-section><div class="text-h6">Add insurance certificate</div></q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="insForm.file_ref" outlined dense label="Certificate link / reference" autofocus hint="Paste a link to your certificate" />
          <q-input v-model="insForm.expiry_date" outlined dense type="date" label="Expiry date (optional)" stack-label />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Add" :loading="saving" :disable="!insForm.file_ref" @click="addInsurance" />
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
import { CATEGORIES, categoryMeta, dayLabel, money, payoutSetupDisplay } from '@/lib/format'
import type {
  ConnectStatus,
  InsuranceDoc,
  ProviderOrderSummary,
  TaxInvoice,
  ListingQuestion,
  Org,
  OrgAnalytics,
  Payout,
  Program,
  Review,
  Venue,
  WwccRecord,
} from '@/lib/types'

const props = defineProps<{ id: string }>()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()

const org = ref<Org | null>(null)
const connect = ref<ConnectStatus | null>(null)
const connecting = ref(false)
const venues = ref<Venue[]>([])
const programs = ref<Program[]>([])
const wwcc = ref<WwccRecord[]>([])
const insurance = ref<InsuranceDoc[]>([])
const payouts = ref<Payout[]>([])
const orders = ref<ProviderOrderSummary[]>([])
const showInvoice = ref(false)
const invoice = ref<TaxInvoice | null>(null)
const reviews = ref<Review[]>([])
const analytics = ref<OrgAnalytics | null>(null)
const questions = ref<ListingQuestion[]>([])
const showAnswer = ref(false)
const answerForm = reactive({ questionId: '', text: '' })
const unansweredCount = computed(() => questions.value.filter((q) => !q.answer).length)
const saving = ref(false)
const savingAbn = ref(false)
const abnDraft = ref('')
const showVenue = ref(false)
const showProgram = ref(false)
const showWwcc = ref(false)
const showInsurance = ref(false)
const showReply = ref(false)
const replyForm = reactive({ reviewId: '', text: '' })

const categoryOptions = CATEGORIES.map((c) => ({ label: c.label, value: c.value }))
const venueForm = reactive({ name: '', suburb: '', postcode: '', latitude: null as number | null, longitude: null as number | null })
const programForm = reactive({ title: '', category: 'art', description: '' })
const wwccForm = reactive({ staff_name: '', wwcc_number: '', expiry_date: '' })
const insForm = reactive({ file_ref: '', expiry_date: '' })

const wwccValid = computed(() => wwccForm.staff_name && wwccForm.wwcc_number && wwccForm.expiry_date)
const scheduledTotal = computed(() =>
  payouts.value.filter((p) => p.status === 'scheduled').reduce((n, p) => n + p.amount_cents, 0),
)
const avgRating = computed(() =>
  reviews.value.length
    ? reviews.value.reduce((n, r) => n + r.rating, 0) / reviews.value.length
    : 0,
)

const connectDisplay = computed(() => payoutSetupDisplay(connect.value))

function statusColor(s: string): string {
  return { pending: 'warning', approved: 'positive', suspended: 'grey-6' }[s] ?? 'grey'
}
function vColor(s: string): string {
  return { pending: 'warning', verified: 'positive', rejected: 'negative', expired: 'negative' }[s] ?? 'grey'
}

// Expiry warning for a compliance doc (PRD §8.1): red if lapsed, amber within 30d.
function expiryWarn(dateStr: string | null): { text: string; cls: string } | null {
  if (!dateStr) return null
  const days = Math.ceil((new Date(`${dateStr}T00:00:00`).getTime() - Date.now()) / 86_400_000)
  if (days < 0) return { text: 'Expired', cls: 'text-negative text-weight-600' }
  if (days <= 30) return { text: `Expires in ${days} day(s)`, cls: 'text-warning text-weight-600' }
  return null
}
function payoutColor(s: string): string {
  return { scheduled: 'primary', paid: 'positive', held: 'warning', reversed: 'grey-6' }[s] ?? 'grey'
}

async function load(): Promise<void> {
  try {
    org.value = await api.org.get(props.id)
    abnDraft.value = org.value.abn ?? ''
    ;[venues.value, programs.value, wwcc.value, insurance.value, payouts.value, reviews.value] =
      await Promise.all([
        api.catalog.venues(props.id),
        api.catalog.programs(props.id),
        api.org.wwcc(props.id),
        api.org.insurance(props.id),
        api.payments.payouts(props.id),
        api.reviews.forProvider(props.id),
      ])
    try {
      connect.value = await api.payments.connectStatus(props.id)
    } catch {
      connect.value = null // non-fatal
    }
    try {
      analytics.value = await api.analytics.org(props.id)
    } catch {
      analytics.value = null // non-fatal
    }
    try {
      questions.value = await api.qanda.forProvider(props.id)
    } catch {
      questions.value = []
    }
    try {
      orders.value = await api.booking.providerOrders(props.id)
    } catch {
      orders.value = [] // non-fatal
    }
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function openInvoice(paymentId: string): Promise<void> {
  showInvoice.value = true
  invoice.value = null
  try {
    invoice.value = await api.booking.taxInvoice(paymentId, props.id)
  } catch (err) {
    showInvoice.value = false
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function startConnect(): Promise<void> {
  connecting.value = true
  try {
    const origin = window.location.origin
    const base = `${origin}/provider/orgs/${props.id}`
    const url = await api.payments.connectOnboard(
      props.id,
      `${base}?connect=return`,
      `${base}?connect=refresh`,
    )
    window.location.href = url
  } catch (err) {
    connecting.value = false
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

// Stripe bounces the provider back with ?connect=return; re-pull capability flags.
async function handleConnectReturn(): Promise<void> {
  if (route.query.connect !== 'return') return
  try {
    connect.value = await api.payments.connectRefresh(props.id)
    if (connect.value.payouts_enabled) {
      $q.notify({ type: 'positive', message: 'Payouts are now active.' })
    }
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    await router.replace({ name: 'provider-org', params: { id: props.id } })
  }
}

function openAnswer(questionId: string): void {
  Object.assign(answerForm, { questionId, text: '' })
  showAnswer.value = true
}

async function postAnswer(): Promise<void> {
  saving.value = true
  try {
    const updated = await api.qanda.answer(answerForm.questionId, answerForm.text.trim())
    questions.value = questions.value.map((q) => (q.id === updated.id ? updated : q))
    showAnswer.value = false
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

function openReply(reviewId: string): void {
  Object.assign(replyForm, { reviewId, text: '' })
  showReply.value = true
}

async function postReply(): Promise<void> {
  saving.value = true
  try {
    const updated = await api.reviews.reply(replyForm.reviewId, replyForm.text.trim())
    reviews.value = reviews.value.map((r) => (r.id === updated.id ? updated : r))
    showReply.value = false
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

async function saveAbn(): Promise<void> {
  savingAbn.value = true
  try {
    org.value = await api.org.setAbn(props.id, abnDraft.value)
    $q.notify({ type: 'positive', message: 'ABN saved' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    savingAbn.value = false
  }
}

async function addWwcc(): Promise<void> {
  saving.value = true
  try {
    await api.org.addWwcc(props.id, { ...wwccForm })
    showWwcc.value = false
    Object.assign(wwccForm, { staff_name: '', wwcc_number: '', expiry_date: '' })
    wwcc.value = await api.org.wwcc(props.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
  }
}

async function addInsurance(): Promise<void> {
  saving.value = true
  try {
    await api.org.addInsurance(props.id, {
      file_ref: insForm.file_ref,
      expiry_date: insForm.expiry_date || null,
    })
    showInsurance.value = false
    Object.assign(insForm, { file_ref: '', expiry_date: '' })
    insurance.value = await api.org.insurance(props.id)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  } finally {
    saving.value = false
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

onMounted(async () => {
  await load()
  await handleConnectReturn()
})
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
.jg-comp-abn { display: flex; align-items: center; gap: 10px; }
.jg-invrow { cursor: pointer; font: inherit; text-align: left; width: 100%; }
.jg-inv td, .jg-inv th { padding: 6px 8px; }
.jg-vlist { display: flex; flex-direction: column; gap: 8px; }
.jg-vrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--jg-line);
  border-radius: 12px;
  padding: 8px 12px;
}
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jg-review__reply {
  margin-top: 12px;
  padding: 10px 12px;
  border-left: 3px solid var(--jg-line);
  background: #fafbfd;
  border-radius: 0 10px 10px 0;
}
.jg-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 599px) {
  .jg-stats { grid-template-columns: 1fr; }
}
.jg-stat { padding: 16px 18px; }
.jg-stat__num { font-size: 26px; font-weight: 700; line-height: 1.1; }
.jg-stat__label { font-weight: 600; margin-top: 2px; }
</style>
