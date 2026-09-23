import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { useFilters } from '../src/hooks/use-filters'

const DEFAULTS = { page: '1', status: '', sort: 'created_at' }

function wrapper(initial: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  )
}

describe('filters in the url', () => {
  it('starts from the defaults when the url is bare', () => {
    const { result } = renderHook(() => useFilters(DEFAULTS), { wrapper: wrapper('/shipments') })

    expect(result.current.values).toEqual(DEFAULTS)
  })

  it('reads what the url already says, so a shared link opens the same view', () => {
    const { result } = renderHook(() => useFilters(DEFAULTS), {
      wrapper: wrapper('/shipments?status=delayed&page=3'),
    })

    expect(result.current.values.status).toBe('delayed')
    expect(result.current.values.page).toBe('3')
  })

  it('returns to the first page when a filter changes', () => {
    // Staying on page 3 of a different result set shows an empty table.
    const { result } = renderHook(() => useFilters(DEFAULTS), {
      wrapper: wrapper('/shipments?page=3'),
    })

    act(() => result.current.setFilter('status', 'delayed'))

    expect(result.current.values.page).toBe('1')
    expect(result.current.values.status).toBe('delayed')
  })

  it('keeps the page when the page itself changes', () => {
    const { result } = renderHook(() => useFilters(DEFAULTS), {
      wrapper: wrapper('/shipments?status=delayed'),
    })

    act(() => result.current.setFilter('page', '2'))

    expect(result.current.values.page).toBe('2')
    expect(result.current.values.status).toBe('delayed')
  })

  it('drops a filter set back to its default rather than leaving it in the url', () => {
    const { result } = renderHook(() => useFilters(DEFAULTS), {
      wrapper: wrapper('/shipments?status=delayed'),
    })

    act(() => result.current.setFilter('status', ''))

    expect(result.current.values.status).toBe('')
  })

  it('clears everything at once', () => {
    const { result } = renderHook(() => useFilters(DEFAULTS), {
      wrapper: wrapper('/shipments?status=delayed&page=4&sort=eta'),
    })

    act(() => result.current.reset())

    expect(result.current.values).toEqual(DEFAULTS)
  })
})
