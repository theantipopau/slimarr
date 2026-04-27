import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { OrphanedDownload } from '@/lib/types'

function fmtAge(hours?: number) {
  if (hours === undefined || hours === null) return 'Unknown'
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  const rem = hours % 24
  return `${days}d ${rem}h`
}

export default function OrphanedDownloads() {
  const [orphans, setOrphans] = useState<OrphanedDownload[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<Record<number, boolean>>({})
  const { toast } = useToast()

  const load = async () => {
    try {
      const data = await api.orphanedDownloads()
      setOrphans(data as OrphanedDownload[])
    } catch {
      toast('Failed to load orphaned downloads', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const iv = setInterval(() => void load(), 30000)
    return () => clearInterval(iv)
  }, [])

  const handleCleanup = async (id: number) => {
    setBusy((prev) => ({ ...prev, [id]: true }))
    try {
      const res = await api.cleanupOrphanedDownload(id) as { success: boolean; message?: string }
      if (res.success) {
        toast('Orphan marked for cleanup', 'success')
      } else {
        toast(res.message || 'Cleanup failed', 'error')
      }
      await load()
    } catch {
      toast('Cleanup failed', 'error')
    } finally {
      setBusy((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
  }

  if (loading) {
    return <div className="text-gray-400">Loading orphaned downloads...</div>
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Orphaned Downloads</h1>
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">
          Orphans ({orphans.length})
        </div>
        {orphans.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-400">No orphaned downloads found.</p>
        ) : (
          <div className="divide-y divide-gray-800">
            {orphans.map((o) => (
              <div key={o.id} className="px-4 py-4 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium truncate">{o.release_name || 'Unknown release'}</p>
                  <span className="text-xs text-gray-400">{o.downloader_name}</span>
                </div>
                <p className="text-xs text-gray-500 break-all">Job ID: {o.downloader_job_id}</p>
                {o.storage_path && (
                  <p className="text-xs text-gray-500 break-all">Path: {o.storage_path}</p>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Age: {fmtAge(o.age_hours)}</span>
                  <button
                    onClick={() => handleCleanup(o.id)}
                    disabled={busy[o.id]}
                    className="px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-xs disabled:opacity-50"
                  >
                    {busy[o.id] ? 'Marking...' : 'Mark Cleanup'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
