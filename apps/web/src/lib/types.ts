// API response/request shapes (mirrors the FastAPI schemas — snake_case JSON).

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  email: string
  full_name: string | null
  is_admin: boolean
  created_at: string
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
  currency: string
  status: string
  bookings: Booking[]
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
  child_first_name: string
  age: number
  medical_notes: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  form_answers: Record<string, unknown>
}

export interface RosterOut {
  session_id: string
  count: number
  rows: RosterRow[]
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
