import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DataTable, type Column } from '../src/components/ui/DataTable'

interface Row {
  id: string
  name: string
}

const columns: Column<Row>[] = [{ key: 'name', header: 'Name', render: (row) => row.name }]

const rows: Row[] = [
  { id: '1', name: 'First' },
  { id: '2', name: 'Second' },
]

const base = {
  columns,
  rowKey: (row: Row) => row.id,
  size: 25,
  onPageChange: () => {},
}

describe('DataTable', () => {
  it('renders a real table so a screen reader can navigate it', () => {
    render(<DataTable {...base} rows={rows} total={2} page={1} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })

  it('explains an empty result instead of showing a blank box', () => {
    render(
      <DataTable
        {...base}
        rows={[]}
        total={0}
        page={1}
        emptyTitle="No shipments match"
        emptyHint="Try clearing a filter"
      />,
    )

    expect(screen.getByText('No shipments match')).toBeInTheDocument()
    expect(screen.getByText('Try clearing a filter')).toBeInTheDocument()
  })

  it('shows placeholder rows while loading, not a spinner that shifts the layout', () => {
    const { container } = render(<DataTable {...base} rows={[]} total={0} page={1} isPending />)

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
    expect(screen.queryByText('Nothing here yet')).not.toBeInTheDocument()
  })

  it('offers a retry when the request failed', async () => {
    const onRetry = vi.fn()
    render(
      <DataTable
        {...base}
        rows={[]}
        total={0}
        page={1}
        error={new Error('Upstream unavailable')}
        onRetry={onRetry}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Upstream unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('hides paging when everything fits on one page', () => {
    render(<DataTable {...base} rows={rows} total={2} page={1} />)

    expect(screen.queryByRole('navigation', { name: 'Pagination' })).not.toBeInTheDocument()
  })

  it('pages through the server side result', async () => {
    const onPageChange = vi.fn()
    render(<DataTable {...base} rows={rows} total={60} page={2} onPageChange={onPageChange} />)

    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('does not offer a previous page from the first one', () => {
    render(<DataTable {...base} rows={rows} total={60} page={1} />)

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })
})
