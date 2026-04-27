import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import type { Download } from '@/lib/types'
import { Clock, RefreshCw } from 'lucide-react'

function fmt(bytes?: number) {
  if (!bytes) return '-'
  const gb = bytes / 1e9
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1e6).toFixed(0)} MB`
}

function statusColor(status: string) {
  if (status === 'replaced' || status === 'completed') return 'bg-green-500'
  if (status === 'failed') return 'bg-red-500'
  if (status === 'downloading') return 'bg-brand-green animate-pulse'
  return 'bg-blue-500'
}

function fmtDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

interface ProgressData {
  download_id: number
  progress_pct: number
  speed?: string
  timeleft?: string
}

type StatusFilter = 'all' | 'completed' | 'failed' | 'downloading'

export default function Queue() {
  const [active, setActive] = useState<Download[]>([])
  const [recent, setRecent] = useState<Download[]>([])
  const [progress, setProgress] = useState<Record<number, ProgressData>>({})
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const loadQueue = async () => {
    try {
      const [activeRows, recentRows] = await Promise.all([
        api.activeDownloads(),
        api.recentDownloads(50),
      ])
      setActive(activeRows as Download[])
      setRecent(recentRows as Download[])
      setLastUpdated(new Date())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadQueue()
    const iv = window.setInterval(() => { void loadQueue() }, 15000)
    return () => window.clearInterval(iv)
  }, [])

  useSocket('download:started', () => { void loadQueue() })
  useSocket('download:completed', () => { void loadQueue() })
  useSocket('download:failed', () => { void loadQueue() })
  useSocket('download:cleanup', () => { void loadQueue() })
  useSocket('download:progress', (data) => {
    const d = data as ProgressData
    setProgress((prev) => ({ ...prev, [d.download_id]: d }))
    setActive((prev) =>
      prev.map((dl) =>
        dl.id === d.download_id ? { ...dl, progress_pct: d.progress_pct } : dl
      )
    )
  })

  const summary = useMemo(() => {
    const failed = recent.filter((item) => item.status === 'failed').length
    const completed = recent.filter((item) => item.status === 'completed' || item.status === 'replaced').length
    return { failed, completed, active: active.length }
  }, [active.length, recent])

  const filteredRecent = useMemo(() => {
    if (statusFilter === 'all') return recent
    if (statusFilter === 'completed') {
      return recent.filter((item) => item.status === 'completed' || item.status === 'replaced')
    }
    return recent.filter((item) => item.status === statusFilter)
  }, [recent, statusFilter])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Queue</h1>
          <p className="text-xs text-gray-500 mt-1">
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : loading ? 'Loading queue...' : 'Queue not refreshed yet'}
          </p>
        </div>
        <button
          onClick={() => { void loadQueue() }}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-sm hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Active</p>
          <p className="text-xl font-semibold">{summary.active}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Completed</p>
          <p className="text-xl font-semibold">{summary.completed}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Failed</p>
          <p className="text-xl font-semibold">{summary.failed}</p>
        </div>
      </div>

      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">
          Active Downloads ({active.length})
        </div>
        {active.length === 0 ? (
          <p className="px-4 py-4 text-gray-500 text-sm">No active downloads.</p>
        ) : (
          <div className="divide-y divide-gray-800">
            {active.map((d) => {
              const live = progress[d.id]
              const pct = live?.progress_pct ?? d.progress_pct ?? 0
              return (
                <div key={d.id} className="px-4 py-4">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4 mb-2">
                    <p className="text-sm font-medium break-words min-w-0">{d.release_title ?? '-'}</p>
                    <span className="text-xs text-gray-400 shrink-0">{fmt(d.expected_size)}</span>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-green transition-all duration-500"
                      style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                    />
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 justify-between mt-1 text-xs text-gray-400">
                    <span>{pct.toFixed(1)}%</span>
                    {live?.speed && <span>{live.speed}</span>}
                    {live?.timeleft && <span>ETA {live.timeleft}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm font-semibold">Recent ({filteredRecent.length})</span>
          <div className="flex flex-wrap gap-2">
            {(['all', 'completed', 'failed', 'downloading'] as StatusFilter[]).map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`px-2.5 py-1 rounded-md text-xs capitalize ${
                  statusFilter === status
                    ? 'bg-brand-green text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {status}
              </button>
            ))}
          </div>
        </div>
        <div className="divide-y divide-gray-800">
          {filteredRecent.length === 0 && (
            <p className="px-4 py-4 text-gray-500 text-sm">No downloads match this filter.</p>
          )}
          {filteredRecent.map((d) => (
            <div key={d.id} className="px-4 py-3 flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:gap-4">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <div className={`w-2 h-2 rounded-full shrink-0 ${statusColor(d.status)}`} />
                <p className="break-words min-w-0">{d.release_title ?? '-'}</p>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 sm:justify-end">
                <span className="capitalize text-gray-400">{d.status}</span>
                <span>{fmt(d.expected_size)}</span>
                {(d.completed_at || d.started_at) && (
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    {fmtDate(d.completed_at || d.started_at)}
                  </span>
                )}
                {d.error_message && (
                  <span className="text-red-400 max-w-full sm:max-w-48 truncate" title={d.error_message}>
                    {d.error_message}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
