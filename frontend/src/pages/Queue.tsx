import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import type { Download } from '@/lib/types'

function fmt(bytes?: number) {
  if (!bytes) return '—'
  const gb = bytes / 1e9
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1e6).toFixed(0)} MB`
}

function statusColor(status: string) {
  if (status === 'replaced' || status === 'completed') return 'bg-green-500'
  if (status === 'failed') return 'bg-red-500'
  if (status === 'downloading') return 'bg-brand-green animate-pulse'
  return 'bg-blue-500'
}

interface ProgressData {
  download_id: number
  progress_pct: number
  speed?: string
  timeleft?: string
}

export default function Queue() {
  const [active, setActive] = useState<Download[]>([])
  const [recent, setRecent] = useState<Download[]>([])
  const [progress, setProgress] = useState<Record<number, ProgressData>>({})

  const loadActive = () => api.activeDownloads().then(setActive).catch(() => {})
  const loadRecent = () => api.recentDownloads(20).then(setRecent).catch(() => {})

  useEffect(() => {
    loadActive()
    loadRecent()
    // Fallback polling in case socket is unavailable
    const iv = setInterval(loadActive, 15000)
    return () => clearInterval(iv)
  }, [])

  // Real-time events
  useSocket('download:started', () => { loadActive(); loadRecent() })
  useSocket('download:completed', () => { loadActive(); loadRecent() })
  useSocket('download:failed', () => { loadActive(); loadRecent() })
  useSocket('download:progress', (data) => {
    const d = data as ProgressData
    setProgress((prev) => ({ ...prev, [d.download_id]: d }))
    // Update the progress_pct on the matching active download
    setActive((prev) =>
      prev.map((dl) =>
        dl.id === d.download_id ? { ...dl, progress_pct: d.progress_pct } : dl
      )
    )
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Queue</h1>

      {/* Active downloads */}
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
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium truncate flex-1 mr-4">{d.release_title ?? '—'}</p>
                    <span className="text-xs text-gray-400 shrink-0">{fmt(d.expected_size)}</span>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-green transition-all duration-500"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <div className="flex justify-between mt-1 text-xs text-gray-400">
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

      {/* Recent */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Recent ({recent.length})</div>
        <div className="divide-y divide-gray-800">
          {recent.length === 0 && (
            <p className="px-4 py-4 text-gray-500 text-sm">No recent downloads.</p>
          )}
          {recent.map((d) => (
            <div key={d.id} className="px-4 py-3 flex items-center gap-4 text-sm">
              <div className={`w-2 h-2 rounded-full shrink-0 ${statusColor(d.status)}`} />
              <p className="flex-1 truncate">{d.release_title ?? '—'}</p>
              <span className="capitalize text-gray-400 text-xs">{d.status}</span>
              <span className="text-gray-500 text-xs">{fmt(d.expected_size)}</span>
              {d.error_message && (
                <span className="text-red-400 text-xs truncate max-w-32" title={d.error_message}>
                  {d.error_message}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
