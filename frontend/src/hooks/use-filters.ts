import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

/**
 * Filters live in the url.
 *
 * A reload keeps them, the back button works, and a link to a filtered view is
 * just the address bar. Holding them in component state gives up all three.
 */
export function useFilters<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams()

  const values = useMemo(() => {
    const merged = { ...defaults }
    for (const key of Object.keys(defaults) as (keyof T)[]) {
      const found = params.get(String(key))
      if (found !== null) merged[key] = found as T[keyof T]
    }
    return merged
  }, [params, defaults])

  const setFilter = useCallback(
    (key: keyof T, value: string) => {
      const next = new URLSearchParams(params)
      if (value === '' || value === defaults[key]) next.delete(String(key))
      else next.set(String(key), value)
      // Changing a filter puts you back on the first page; staying on page 4 of
      // a different result set shows an empty table.
      if (key !== 'page') next.delete('page')
      setParams(next, { replace: true })
    },
    [params, setParams, defaults],
  )

  const reset = useCallback(() => setParams(new URLSearchParams()), [setParams])

  return { values, setFilter, reset }
}
