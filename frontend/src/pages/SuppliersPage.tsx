import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { suppliers } from '../api'
import { Badge, Button, Card, EmptyState, Skeleton } from '../components/ui'
import { SidePanel } from '../components/ui/SidePanel'
import { useFilters } from '../hooks/use-filters'
import { days, rate } from '../lib/format'
import { qk } from '../lib/query-keys'
import type { Supplier } from '../types'

const DEFAULTS = { page: '1', sort: 'name', order: 'asc' }

export default function SuppliersPage() {
  const { values, setFilter } = useFilters(DEFAULTS)
  const [selected, setSelected] = useState<Supplier | null>(null)

  const params = { page: Number(values.page), size: 24, sort: values.sort, order: values.order }
  const query = useQuery({
    queryKey: qk.suppliers(params),
    queryFn: () => suppliers.list(params),
    placeholderData: (previous) => previous,
  })

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Suppliers</h1>
          <p className="text-sm text-(--color-ink-muted)">
            On-time rate is measured against the confirmed ETA.
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => setFilter('sort', values.sort === 'name' ? 'risk_score' : 'name')}
        >
          Sort by {values.sort === 'name' ? 'risk' : 'name'}
        </Button>
      </header>

      {query.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : !query.data?.items.length ? (
        <Card>
          <EmptyState
            title="No suppliers yet"
            hint="Importing a manifest creates them automatically."
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.items.map((supplier) => (
            <button
              key={supplier.id}
              onClick={() => setSelected(supplier)}
              className="rounded-xl bg-(--color-surface-raised) p-4 text-left shadow-sm ring-1 ring-black/5 transition-colors hover:ring-(--color-accent)/40"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">{supplier.name}</p>
                <Badge tone={toneFor(supplier.on_time_rate)}>
                  {rate(numberOr(supplier.on_time_rate))}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-(--color-ink-muted)">
                {supplier.country} · {supplier.category}
              </p>
            </button>
          ))}
        </div>
      )}

      {query.data && query.data.pages > 1 && (
        <nav className="flex justify-end gap-2" aria-label="Pagination">
          <Button
            variant="ghost"
            disabled={Number(values.page) <= 1}
            onClick={() => setFilter('page', String(Number(values.page) - 1))}
          >
            Previous
          </Button>
          <Button
            variant="ghost"
            disabled={Number(values.page) >= query.data.pages}
            onClick={() => setFilter('page', String(Number(values.page) + 1))}
          >
            Next
          </Button>
        </nav>
      )}

      {selected && <PerformancePanel supplier={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function PerformancePanel({ supplier, onClose }: { supplier: Supplier; onClose: () => void }) {
  const query = useQuery({
    queryKey: qk.supplierPerformance(supplier.id),
    queryFn: () => suppliers.performance(supplier.id),
  })

  return (
    <SidePanel
      title={supplier.name}
      subtitle={`${supplier.country} · ${supplier.category}`}
      onClose={onClose}
    >
      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : query.data ? (
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="Shipments" value={String(query.data.shipments)} />
            <Stat label="Delivered" value={String(query.data.delivered)} />
            <Stat label="Late" value={String(query.data.late)} />
            <Stat label="On time" value={rate(query.data.on_time_rate)} />
            <Stat label="Average slip" value={days(query.data.avg_delay_days)} />
          </dl>

          {query.data.monthly.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs tracking-wide text-(--color-ink-muted) uppercase">
                By month
              </h3>
              <ul className="flex flex-col gap-1 text-sm">
                {query.data.monthly.map((month) => (
                  <li key={month.month} className="flex justify-between">
                    <span className="text-(--color-ink-muted)">{month.month}</span>
                    <span className="tabular-nums">
                      {month.shipments} shipments
                      {month.late > 0 && (
                        <span className="text-(--color-bad)"> · {month.late} late</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : null}
    </SidePanel>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-(--color-ink-muted)">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  )
}

const numberOr = (value: string | null) => (value == null ? null : Number(value))

function toneFor(value: string | null): 'ok' | 'warn' | 'bad' | 'neutral' {
  const rateValue = numberOr(value)
  if (rateValue == null) return 'neutral'
  if (rateValue >= 0.9) return 'ok'
  if (rateValue >= 0.75) return 'warn'
  return 'bad'
}
