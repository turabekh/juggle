// API response/request shapes (mirrors the FastAPI schemas — snake_case JSON).

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthConfig {
  sms_enabled: boolean
}

export interface User {
  id: string
  email: string
  full_name: string | null
  is_admin: boolean
  created_at: string
}

export interface CoGuardian {
  id: string
  other_email: string
  other_name: string | null
  direction: 'sent' | 'received'
  accepted: boolean
}

export interface Child {
  id: string
  first_name: string
  date_of_birth: string
  medical_notes: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  photo_consent: boolean
}

export interface ChildCreate {
  first_name: string
  date_of_birth: string
  medical_notes?: string | null
  emergency_contact_name?: string | null
  emergency_contact_phone?: string | null
  photo_consent?: boolean
}

// --- AI holiday planner (§7 discovery; behind the `planner` flag) ---
export interface PlanRequest {
  ages: number[]
  date_from: string
  date_to: string
  suburb?: string | null
  budget_cents?: number | null
  categories?: string[] | null
  day_type?: string | null
  start_after_hour?: number | null
  drop_off_only?: boolean
}

export interface PlanCandidate {
  session_id: string
  title: string
  category: string
  organisation_name: string
  venue_name: string
  suburb: string | null
  starts_at: string
  ends_at: string
  price_cents: number
  age_min: number
  age_max: number
  seats_remaining: number
  distance_km: number | null
}

export interface PlanItem {
  session: PlanCandidate
  for_ages: number[]
  reason: string
}

export interface PlanDay {
  day: string
  items: PlanItem[]
}

export interface PlanOut {
  days: PlanDay[]
  total_cents: number
  summary: string
  generated_by: 'ai' | 'rules'
  candidate_count: number
}

export interface SearchCard {
  session_id: string
  program_id: string
  title: string
  category: string
  organisation_name: string
  venue_name: string
  suburb: string | null
  postcode: string | null
  starts_at: string
  ends_at: string
  price_cents: number
  age_min: number
  age_max: number
  seats_remaining: number
  session_type: string
  drop_off: boolean
  distance_km: number | null
}

export interface SearchResults {
  items: SearchCard[]
  limit: number
  offset: number
}

export interface SessionDetail {
  id: string
  program_id: string
  venue_id: string
  starts_at: string
  ends_at: string
  capacity: number
  seats_taken: number
  seats_remaining: number
  price_cents: number
  age_min: number
  age_max: number
  session_type: string
  drop_off: boolean
  status: string
  title: string
  category: string
  description: string | null
  organisation_name: string
  venue_name: string
  suburb: string | null
  postcode: string | null
  provider_approved: boolean
  provider_abn: boolean
  provider_wwcc_verified: boolean
  provider_insurance_verified: boolean
}

export interface Hold {
  id: string
  session_id: string
  quantity: number
  status: string
  expires_at: string
}

export interface Availability {
  session_id: string
  capacity: number
  seats_taken: number
  seats_remaining: number
}

export interface BookingChild {
  child_id: string
  form_answers: Record<string, unknown>
}

export interface Booking {
  id: string
  session_id: string
  organisation_id: string
  payment_id: string | null
  status: string
  unit_price_cents: number
  children: BookingChild[]
}

export interface Notification {
  id: string
  kind: string
  subject: string
  to_email: string
  status: string
  detail: Record<string, unknown>
  created_at: string
}

export interface Order {
  payment_id: string
  amount_cents: number
  application_fee_cents: number
  fee_gst_cents: number
  currency: string
  status: string
  client_secret: string | null
  bookings: Booking[]
}

export interface PaymentConfig {
  live: boolean
  publishable_key: string | null
}

export interface PartyPackage {
  id: string
  organisation_id: string
  venue_id: string
  name: string
  description: string | null
  per_head_price_cents: number
  min_headcount: number
  max_headcount: number
  deposit_pct: number | null
  outdoor: boolean
  status: string
}

