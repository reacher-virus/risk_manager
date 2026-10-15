import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'

export interface Async<T> { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }

/** Run an async loader when `deps` change; keeps the last good data while reloading. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): Async<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loaderRef.current()
      .then((d) => { if (!cancelled) { setData(d); setError(null) } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, String(e))) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload: useCallback(() => setTick((t) => t + 1), []) }
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}
