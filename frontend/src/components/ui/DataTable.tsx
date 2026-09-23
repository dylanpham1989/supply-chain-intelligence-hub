import type { ReactNode } from 'react'
import { Button, EmptyState, ErrorState, Skeleton } from './index'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  align?: 'left' | 'right'
  hideBelow?: 'sm' | 'md'
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  total: number
  page: number
  size: number
  onPageChange: (page: number) => void
  isPending?: boolean
  error?: Error | null
  onRetry?: () => void
  onRowClick?: (row: T) => void
  emptyTitle?: string
  emptyHint?: string
}

/**
 * Paging and sorting happen on the server, so this renders the page it is given
 * and never sorts in the browser. Fetching everything to sort it client side
 * stops working at the first customer with real data.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  total,
  page,
  size,
  onPageChange,
  isPending,
  error,
  onRetry,
  onRowClick,
  emptyTitle = 'Nothing here yet',
  emptyHint,
}: Props<T>) {
  const pages = Math.max(1, Math.ceil(total / size))

  if (error) return <ErrorState message={error.message} onRetry={onRetry} />

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-black/10 text-left text-xs tracking-wide text-(--color-ink-muted) uppercase">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cellClass(column, 'px-3 py-2 font-medium')}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 6 }, (_, index) => (
                  <tr key={index} className="border-b border-black/5">
                    {columns.map((column) => (
                      <td key={column.key} className={cellClass(column, 'px-3 py-3')}>
                        <Skeleton className="h-4 w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row) => (
                  <tr
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={
                      'border-b border-black/5 ' +
                      (onRowClick ? 'cursor-pointer hover:bg-black/5 dark:hover:bg-white/5' : '')
                    }
                  >
                    {columns.map((column) => (
                      <td key={column.key} className={cellClass(column, 'px-3 py-3')}>
                        {column.render(row)}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {!isPending && rows.length === 0 && <EmptyState title={emptyTitle} hint={emptyHint} />}

      {pages > 1 && (
        <nav className="mt-4 flex items-center justify-between gap-3" aria-label="Pagination">
          <p className="text-sm text-(--color-ink-muted)">
            Page {page} of {pages} · {total} total
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
              Previous
            </Button>
            <Button variant="ghost" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
              Next
            </Button>
          </div>
        </nav>
      )}
    </div>
  )
}

function cellClass<T>(column: Column<T>, base: string): string {
  return [
    base,
    column.align === 'right' ? 'text-right tabular-nums' : '',
    column.hideBelow === 'sm' ? 'hidden sm:table-cell' : '',
    column.hideBelow === 'md' ? 'hidden md:table-cell' : '',
  ]
    .filter(Boolean)
    .join(' ')
}
