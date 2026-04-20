import { useState, useCallback } from 'react'

export function useApi<T>(fn: (...args: unknown[]) => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const execute = useCallback(
    async (...args: unknown[]) => {
      setLoading(true)
      setError(null)
      try {
        const result = await fn(...args)
        setData(result)
        return result
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ?? (e as { message?: string })?.message ?? 'Error'
        setError(msg)
        throw e
      } finally {
        setLoading(false)
      }
    },
    [fn]
  )

  return { data, loading, error, execute }
}
