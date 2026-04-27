import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import { useSocket } from '@/hooks/useSocket'
import type { Download } from '@/lib/types'

function fmt(bytes?: number) {
  if (!bytes) return '—'
  const gb = bytes / 1e9
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1e6).toFixed(0)} MB`
}

function cleanupStatusColor(status?: string) {
  if (status === 'cleaned') return 'text-green-400'
  if (status === 'error') return 'text-red-400'
  return 'text-gray-400'
}

export default function FailedDownloads() {
  const [downloads, setDownloads] = useState<Download[]>([])
  const [loading, setLoading] = useState(true)
  const [actionInProgress, setActionInProgress] = useState<Record<number, string>>({})
  const { toast } = useToast()

  const loadFailed = async () => {
    try {
      const data = await api.failedDownloads()
      setDownloads(data as Download[])
    } catch {
      toast('Failed to load failed downloads', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFailed()
    // Fallback polling
    const iv = setInterval(loadFailed, 30000)
    return () => clearInterval(iv)
  }, [])

  // Real-time events
  useSocket('download:failed', () => { loadFailed() })
  useSocket('download:cleanup', () => { loadFailed() })

  const handleCleanup = async (downloadId: number) => {
    setActionInProgress((prev) => ({ ...prev, [downloadId]: 'cleanup' }))
    try {
      await api.cleanupFailedDownload(downloadId)
      toast('Cleanup initiated', 'success')
      await loadFailed()
    } catch {
      toast('Cleanup failed', 'error')
    } finally {
      setActionInProgress((prev) => {
        const next = { ...prev }
        delete next[downloadId]
        return next
      })
    }
  }

  const handleRetry = async (downloadId: number) => {
    setActionInProgress((prev) => ({ ...prev, [downloadId]: 'retry' }))
    try {
      const res = await api.retryFailedDownload(downloadId) as { success: boolean; message?: string }
      if (res.success) {
        toast(res.message || 'Retry queued', 'success')
      } else {
        toast(res.message || 'Retry rejected', 'error')
      }
      await loadFailed()
    } catch {
      toast('Retry failed', 'error')
    } finally {
      setActionInProgress((prev) => {
        const next = { ...prev }
        delete next[downloadId]
        return next
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-400">Loading failed downloads...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Failed Downloads</h1>

      {downloads.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-6 text-center">
          <p className="text-gray-400">No failed downloads</p>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">
            Failed Downloads ({downloads.length})
          </div>
          <div className="divide-y divide-gray-800">
            {downloads.map((dl) => (
              <div key={dl.id} className="px-4 py-4 space-y-3">
                {/* Title and basic info */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{dl.release_title ?? '—'}</p>
                    {dl.error_message && (
                      <p className="text-xs text-red-400 mt-1 line-clamp-2">{dl.error_message}</p>
                    )}
                  </div>
                  <span className="text-xs text-gray-400 shrink-0">{fmt(dl.expected_size)}</span>
                </div>

                {/* Storage path */}
                {dl.storage_path && (
                  <div className="text-xs text-gray-500 line-clamp-1 bg-gray-800 p-2 rounded">
                    Folder: {dl.storage_path}
                  </div>
                )}

                {/* Cleanup status */}
                <div className="text-xs flex items-center gap-2">
                  <span className="text-gray-400">Cleanup:</span>
                  <span className={cleanupStatusColor(dl.cleanup_status)}>
                    {dl.cleanup_status || 'pending'}
                  </span>
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => handleCleanup(dl.id)}
                    disabled={actionInProgress[dl.id] === 'cleanup'}
                    className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 rounded text-xs font-medium transition-colors"
                  >
                    {actionInProgress[dl.id] === 'cleanup' ? 'Cleaning...' : 'Clean Folder'}
                  </button>
                  <button
                    onClick={() => handleRetry(dl.id)}
                    disabled={actionInProgress[dl.id] === 'retry'}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded text-xs font-medium transition-colors"
                  >
                    {actionInProgress[dl.id] === 'retry' ? 'Retrying...' : 'Retry Search'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
