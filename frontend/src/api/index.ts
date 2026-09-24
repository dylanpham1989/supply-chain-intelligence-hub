import { api } from '../lib/api-client'
import type {
  Alert,
  AskResponse,
  Chunk,
  Document,
  Insight,
  Page,
  RiskBreakdown,
  Shipment,
  StatusBreakdown,
  Summary,
  Supplier,
  SupplierPerformance,
  Timeseries,
  TokenResponse,
  TopSuppliers,
  User,
} from '../types'

const v1 = '/api/v1'

export const auth = {
  login: (body: { tenant_slug: string; email: string; password: string }) =>
    api.post<TokenResponse>(`${v1}/auth/login`, body).then((r) => r.data),
  signup: (body: {
    company_name: string
    tenant_slug: string
    email: string
    password: string
    full_name: string
  }) => api.post<TokenResponse>(`${v1}/auth/signup`, body).then((r) => r.data),
  refresh: () => api.post<TokenResponse>(`${v1}/auth/refresh`).then((r) => r.data),
  logout: () => api.post(`${v1}/auth/logout`).then(() => undefined),
  me: () => api.get<User>(`${v1}/auth/me`).then((r) => r.data),
}

export const shipments = {
  list: (params: Record<string, unknown>) =>
    api.get<Page<Shipment>>(`${v1}/shipments`, { params }).then((r) => r.data),
  get: (id: string) => api.get<Shipment>(`${v1}/shipments/${id}`).then((r) => r.data),
}

export const suppliers = {
  list: (params: Record<string, unknown>) =>
    api.get<Page<Supplier>>(`${v1}/suppliers`, { params }).then((r) => r.data),
  performance: (id: string) =>
    api.get<SupplierPerformance>(`${v1}/suppliers/${id}/performance`).then((r) => r.data),
}

export const documents = {
  list: (params: Record<string, unknown>) =>
    api.get<Page<Document>>(`${v1}/documents`, { params }).then((r) => r.data),
  get: (id: string) => api.get<Document>(`${v1}/documents/${id}`).then((r) => r.data),
  chunks: (id: string) =>
    api
      .get<Page<Chunk>>(`${v1}/documents/${id}/chunks`, { params: { size: 200 } })
      .then((r) => r.data),
  upload: (file: File, docType: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('doc_type', docType)
    return api
      .post<{ document_id: string; status: string }>(`${v1}/documents`, form)
      .then((r) => r.data)
  },
}

export const alerts = {
  list: (params: Record<string, unknown>) =>
    api.get<Page<Alert>>(`${v1}/alerts`, { params }).then((r) => r.data),
  unreadCount: () =>
    api.get<{ unread: number }>(`${v1}/alerts/unread-count`).then((r) => r.data.unread),
  markAllRead: () => api.post(`${v1}/alerts/read-all`).then(() => undefined),
}

export const analytics = {
  summary: (days: number) =>
    api.get<Summary>(`${v1}/analytics/summary`, { params: { days } }).then((r) => r.data),
  byStatus: (days: number) =>
    api
      .get<StatusBreakdown>(`${v1}/analytics/shipments-by-status`, { params: { days } })
      .then((r) => r.data),
  timeseries: (days: number) =>
    api
      .get<Timeseries>(`${v1}/analytics/shipments-timeseries`, { params: { days } })
      .then((r) => r.data),
  topSuppliers: (limit: number) =>
    api
      .get<TopSuppliers>(`${v1}/analytics/top-suppliers`, { params: { limit } })
      .then((r) => r.data),
  risk: (days: number) =>
    api
      .get<RiskBreakdown>(`${v1}/analytics/risk-breakdown`, { params: { days } })
      .then((r) => r.data),
}

export const insights = {
  ask: (question: string) => api.post<AskResponse>(`${v1}/ask`, { question }).then((r) => r.data),
  history: (page: number) =>
    api.get<Page<Insight>>(`${v1}/insights`, { params: { page } }).then((r) => r.data),
}

export const users = {
  list: (page: number) =>
    api.get<Page<User>>(`${v1}/users`, { params: { page } }).then((r) => r.data),
}
