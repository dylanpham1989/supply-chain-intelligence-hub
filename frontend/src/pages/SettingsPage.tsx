import { useQuery } from '@tanstack/react-query'
import { users } from '../api'
import { Badge, Card, Skeleton } from '../components/ui'
import { DataTable, type Column } from '../components/ui/DataTable'
import { useFilters } from '../hooks/use-filters'
import { day } from '../lib/format'
import { qk } from '../lib/query-keys'
import type { User } from '../types'

const DEFAULTS = { page: '1' }

const columns: Column<User>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (u) => <span className="font-medium">{u.full_name}</span>,
  },
  { key: 'email', header: 'Email', render: (u) => u.email },
  { key: 'role', header: 'Role', render: (u) => <Badge>{u.role}</Badge> },
  {
    key: 'active',
    header: 'Status',
    render: (u) => (
      <Badge tone={u.is_active ? 'ok' : 'neutral'}>{u.is_active ? 'active' : 'disabled'}</Badge>
    ),
  },
  { key: 'last', header: 'Last sign in', hideBelow: 'md', render: (u) => day(u.last_login_at) },
]

export default function SettingsPage() {
  const { values, setFilter } = useFilters(DEFAULTS)
  const page = Number(values.page)
  const query = useQuery({ queryKey: qk.users(page), queryFn: () => users.list(page) })

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-(--color-ink-muted)">People with access to this workspace.</p>
      </header>

      <Card title="Users">
        {query.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <DataTable
            columns={columns}
            rows={query.data?.items ?? []}
            rowKey={(u) => u.id}
            total={query.data?.total ?? 0}
            page={page}
            size={50}
            onPageChange={(next) => setFilter('page', String(next))}
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        )}
      </Card>
    </div>
  )
}
