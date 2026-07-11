// Typed API client. A single axios instance injects the bearer token (held in
// a module variable set by the auth store — avoids a store↔api import cycle).

import axios, { type AxiosInstance } from 'axios'

import type {
  AuditEvent,
  Availability,
  Booking,
  CatalogSession,
  Child,
  ChildCreate,
  Flag,
  Hold,
  ImpersonationMode,
  ImpersonationSession,
  ImpersonationToken,
  InsuranceDoc,
  Notification,
  Order,
  Org,
  OrgAdmin,
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
  SettingItem,
  SettingVersion,
  TokenResponse,
  User,
  UserSummary,
  Venue,
  VerificationStatus,
  WwccRecord,
} from '@/lib/types'

let authToken: string | null = null
export function setAuthToken(token: string | null): void {
  authToken = token
}

const http: AxiosInstance = axios.create({ baseURL: '/api/v1', timeout: 15000 })

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
  },
  notifications: {
    async list(): Promise<Notification[]> {
      const { data } = await http.get<Notification[]>('/notifications')
      return data
    },
  },
  payments: {
    async payouts(organisationId: string): Promise<Payout[]> {
      const { data } = await http.get<Payout[]>('/payments/payouts', {
        params: { organisation_id: organisationId },
      })
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
  admin: {
    async users(q: string): Promise<UserSummary[]> {
      const { data } = await http.get<UserSummary[]>('/admin/users', { params: { q } })
      return data
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