export interface PartyPackageCreate {
  venue_id: string
  name: string
  description?: string | null
  per_head_price_cents: number
  min_headcount: number
  max_headcount: number
  deposit_pct?: number | null
  outdoor?: boolean
}

export interface PartyPackageDetail extends PartyPackage {
  organisation_name: string
  venue_name: string
  venue_suburb: string | null
  deposit_pct_effective: number
}

export interface PartySlot {
  id: string
  package_id: string
  starts_at: string
  ends_at: string
  status: string
}

export interface PartyBooking {
  id: string
  slot_id: string
  package_id: string
  headcount: number
  total_cents: number
  deposit_cents: number
  balance_cents: number
  status: string
  client_secret: string | null
}

// --- Party Planner (ADR-0011) ------------------------------------------------

export interface PlanOptionView {
  id: string
  kind: 'package' | 'custom'
  position: number
  voided: boolean
  custom_text: string | null
  package_id: string | null
  package_name: string | null
  venue_name: string | null
  starts_at: string | null
  ends_at: string | null
  per_head_price_cents: number | null
  available: boolean | null
  votes: number
  is_favourite: boolean
  reactions: Record<string, number>
}

export interface PlanBoardEntry {
  nickname: string | null
  avatar_key: string | null
}

export type PartyWidgetKey = 'welcome' | 'countdown' | 'board' | 'reveal_venue'

export interface PartyPageView {
  template: string
  title: string | null
  message: string | null
  hero_avatar: string | null
  widgets: PartyWidgetKey[]
}

export interface PartyPagePatch {
  template: string
  title: string
  message: string
  hero_avatar: string | null
  widgets: PartyWidgetKey[]
}

export interface PlanHostInvite {
  id: string
  mode: 'open' | 'email'
  parent_name: string
  email: string
  status: 'pending' | 'approved' | 'removed' | 'blocked'
  attending: boolean | null
  kid_count: number | null
  nickname: string | null
  avatar_key: string | null
}

export interface PlanView {
  id: string
  status: 'draft' | 'open' | 'resolved' | 'booked' | 'expired_unbooked'
  deadline_at: string | null
  theme: string
  approval_required: boolean
  share_token: string | null
  share_path: string | null
  winning_option_id: string | null
  booking_id: string | null
  ranking: string[]
  options: PlanOptionView[]
  invites: PlanHostInvite[]
  rsvp_yes_headcount: number
  page: PartyPageView
  deadline_warnings: string[]
  deposit_client_secret: string | null
  deposit_payment_id: string | null
  deposit_cents: number | null
}

export interface PublicPlanView {
  status: 'draft' | 'open' | 'resolved' | 'booked' | 'expired_unbooked'
  is_open: boolean
  deadline_at: string | null
  theme: string
  options: PlanOptionView[]
  board: PlanBoardEntry[]
  rsvp_count: number
  page: PartyPageView
  winner_option_id: string | null
  is_tie: boolean
}

export interface PlanInviteCreated {
  invite_token: string
  status: string
}

export interface PlanRsvpView {
  attending: boolean
  kid_count: number
  nickname: string | null
  avatar_key: string | null
}

export interface InviteSelfView {
  invite_token: string
  status: 'pending' | 'approved' | 'removed' | 'blocked'
  has_voted: boolean
  rsvp: PlanRsvpView | null
  plan: PublicPlanView
}

export interface ProviderOrderSummary {
  payment_id: string
  ordered_at: string
  session_count: number
  gross_cents: number
  commission_cents: number
  commission_gst_cents: number
  net_cents: number
}

export interface TaxInvoiceLine {
  session_id: string
  session_title: string
  starts_at: string
  status: string
  gross_cents: number
  commission_cents: number
  commission_gst_cents: number
  net_cents: number
}

export interface TaxInvoiceParty {
  name: string
  abn: string | null
}

