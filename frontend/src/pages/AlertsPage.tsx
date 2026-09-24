import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { alerts } from '../api'
import { Badge, Button, Card, EmptyState, Skeleton } from '../components/ui'
import { useAuth } from '../hooks/auth-context'
import { useFilters } from '../hooks/use-filters'
import { can } from '../lib/permissions'
import { day } from '../lib/format'
import { qk } from '../lib/query-keys'

const DEFAULTS = { page: '1', unread_only: '' }

const SEVERITY_TONE = {
  low: 'neutral',
  medium: 'warn',
  high: 'bad',
  critical: 'bad',
} as const

export default function AlertsPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const { values, setFilter } = useFilters(DEFAULTS)

  const params = {
    page: Number(values.page),
    size: 25,
    ...(values.unread_only === 'true' && { unread_only: true }),
  }
  const query = useQuery({ queryKey: qk.alerts(params), queryFn: () => alerts.list(params) })

  const markAll = useMutation({
    mutationFn: alerts.markAllRead,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Alerts</h1>
          <p className="text-sm text-(--color-ink-muted)">
            Raised when a shipment slips or a supplier drifts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={values.unread_only === 'true'}
              onChange={(event) => setFilter('unread_only', event.target.checked ? 'true' : '')}
            />
            Unread only
          </label>
          {can(user?.role, 'alert:write') && (
            <Button variant="ghost" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
              Mark all read
            </Button>
          )}
        </div>
      </header>

      <Card>
        {query.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : !query.data?.items.length ? (
          <EmptyState title="No alerts" hint="Nothing has slipped in this workspace." />
        ) : (
          <ul className="flex flex-col divide-y divide-black/5">
            {query.data.items.map((alert) => (
              <li key={alert.id} className="flex items-start gap-3 py-3">
                <Badge tone={SEVERITY_TONE[alert.severity]}>{alert.severity}</Badge>
                <div className="min-w-0 flex-1">
                  <p className={alert.is_read ? 'text-(--color-ink-muted)' : 'font-medium'}>
                    {alert.title}
                  </p>
                  {alert.body && <p className="text-sm text-(--color-ink-muted)">{alert.body}</p>}
                </div>
                <span className="shrink-0 text-xs text-(--color-ink-muted)">
                  {day(alert.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

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
    </div>
  )
}
