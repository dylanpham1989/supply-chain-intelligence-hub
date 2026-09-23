import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, Skeleton } from '../ui'
import { count } from '../../lib/format'

const PALETTE = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#22d3ee']
const AXIS = { fontSize: 11, fill: 'currentColor', opacity: 0.6 }

/**
 * ResponsiveContainer measures its parent, and a parent with no resolved height
 * measures zero, which renders nothing at all. The fixed height is the fix.
 */
export function ChartCard({
  title,
  isPending,
  isEmpty,
  children,
}: {
  title: string
  isPending?: boolean
  isEmpty?: boolean
  children: ReactNode
}) {
  return (
    <Card title={title}>
      <div className="h-[280px]">
        {isPending ? (
          <Skeleton className="h-full w-full" />
        ) : isEmpty ? (
          <div className="flex h-full items-center justify-center text-sm text-(--color-ink-muted)">
            Nothing to show yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {children as never}
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  )
}

export function ShipmentsOverTime({
  data,
}: {
  data: { month: string; shipments: number; late: number }[]
}) {
  return (
    <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
      <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
      <XAxis dataKey="month" tick={AXIS} tickLine={false} axisLine={false} />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} />
      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
      <Legend wrapperStyle={{ fontSize: 12 }} />
      <Line type="monotone" dataKey="shipments" stroke={PALETTE[0]} strokeWidth={2} dot={false} />
      <Line type="monotone" dataKey="late" stroke={PALETTE[3]} strokeWidth={2} dot={false} />
    </LineChart>
  )
}

export function ByStatus({ data }: { data: { status: string; shipments: number }[] }) {
  return (
    <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
      <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
      <XAxis
        dataKey="status"
        tick={AXIS}
        tickLine={false}
        axisLine={false}
        tickFormatter={(v: string) => v.replace(/_/g, ' ')}
      />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} />
      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
      <Bar dataKey="shipments" radius={[4, 4, 0, 0]}>
        {data.map((row, index) => (
          <Cell key={row.status} fill={PALETTE[index % PALETTE.length]} />
        ))}
      </Bar>
    </BarChart>
  )
}

export function RiskSplit({ data }: { data: { label: string; shipments: number }[] }) {
  return (
    <PieChart>
      <Pie data={data} dataKey="shipments" nameKey="label" innerRadius={55} outerRadius={85}>
        {data.map((row, index) => (
          <Cell key={row.label} fill={PALETTE[index % PALETTE.length]} />
        ))}
      </Pie>
      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
      <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: string) => v.replace(/_/g, ' ')} />
    </PieChart>
  )
}

export function TopSuppliersChart({
  data,
}: {
  data: { name: string; shipments: number; late: number }[]
}) {
  return (
    <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
      <CartesianGrid strokeDasharray="3 3" opacity={0.15} horizontal={false} />
      <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={count} />
      <YAxis
        type="category"
        dataKey="name"
        width={130}
        tick={AXIS}
        tickLine={false}
        axisLine={false}
      />
      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
      <Legend wrapperStyle={{ fontSize: 12 }} />
      <Bar dataKey="shipments" fill={PALETTE[0]} radius={[0, 4, 4, 0]} />
      <Bar dataKey="late" fill={PALETTE[3]} radius={[0, 4, 4, 0]} />
    </BarChart>
  )
}
