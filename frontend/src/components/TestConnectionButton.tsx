import { useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  service: string
  label?: string
  body?: unknown
}

export default function TestConnectionButton({ service, label, body }: Props) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message?: string } | null>(null)

  const test = async () => {
    setLoading(true)
    setResult(null)
    try {
      const data = await api.testConnection(service, body)
      setResult({ success: data.success, message: data.error ?? JSON.stringify(data) })
    } catch {
      setResult({ success: false, message: 'Request failed' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={test}
        disabled={loading}
        className="px-3 py-1.5 rounded bg-brand-accent text-white text-sm disabled:opacity-50"
      >
        {loading ? 'Testing…' : label ?? 'Test Connection'}
      </button>
      {result && (
        <span className={result.success ? 'text-green-400 text-xs' : 'text-red-400 text-xs'}>
          {result.success ? '✓ Connected' : `✗ ${result.message}`}
        </span>
      )}
    </div>
  )
}
