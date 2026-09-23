import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { shipments } from '../api'
import { Button, Card, Input, Select } from '../components/ui'
import { DataTable, type Column } from '../components/ui/DataTable'
import { ShipmentStatusBadge } from '../components/ui/status'
import { useDebounced } from '../hooks/use-debounce'
import { useFilters } from '../hooks/use-filters'
import { day, money } from '../lib/format'
import { qk } from '../lib/query-keys'
import type { Shipment } from '../types'

const DEFAULTS = {
  page: '1',
  status: '',
  mode: '',
  dest_country: '',
  late_only: '',
  search: '',
  sort: 'created_at',
  order: 'desc',
}

const STATUSES = ['planned', 'in_transit', 'delivered', 'delayed', 'cancelled']
const MODES = ['air', 'ocean', 'road', 'rail']

const columns: Column<Shipment>[] = [
  {
    key: 'reference',
    header: 'Reference',
    render: (s) => <span className="font-medium">{s.reference}</span>,
  },
  { key: 'lane', header: 'Lane', render: (s) => `${s.origin_country} → ${s.dest_country}` },
  { key: 'mode', header: 'Mode', hideBelow: 'sm', render: (s) => s.mode },
  { key: 'eta', header: 'ETA', hideBelow: 'sm', render: (s) => day(s.eta) },
  { key: 'ata', header: 'Arrived', hideBelow: 'md', render: (s) => day(s.ata) },
  {
    key: 'delay',
    header: 'Slip',
    align: 'right',
    hideBelow: 'md',
    render: (s) =>
      s.delay_days == null ? (
        '—'
      ) : (
        <span className={s.delay_days > 0 ? 'text-(--color-bad)' : 'text-(--color-ok)'}>
          {s.delay_days > 0 ? `+${s.delay_days}d` : `${s.delay_days}d`}
        </span>
      ),
  },
  { key: 'value', header: 'Value', align: 'right', render: (s) => money(s.value_usd) },
  { key: 'status', header: 'Status', render: (s) => <ShipmentStatusBadge status={s.status} /> },
]

export default function ShipmentsPage() {
  const { values, setFilter, reset } = useFilters(DEFAULTS)
  const [searchInput, setSearchInput] = useState(values.search)
  const search = useDebounced(searchInput)

  const params = {
    page: Number(values.page),
    size: 25,
    sort: values.sort,
    order: values.order,
    ...(values.status && { status: values.status }),
    ...(values.mode && { mode: values.mode }),
    ...(values.dest_country && { dest_country: values.dest_country }),
    ...(values.late_only === 'true' && { late_only: true }),
    ...(search && { search }),
  }

  const query = useQuery({
    queryKey: qk.shipments(params),
    queryFn: () => shipments.list(params),
    placeholderData: (previous) => previous,
  })

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Shipments</h1>
        <p className="text-sm text-(--color-ink-muted)">
          Filters live in the address bar, so this view can be shared or reloaded.
        </p>
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Search</span>
            <Input
              value={searchInput}
              placeholder="Reference or country"
              onChange={(event) => {
                setSearchInput(event.target.value)
                setFilter('search', event.target.value)
              }}
            />
          </label>

          <Field label="Status">
            <Select value={values.status} onChange={(e) => setFilter('status', e.target.value)}>
              <option value="">Any</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Mode">
            <Select value={values.mode} onChange={(e) => setFilter('mode', e.target.value)}>
              <option value="">Any</option>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Sort">
            <Select
              value={`${values.sort}:${values.order}`}
              onChange={(e) => {
                const [sort = 'created_at', order = 'desc'] = e.target.value.split(':')
                setFilter('sort', sort)
                setFilter('order', order)
              }}
            >
              <option value="created_at:desc">Newest</option>
              <option value="eta:asc">ETA soonest</option>
              <option value="value_usd:desc">Highest value</option>
              <option value="reference:asc">Reference</option>
            </Select>
          </Field>

          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={values.late_only === 'true'}
              onChange={(e) => setFilter('late_only', e.target.checked ? 'true' : '')}
            />
            Late only
          </label>

          <Button
            variant="ghost"
            onClick={() => {
              setSearchInput('')
              reset()
            }}
          >
            Clear
          </Button>
        </div>
      </Card>

      <Card>
        <DataTable
          columns={columns}
          rows={query.data?.items ?? []}
          rowKey={(s) => s.id}
          total={query.data?.total ?? 0}
          page={Number(values.page)}
          size={25}
          onPageChange={(page) => setFilter('page', String(page))}
          isPending={query.isPending}
          error={query.error}
          onRetry={() => void query.refetch()}
          emptyTitle="No shipments match"
          emptyHint="Try clearing a filter, or upload a manifest to import some."
        />
      </Card>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-(--color-ink-muted)">{label}</span>
      {children}
    </label>
  )
}
