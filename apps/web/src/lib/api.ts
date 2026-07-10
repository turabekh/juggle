// Typed API client. A single axios instance injects the bearer token (held in
// a module variable set by the auth store — avoids a store↔api import cycle).

import axios, { type AxiosInstance } from 'axios'

import type {
  AuditEvent,
  Availability,
  Booking,
  Child,
  ChildCreate,
  Flag,
  Hold,
  ImpersonationMode,
  ImpersonationSession,
  ImpersonationToken,
  Order,
  OrgAdmin,
  OrgStatus,
  SearchFilters,
  SearchResults,
  SessionDetail,
  SettingItem,
  SettingVersion,
  TokenResponse,
  User,
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
  },
  admin: {
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