export interface TaxInvoice {
  invoice_number: string
  issued_at: string
  payment_id: string
  currency: string
  supplier: TaxInvoiceParty
  recipient: TaxInvoiceParty
  lines: TaxInvoiceLine[]
  totals: {
    gross_cents: number
    commission_cents: number
    commission_gst_cents: number
    net_cents: number
  }
}

export interface PaymentStatus {
  id: string
  amount_cents: number
  application_fee_cents: number
  fee_gst_cents: number
  currency: string
  status: string
}

export type Category = 'sport' | 'art' | 'stem' | 'drama' | 'outdoor' | 'other'

export interface SearchFilters {
  lat: number | null
  lng: number | null
  radius_km: number
  suburb: string | null
  date_from: string | null
  date_to: string | null
  child_age: number | null
  category: Category | null
  price_max_cents: number | null
  session_type: 'half_day' | 'full_day' | null
  when: 'weekend' | 'weekday' | 'after_school' | null
  available_only: boolean
}

// --- Admin ------------------------------------------------------------------

export type OrgStatus = 'pending' | 'approved' | 'suspended'

export interface OrgAdmin {
  id: string
  name: string
  slug: string
  status: OrgStatus
  reliability_score: number
  abn: string | null
  created_at: string
}

export interface SettingItem {
  key: string
  value: number
  default: number
  minimum: number
  maximum: number
  description: string
}

export interface SettingVersion {
  version: number
  is_current: boolean
  note: string | null
  changed_by_id: string | null
  created_at: string
}

export interface Flag {
  key: string
  description: string | null
  enabled: boolean
  rollout_percentage: number
  targeting: Record<string, unknown> | null
}

export interface AuditEvent {
  id: string
  actor_id: string | null
  impersonated_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  detail: Record<string, unknown>
  created_at: string
}

export type ImpersonationMode = 'view_as' | 'act_as'

export interface ImpersonationToken {
  session_id: string
  token: string
  mode: ImpersonationMode
  expires_at: string
}

export interface ImpersonationSession {
  id: string
  impersonator_id: string
  target_id: string
  mode: ImpersonationMode
  reason: string | null
  expires_at: string
  ended_at: string | null
}

export interface UserSummary {
  id: string
  email: string
  full_name: string | null
  is_admin: boolean
}

// --- Provider console -------------------------------------------------------

export interface Org {
  id: string
  name: string
  slug: string
  status: OrgStatus
  abn: string | null
  created_at: string
}

export interface Venue {
  id: string
  organisation_id: string
  name: string
  suburb: string | null
  postcode: string | null
}

export interface Program {
  id: string
  organisation_id: string
  title: string
  description: string | null
  category: string
  status: 'draft' | 'published' | 'unpublished'
}

export interface CatalogSession {
  id: string
  program_id: string
  venue_id: string
  starts_at: string
  ends_at: string
  capacity: number
  seats_taken: number
  seats_remaining: number
  price_cents: number
  age_min: number
  age_max: number
  session_type: 'half_day' | 'full_day'
  drop_off: boolean
  status: 'scheduled' | 'cancelled'
}

export interface RosterRow {
  booking_id: string
  booking_child_id: string
  child_first_name: string
  age: number
  medical_notes: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  form_answers: Record<string, unknown>
  attended: boolean
  attended_at: string | null
}

export interface RosterOut {
  session_id: string
  count: number
  attended_count: number
  rows: RosterRow[]
}

export interface AttendanceOut {
  booking_child_id: string
  attended: boolean
  attended_at: string | null
}

export interface SessionCancelResult {
  session_id: string
  cancelled_bookings: number
  refunded_payments: number
  reliability_score: number
}

export type VerificationStatus = 'pending' | 'verified' | 'rejected' | 'expired'

export interface WwccRecord {
  id: string
  staff_name: string
  wwcc_number: string
  expiry_date: string
  status: VerificationStatus
  created_at: string
}

export interface InsuranceDoc {
  id: string
  file_ref: string
  expiry_date: string | null
  status: VerificationStatus
  created_at: string
}

