// Typed API client. A single axios instance injects the bearer token (held in
// a module variable set by the auth store — avoids a store↔api import cycle).

import axios, { type AxiosInstance } from 'axios'

import type {
  AttendanceOut,
  AuditEvent,
  Availability,
  Booking,
  Broadcast,
  CatalogSession,
  Child,
  ChildCreate,
  CoGuardian,
  ConnectStatus,
  Flag,
  FunnelOut,
  Hold,
  ImpersonationMode,
  ImpersonationSession,
  ImpersonationToken,
  InsuranceDoc,
  ListingQuestion,
  JobSummary,
  Notification,
  Order,
  PartyBooking,
  PartyPackage,
  PartyPackageCreate,
  PartyPackageDetail,
  PartySlot,
  PaymentConfig,
  PaymentStatus,
  ProviderOrderSummary,
  TaxInvoice,
  Org,
  OrgAdmin,
  OrgAnalytics,
  OrgStatus,
  OrgVerifications,
  Payout,
  PayoutRunResult,
  PayoutStatus,
  Program,
  Review,
  ReviewableBooking,
  ReviewList,
  ReviewStatus,
  RosterOut,
  SearchFilters,
  SearchResults,
  SessionCancelResult,
  SessionCreateInput,
  SessionDetail,
  SessionWaitlist,
  SettingItem,
  SettingVersion,
  TokenResponse,
  User,
  UserSummary,
  Venue,
  VerificationStatus,
  WaitlistEntry,
  WwccRecord,
} from '@/lib/types'

let authToken: string | null = null
export function setAuthToken(token: string | null): void {
  authToken = token
}

// On the client, requests are relative (Vite proxy / same-origin nginx). During
// SSR there is no origin, so hit the API directly (overridable via env).
const API_BASE = import.meta.env.SSR
  ? (import.meta.env.VITE_SSR_API_BASE ?? 'http://localhost:8000/api/v1')
  : '/api/v1'
const http: AxiosInstance = axios.create({ baseURL: API_BASE, timeout: 15000 })

http.interceptors.request.use((config) => {
  if (authToken) config.headers.Authorization = `Bearer ${authToken}`
  return config
})

/** Extract a human-friendly message from an API error. */
export function apiError(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (err.response?.status === 401) return 'Please sign in to continue'
  }
  return fallback
}

function cleanParams(filters: SearchFilters): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== '' && value !== undefined) out[key] = value
  }
  return out
}

