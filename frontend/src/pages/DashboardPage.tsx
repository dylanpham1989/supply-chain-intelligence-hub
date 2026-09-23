import { useQueries } from '@tanstack/react-query'
import { useState } from 'react'
import { analytics } from '../api'
import {
  ByStatus,
  ChartCard,
  RiskSplit,
  ShipmentsOverTime,
  TopSuppliersChart,
} from '../components/charts'
import { KpiCard } from '../components/ui/kpi'
import { Select } from '../components/ui'
import { compactMoney, count, days, rate } from '../lib/format'
import { qk } from '../lib/query-keys'

const WINDOWS = [
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last quarter' },
  { value: 365, label: 'Last year' },
]

export default function DashboardPage() {
  const [window, setWindow] = useState(365)

  // One batch, so the five panels load together instead of chaining five
  // round trips one component at a time.
  const [summary, byStatus, timeseries, topSuppliers, risk] = useQueries({
    queries: [
      { queryKey: qk.analytics.summary(window), queryFn: () => analytics.summary(window) },
      { queryKey: qk.analytics.byStatus(window), queryFn: () => analytics.byStatus(window) },
      { queryKey: qk.analytics.timeseries(window), queryFn: () => analytics.timeseries(window) },
      { queryKey: qk.analytics.topSuppliers(8), queryFn: () => analytics.topSuppliers(8) },
      { queryKey: qk.analytics.risk(window), queryFn: () => analytics.risk(window) },
    ],
  })

  const onTime = summary.data?.on_time_rate ?? null

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-(--color-ink-muted)">
            Shipment performance across the workspace.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-(--color-ink-muted)">Period</span>
          <Select value={window} onChange={(event) => setWindow(Number(event.target.value))}>
            {WINDOWS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </label>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard
          label="Shipments"
          value={count(summary.data?.total_shipments)}
          isPending={summary.isPending}
        />
        <KpiCard
          label="On time"
          value={rate(onTime)}
          tone={onTime == null ? undefined : onTime >= 0.9 ? 'ok' : onTime >= 0.75 ? 'warn' : 'bad'}
          isPending={summary.isPending}
        />
        <KpiCard
          label="Delayed"
          value={count(summary.data?.delayed)}
          hint={summary.data ? `${days(summary.data.avg_delay_days)} average slip` : undefined}
          tone={summary.data?.delayed ? 'bad' : undefined}
          isPending={summary.isPending}
        />
        <KpiCard
          label="Declared value"
          value={compactMoney(summary.data?.total_value_usd)}
          isPending={summary.isPending}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Shipments over time"
          isPending={timeseries.isPending}
          isEmpty={!timeseries.data?.items.length}
        >
          <ShipmentsOverTime data={timeseries.data?.items ?? []} />
        </ChartCard>

        <ChartCard
          title="By status"
          isPending={byStatus.isPending}
          isEmpty={!byStatus.data?.items.length}
        >
          <ByStatus data={byStatus.data?.items ?? []} />
        </ChartCard>

        <ChartCard
          title="Suppliers by volume"
          isPending={topSuppliers.isPending}
          isEmpty={!topSuppliers.data?.items.length}
        >
          <TopSuppliersChart data={topSuppliers.data?.items ?? []} />
        </ChartCard>

        <ChartCard title="Risk split" isPending={risk.isPending} isEmpty={!risk.data?.items.length}>
          <RiskSplit data={risk.data?.items ?? []} />
        </ChartCard>
      </div>
    </div>
  )
}