export interface OrgVerifications {
  organisation_id: string
  name: string
  status: OrgStatus
  abn: string | null
  wwcc: WwccRecord[]
  insurance: InsuranceDoc[]
}

export type PayoutStatus = 'scheduled' | 'paid' | 'held' | 'reversed'

export interface Payout {
  id: string
  organisation_id: string
  session_id: string | null
  amount_cents: number
  status: PayoutStatus
  scheduled_for: string | null
}

export interface PayoutRunResult {
  released: number
  total_cents: number
}

export interface ConnectStatus {
  onboarded: boolean
  charges_enabled: boolean
  payouts_enabled: boolean
}

export interface SessionCreateInput {
  venue_id: string
  starts_at: string
  ends_at: string
  capacity: number
  price_cents: number
  age_min: number
  age_max: number
  session_type: 'half_day' | 'full_day'
  drop_off: boolean
  what_to_bring?: string | null
}

// --- Reviews (PRD §7.6) ------------------------------------------------------

export type ReviewStatus = 'pending' | 'published' | 'rejected'

export interface RatingSummary {
  average: number | null
  count: number
}

export interface ReviewPublic {
  id: string
  rating: number
  body: string
  author_label: string
  created_at: string
  provider_reply: string | null
  provider_reply_at: string | null
}

export interface ReviewList {
  summary: RatingSummary
  items: ReviewPublic[]
}

export interface Review {
  id: string
  booking_id: string
  organisation_id: string
  program_id: string
  session_id: string
  rating: number
  body: string
  status: ReviewStatus
  rejection_reason: string | null
  author_label: string
  program_title: string
  provider_reply: string | null
  provider_reply_at: string | null
  created_at: string
}

export interface ReviewableBooking {
  booking_id: string
  session_id: string
  program_title: string
  organisation_name: string
  starts_at: string
}

// --- Listing Q&A (PRD §7.2) --------------------------------------------------

export interface ListingQuestion {
  id: string
  program_id: string
  body: string
  answer: string | null
  answered_at: string | null
  asker_label: string
  created_at: string
}

// --- Waitlist (PRD §7.7) -----------------------------------------------------

export type WaitlistStatus = 'waiting' | 'offered' | 'claimed' | 'expired' | 'cancelled'

export interface WaitlistEntry {
  id: string
  session_id: string
  status: WaitlistStatus
  position: number | null
  program_title: string
  organisation_name: string
  starts_at: string
  ends_at: string
  offer_hold_id: string | null
  offer_expires_at: string | null
  created_at: string
}

export interface SessionWaitlist {
  session_id: string
  waiting: number
  offered: number
}

// --- Provider comms + analytics (PRD §8.5 / §8.6) ----------------------------

export interface Broadcast {
  id: string
  session_id: string
  template_key: string | null
  subject: string
  body: string
  recipient_count: number
  created_at: string
}

export interface ProgramStat {
  program_id: string
  title: string
  category: string
  status: string
  sessions: number
  capacity_total: number
  booked_total: number
  fill_rate: number
  revenue_cents: number
}

export interface FamilyMix {
  total: number
  new: number
  returning: number
}

export interface OrgAnalytics {
  organisation_id: string
  revenue_cents: number
  bookings: number
  sessions_total: number
  published_sessions: number
  capacity_total: number
  booked_total: number
  fill_rate: number
  families: FamilyMix
  programs: ProgramStat[]
}

// --- Funnel analytics (PRD §13) ----------------------------------------------

export interface FunnelStage {
  event_type: string
  count: number
}

export interface FunnelOut {
  days: number
  stages: FunnelStage[]
}

// --- Scheduler / maintenance worker ------------------------------------------

export interface JobSummary {
  holds_reclaimed: number
  waitlist_sessions_processed: number
  waitlist_offers_made: number
  waitlist_offers_expired: number
  reminders_sent: number
  what_to_bring_sent: number
  compliance_expired: number
}
