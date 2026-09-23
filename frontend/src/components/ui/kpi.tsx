import type { ReactNode } from 'react'
import { Skeleton } from './index'

export function KpiCard({
  label,
  value,
  hint,
  tone,
  isPending,
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'ok' | 'warn' | 'bad'
  isPending?: boolean
}) {
  const color =
    tone === 'ok'
      ? 'text-(--color-ok)'
      : tone === 'warn'
        ? 'text-(--color-warn)'
        : tone === 'bad'
          ? 'text-(--color-bad)'
          : ''

  return (
    <div className="rounded-xl bg-(--color-surface-raised) p-4 shadow-sm ring-1 ring-black/5">
      <p className="text-xs tracking-wide text-(--color-ink-muted) uppercase">{label}</p>
      {isPending ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-(--color-ink-muted)">{hint}</p>}
    </div>
  )
}