export const api = {
  auth: {
    async signup(email: string, password: string, full_name?: string): Promise<TokenResponse> {
      const { data } = await http.post<TokenResponse>('/identity/signup', {
        email,
        password,
        full_name,
      })
      return data
    },
    async login(email: string, password: string): Promise<TokenResponse> {
      const { data } = await http.post<TokenResponse>('/identity/login', { email, password })
      return data
    },
    async me(): Promise<User> {
      const { data } = await http.get<User>('/identity/me')
      return data
    },
    async deleteAccount(): Promise<void> {
      await http.delete('/identity/me')
    },
  },
  children: {
    async list(): Promise<Child[]> {
      const { data } = await http.get<Child[]>('/identity/children')
      return data
    },
    async create(payload: ChildCreate): Promise<Child> {
      const { data } = await http.post<Child>('/identity/children', payload)
      return data
    },
  },
  coGuardians: {
    async list(): Promise<CoGuardian[]> {
      const { data } = await http.get<CoGuardian[]>('/identity/co-guardians')
      return data
    },
    async invite(email: string): Promise<CoGuardian> {
      const { data } = await http.post<CoGuardian>('/identity/co-guardians', { email })
      return data
    },
    async accept(linkId: string): Promise<CoGuardian> {
      const { data } = await http.post<CoGuardian>(`/identity/co-guardians/${linkId}/accept`)
      return data
    },
    async remove(linkId: string): Promise<void> {
      await http.delete(`/identity/co-guardians/${linkId}`)
    },
  },
  search: {
    async sessions(filters: SearchFilters): Promise<SearchResults> {
      const { data } = await http.get<SearchResults>('/search/sessions', {
        params: cleanParams(filters),
      })
      return data
    },
  },
  catalog: {
    async session(id: string): Promise<SessionDetail> {
      const { data } = await http.get<SessionDetail>(`/catalog/sessions/${id}`)
      return data
    },
    async createVenue(payload: {
      organisation_id: string
      name: string
      suburb?: string | null
      postcode?: string | null
      latitude?: number | null
      longitude?: number | null
    }): Promise<Venue> {
      const { data } = await http.post<Venue>('/catalog/venues', payload)
      return data
    },
    async venues(organisationId: string): Promise<Venue[]> {
      const { data } = await http.get<Venue[]>('/catalog/venues', {
        params: { organisation_id: organisationId },
      })
      return data
    },
    async programs(organisationId: string): Promise<Program[]> {
      const { data } = await http.get<Program[]>('/catalog/programs', {
        params: { organisation_id: organisationId },
      })
      return data
    },
    async program(id: string): Promise<Program> {
      const { data } = await http.get<Program>(`/catalog/programs/${id}`)
      return data
    },
    async createProgram(payload: {
      organisation_id: string
      title: string
      description?: string | null
      category: string
    }): Promise<Program> {
      const { data } = await http.post<Program>('/catalog/programs', payload)
      return data
    },
    async publishProgram(programId: string): Promise<Program> {
      const { data } = await http.post<Program>(`/catalog/programs/${programId}/publish`)
      return data
    },
    async programSessions(programId: string): Promise<CatalogSession[]> {
      const { data } = await http.get<CatalogSession[]>(`/catalog/programs/${programId}/sessions`)
      return data
    },
    async createSession(programId: string, body: SessionCreateInput): Promise<CatalogSession> {
      const { data } = await http.post<CatalogSession>(
        `/catalog/programs/${programId}/sessions`,
        body,
      )
      return data
    },
    async duplicateSessions(programId: string, shiftDays: number): Promise<CatalogSession[]> {
      const { data } = await http.post<CatalogSession[]>(
        `/catalog/programs/${programId}/duplicate-sessions`,
        { shift_days: shiftDays },
      )
      return data
    },
    async bulkSessions(
      programId: string,
      items: SessionCreateInput[],
    ): Promise<CatalogSession[]> {
      const { data } = await http.post<CatalogSession[]>(
        `/catalog/programs/${programId}/bulk-sessions`,
        { items },
      )
      return data
    },
  },
  org: {
    async mine(): Promise<Org[]> {
      const { data } = await http.get<Org[]>('/org')
      return data
    },
    async get(id: string): Promise<Org> {
      const { data } = await http.get<Org>(`/org/${id}`)
      return data
    },
    async create(name: string): Promise<Org> {
      const { data } = await http.post<Org>('/org', { name })
      return data
    },
    async setAbn(orgId: string, abn: string): Promise<Org> {
      const { data } = await http.put<Org>(`/org/${orgId}/abn`, { abn })
      return data
    },
    async wwcc(orgId: string): Promise<WwccRecord[]> {
      const { data } = await http.get<WwccRecord[]>(`/org/${orgId}/wwcc`)
      return data
    },
    async addWwcc(
      orgId: string,
      payload: { staff_name: string; wwcc_number: string; expiry_date: string },
    ): Promise<WwccRecord> {
      const { data } = await http.post<WwccRecord>(`/org/${orgId}/wwcc`, payload)
      return data
    },
    async insurance(orgId: string): Promise<InsuranceDoc[]> {
      const { data } = await http.get<InsuranceDoc[]>(`/org/${orgId}/insurance`)
      return data
    },
    async addInsurance(
      orgId: string,
      payload: { file_ref: string; expiry_date?: string | null },
    ): Promise<InsuranceDoc> {
      const { data } = await http.post<InsuranceDoc>(`/org/${orgId}/insurance`, payload)
      return data
    },
  },
  roster: {
    async forSession(sessionId: string): Promise<RosterOut> {
      const { data } = await http.get<RosterOut>(`/roster/sessions/${sessionId}`)
      return data
    },
    async csv(sessionId: string): Promise<string> {
      const { data } = await http.get<string>(`/roster/sessions/${sessionId}/export.csv`, {
        responseType: 'text',
      })
      return data
    },
    async markAttendance(
      sessionId: string,
      bookingChildId: string,
      attended: boolean,
    ): Promise<AttendanceOut> {
      const { data } = await http.put<AttendanceOut>(
        `/roster/sessions/${sessionId}/attendance/${bookingChildId}`,
        { attended },
      )
      return data
    },
  },
  inventory: {
    async availability(sessionId: string): Promise<Availability> {
      const { data } = await http.get<Availability>(`/inventory/sessions/${sessionId}/availability`)
      return data
    },
    async hold(sessionId: string, quantity: number): Promise<Hold> {
      const { data } = await http.post<Hold>('/inventory/holds', {
        session_id: sessionId,
        quantity,
      })
      return data
    },
    async release(holdId: string): Promise<void> {
      await http.delete(`/inventory/holds/${holdId}`)
    },
  },
  booking: {
    async checkout(
      idempotencyKey: string,
      items: { hold_id: string; children: { child_id: string; form_answers?: Record<string, unknown> }[] }[],
    ): Promise<Order> {
      const { data } = await http.post<Order>('/booking/checkout', {
        idempotency_key: idempotencyKey,
        items,
      })
      return data
    },
    async confirm(paymentId: string): Promise<Order> {
      const { data } = await http.post<Order>(`/booking/payments/${paymentId}/confirm`)
      return data
    },
    async cancel(paymentId: string): Promise<Order> {
      const { data } = await http.post<Order>(`/booking/payments/${paymentId}/cancel`)
      return data
    },
    async list(): Promise<Booking[]> {
      const { data } = await http.get<Booking[]>('/booking/bookings')
      return data
    },
    async cancelSession(sessionId: string): Promise<SessionCancelResult> {
      const { data } = await http.post<SessionCancelResult>(`/booking/sessions/${sessionId}/cancel`)
      return data
    },
    async calendarIcs(paymentId: string): Promise<string> {
      const { data } = await http.get<string>(`/booking/payments/${paymentId}/calendar.ics`, {
        responseType: 'text',
      })
      return data
    },
    async providerOrders(organisationId: string): Promise<ProviderOrderSummary[]> {
      const { data } = await http.get<ProviderOrderSummary[]>('/booking/orders', {
        params: { organisation_id: organisationId },
      })
      return data
    },
    async taxInvoice(paymentId: string, organisationId: string): Promise<TaxInvoice> {
      const { data } = await http.get<TaxInvoice>(`/booking/orders/${paymentId}/tax-invoice`, {
        params: { organisation_id: organisationId },
      })
      return data
    },
  },
  notifications: {
    async list(): Promise<Notification[]> {
      const { data } = await http.get<Notification[]>('/notifications')
      return data
    },
  },
  payments: {
    async config(): Promise<PaymentConfig> {
      const { data } = await http.get<PaymentConfig>('/payments/config')
      return data
    },
    async status(paymentId: string): Promise<PaymentStatus> {
      const { data } = await http.get<PaymentStatus>(`/payments/${paymentId}`)
      return data
    },
    async payouts(organisationId: string): Promise<Payout[]> {
      const { data } = await http.get<Payout[]>('/payments/payouts', {
        params: { organisation_id: organisationId },
      })
      return data
    },
    async connectStatus(organisationId: string): Promise<ConnectStatus> {
      const { data } = await http.get<ConnectStatus>('/payments/connect/status', {
        params: { organisation_id: organisationId },
      })
      return data
    },
    async connectOnboard(
      organisationId: string,
      returnUrl: string,
      refreshUrl: string,
    ): Promise<string> {
      const { data } = await http.post<{ url: string }>('/payments/connect/onboard', {
        organisation_id: organisationId,
        return_url: returnUrl,
        refresh_url: refreshUrl,
      })
      return data.url
    },
    async connectRefresh(organisationId: string): Promise<ConnectStatus> {
      const { data } = await http.post<ConnectStatus>('/payments/connect/refresh', {
        organisation_id: organisationId,
      })
      return data
    },
  },
  parties: {
    // Provider
    async providerPackages(orgId: string): Promise<PartyPackage[]> {
      const { data } = await http.get<PartyPackage[]>(`/parties/orgs/${orgId}/packages/manage`)
      return data
    },
    async createPackage(orgId: string, payload: PartyPackageCreate): Promise<PartyPackage> {
      const { data } = await http.post<PartyPackage>(`/parties/orgs/${orgId}/packages`, payload)
      return data
    },
    async archivePackage(packageId: string): Promise<PartyPackage> {
      const { data } = await http.post<PartyPackage>(`/parties/packages/${packageId}/archive`)
      return data
    },
    async addSlots(
      packageId: string,
      slots: { starts_at: string; ends_at: string }[],
    ): Promise<PartySlot[]> {
      const { data } = await http.post<PartySlot[]>(`/parties/packages/${packageId}/slots`, {
        slots,
      })
      return data
    },
    // Public / parent
    async activePackages(orgId: string): Promise<PartyPackage[]> {
      const { data } = await http.get<PartyPackage[]>(`/parties/orgs/${orgId}/packages`)
      return data
    },
    async allPackages(): Promise<PartyPackageDetail[]> {
      const { data } = await http.get<PartyPackageDetail[]>('/parties/packages')
      return data
    },
    async package(packageId: string): Promise<PartyPackageDetail> {
      const { data } = await http.get<PartyPackageDetail>(`/parties/packages/${packageId}`)
      return data
    },
    async slots(packageId: string): Promise<PartySlot[]> {
      const { data } = await http.get<PartySlot[]>(`/parties/packages/${packageId}/slots`)
      return data
    },
    async book(slotId: string, headcount: number): Promise<PartyBooking> {
      const { data } = await http.post<PartyBooking>(`/parties/slots/${slotId}/book`, {
        headcount,
      })
      return data
    },
    async devConfirm(bookingId: string): Promise<PartyBooking> {
      const { data } = await http.post<PartyBooking>(`/parties/bookings/${bookingId}/dev-confirm`)
      return data
    },
    async adjust(bookingId: string, headcount: number): Promise<PartyBooking> {
      const { data } = await http.post<PartyBooking>(`/parties/bookings/${bookingId}/adjust`, {
        headcount,
      })
      return data
    },
    async cancel(bookingId: string): Promise<PartyBooking> {
      const { data } = await http.post<PartyBooking>(`/parties/bookings/${bookingId}/cancel`)
      return data
    },
  },
  reviews: {
    // Public
    async forProgram(programId: string): Promise<ReviewList> {
      const { data } = await http.get<ReviewList>(`/reviews/programs/${programId}`)
      return data
    },
    async forOrganisation(organisationId: string): Promise<ReviewList> {
      const { data } = await http.get<ReviewList>(`/reviews/organisations/${organisationId}`)
      return data
    },
    // Guardian
    async reviewable(): Promise<ReviewableBooking[]> {
      const { data } = await http.get<ReviewableBooking[]>('/reviews/reviewable')
      return data
    },
    async mine(): Promise<Review[]> {
      const { data } = await http.get<Review[]>('/reviews/mine')
      return data
    },
    async submit(payload: {
      booking_id: string
      rating: number
      body: string
    }): Promise<Review> {
      const { data } = await http.post<Review>('/reviews', payload)
      return data
    },
    // Provider
    async forProvider(organisationId: string): Promise<Review[]> {
      const { data } = await http.get<Review[]>(`/reviews/provider/${organisationId}`)
      return data
    },
    async reply(reviewId: string, reply: string): Promise<Review> {
      const { data } = await http.post<Review>(`/reviews/${reviewId}/reply`, { reply })
      return data
    },
    // Admin moderation
    async moderationQueue(status: ReviewStatus = 'pending'): Promise<Review[]> {
      const { data } = await http.get<Review[]>('/reviews/moderation/queue', {
        params: { review_status: status },
      })
      return data
    },
    async moderate(reviewId: string, approve: boolean, reason?: string): Promise<Review> {
      const { data } = await http.post<Review>(`/reviews/${reviewId}/moderate`, {
        approve,
        reason,
      })
      return data
    },
  },
  comms: {
    async broadcast(
      sessionId: string,
      payload: { subject: string; body: string; template_key?: string | null },
    ): Promise<Broadcast> {
      const { data } = await http.post<Broadcast>(
        `/comms/sessions/${sessionId}/broadcast`,
        payload,
      )
      return data
    },
    async history(sessionId: string): Promise<Broadcast[]> {
      const { data } = await http.get<Broadcast[]>(`/comms/sessions/${sessionId}/broadcasts`)
      return data
    },
  },
  analytics: {
    async org(organisationId: string): Promise<OrgAnalytics> {
      const { data } = await http.get<OrgAnalytics>(`/analytics/organisations/${organisationId}`)
      return data
    },
    async funnel(days = 30): Promise<FunnelOut> {
      const { data } = await http.get<FunnelOut>('/analytics/funnel', { params: { days } })
      return data
    },
  },
  qanda: {
    async forProgram(programId: string): Promise<ListingQuestion[]> {
      const { data } = await http.get<ListingQuestion[]>(
        `/qanda/programs/${programId}/questions`,
      )
      return data
    },
    async ask(programId: string, body: string): Promise<ListingQuestion> {
      const { data } = await http.post<ListingQuestion>(
        `/qanda/programs/${programId}/questions`,
        { body },
      )
      return data
    },
    async answer(questionId: string, answer: string): Promise<ListingQuestion> {
      const { data } = await http.post<ListingQuestion>(
        `/qanda/questions/${questionId}/answer`,
        { answer },
      )
      return data
    },
    async forProvider(organisationId: string): Promise<ListingQuestion[]> {
      const { data } = await http.get<ListingQuestion[]>(
        `/qanda/provider/${organisationId}/questions`,
      )
      return data
    },
  },
  waitlist: {
    async join(sessionId: string): Promise<WaitlistEntry> {
      const { data } = await http.post<WaitlistEntry>('/waitlist', { session_id: sessionId })
      return data
    },
    async mine(): Promise<WaitlistEntry[]> {
      const { data } = await http.get<WaitlistEntry[]>('/waitlist/mine')
      return data
    },
    async leave(entryId: string): Promise<void> {
      await http.delete(`/waitlist/${entryId}`)
    },
    async sessionCounts(sessionId: string): Promise<SessionWaitlist> {
      const { data } = await http.get<SessionWaitlist>(`/waitlist/sessions/${sessionId}`)
      return data
    },
  },
  scheduler: {
    async run(): Promise<JobSummary> {
      const { data } = await http.post<JobSummary>('/scheduler/run')
      return data
    },
  },
  admin: {
    async users(q: string): Promise<UserSummary[]> {
      const { data } = await http.get<UserSummary[]>('/admin/users', { params: { q } })
      return data
    },
    async userBookings(userId: string): Promise<Booking[]> {
      const { data } = await http.get<Booking[]>(`/admin/users/${userId}/bookings`)
      return data
    },
    async deleteUser(userId: string): Promise<void> {
      await http.post(`/admin/users/${userId}/delete`)
    },
    async mergeUsers(sourceId: string, targetId: string): Promise<void> {
      await http.post('/admin/users/merge', { source_id: sourceId, target_id: targetId })
    },
    async orgs(status: OrgStatus): Promise<OrgAdmin[]> {
      const { data } = await http.get<OrgAdmin[]>('/admin/orgs', { params: { status } })
      return data
    },
    async approveOrg(id: string): Promise<OrgAdmin> {
      const { data } = await http.post<OrgAdmin>(`/admin/orgs/${id}/approve`)
      return data
    },
    async suspendOrg(id: string): Promise<OrgAdmin> {
      const { data } = await http.post<OrgAdmin>(`/admin/orgs/${id}/suspend`)
      return data
    },
    async orgVerifications(id: string): Promise<OrgVerifications> {
      const { data } = await http.get<OrgVerifications>(`/admin/orgs/${id}/verifications`)
      return data
    },
    async verifyWwcc(id: string, status: VerificationStatus): Promise<WwccRecord> {
      const { data } = await http.post<WwccRecord>(`/admin/wwcc/${id}/verify`, { status })
      return data
    },
    async verifyInsurance(id: string, status: VerificationStatus): Promise<InsuranceDoc> {
      const { data } = await http.post<InsuranceDoc>(`/admin/insurance/${id}/verify`, { status })
      return data
    },
    async payouts(status: PayoutStatus): Promise<Payout[]> {
      const { data } = await http.get<Payout[]>('/admin/payouts', { params: { status } })
      return data
    },
    async runPayouts(): Promise<PayoutRunResult> {
      const { data } = await http.post<PayoutRunResult>('/admin/payouts/run')
      return data
    },
    async holdPayout(id: string): Promise<Payout> {
      const { data } = await http.post<Payout>(`/admin/payouts/${id}/hold`)
      return data
    },
    async releasePayout(id: string): Promise<Payout> {
      const { data } = await http.post<Payout>(`/admin/payouts/${id}/release`)
      return data
    },
    async refund(paymentId: string, reason: string): Promise<Order> {
      const { data } = await http.post<Order>(`/admin/payments/${paymentId}/refund`, { reason })
      return data
    },
    async impersonations(): Promise<ImpersonationSession[]> {
      const { data } = await http.get<ImpersonationSession[]>('/admin/impersonations')
      return data
    },
    async startImpersonation(
      targetUserId: string,
      mode: ImpersonationMode,
      reason?: string,
    ): Promise<ImpersonationToken> {
      const { data } = await http.post<ImpersonationToken>('/admin/impersonations', {
        target_user_id: targetUserId,
        mode,
        reason,
      })
      return data
    },
    async endImpersonation(id: string): Promise<void> {
      await http.post(`/admin/impersonations/${id}/end`)
    },
  },
  config: {
    async list(): Promise<SettingItem[]> {
      const { data } = await http.get<SettingItem[]>('/config')
      return data
    },
    async update(key: string, value: number, note?: string): Promise<SettingItem> {
      const { data } = await http.put<SettingItem>(`/config/${key}`, { value, note })
      return data
    },
    async history(key: string): Promise<SettingVersion[]> {
      const { data } = await http.get<SettingVersion[]>(`/config/${key}/history`)
      return data
    },
  },
  flags: {
    async list(): Promise<Flag[]> {
      const { data } = await http.get<Flag[]>('/flags')
      return data
    },
    async upsert(
      key: string,
      payload: {
        enabled: boolean
        rollout_percentage: number
        targeting?: Record<string, unknown> | null
        description?: string | null
      },
    ): Promise<Flag> {
      const { data } = await http.put<Flag>(`/flags/${key}`, payload)
      return data
    },
  },
  audit: {
    async list(params: {
      action?: string
      entity_type?: string
      limit?: number
      offset?: number
    }): Promise<AuditEvent[]> {
      const clean = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== ''),
      )
      const { data } = await http.get<AuditEvent[]>('/audit', { params: clean })
      return data
    },
  },
}
