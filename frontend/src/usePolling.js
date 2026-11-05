import { useCallback, useEffect, useRef, useState } from 'react'

// ADR-06: the frontend refreshes its data by polling every 5 minutes.
export const POLL_INTERVAL_MS = 5 * 60 * 1000

/**
 * Calls `load` now, whenever `deps` change and every `interval` ms.
 * Keeps the last good data when a refresh fails.
 */
export function usePolling(load, deps = [], interval = POLL_INTERVAL_MS) {
  const [state, setState] = useState({ data: null, error: null, loading: true, updatedAt: null })
  const loadRef = useRef(load)
  loadRef.current = load

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }))
    try {
      const data = await loadRef.current()
      setState({ data, error: null, loading: false, updatedAt: new Date() })
    } catch (error) {
      setState((s) => ({ ...s, error, loading: false }))
    }
  }, [])

  useEffect(() => {
    setState({ data: null, error: null, loading: true, updatedAt: null })
    refresh()
    const timer = setInterval(refresh, interval)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, interval, refresh])

  return { ...state, refresh }
}
