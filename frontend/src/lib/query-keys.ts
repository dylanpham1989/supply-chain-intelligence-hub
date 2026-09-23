// Everything that changes a response belongs in its key. A filter left out is a
// list that does not refetch when the filter changes, which reads as stale data
// with no obvious cause.
export const qk = {
  me: ['me'] as const,
  users: (page: number) => ['users', page] as const,
  shipments: (params: Record<string, unknown>) => ['shipments', params] as const,
  shipment: (id: string) => ['shipment', id] as const,
  suppliers: (params: Record<string, unknown>) => ['suppliers', params] as const,
  supplierPerformance: (id: string) => ['supplier-performance', id] as const,
  documents: (params: Record<string, unknown>) => ['documents', params] as const,
  document: (id: string) => ['document', id] as const,
  chunks: (id: string) => ['chunks', id] as const,
  alerts: (params: Record<string, unknown>) => ['alerts', params] as const,
  unreadCount: ['alerts', 'unread-count'] as const,
  insights: (page: number) => ['insights', page] as const,
  analytics: {
    all: ['analytics'] as const,
    summary: (days: number) => ['analytics', 'summary', days] as const,
    byStatus: (days: number) => ['analytics', 'by-status', days] as const,
    timeseries: (days: number) => ['analytics', 'timeseries', days] as const,
    topSuppliers: (limit: number) => ['analytics', 'top-suppliers', limit] as const,
    risk: (days: number) => ['analytics', 'risk', days] as const,
  },
}
