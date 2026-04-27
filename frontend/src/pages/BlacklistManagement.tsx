import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { BlacklistEntry } from '@/lib/types'

export default function BlacklistManagement() {
  const [entries, setEntries] = useState<BlacklistEntry[]>([])
  const [releaseTitle, setReleaseTitle] = useState('')
  const [reason, setReason] = useState('manual')
  const [loading, setLoading] = useState(true)
  const { toast } = useToast()

  const load = async () => {
    try {
      const data = await api.getBlacklist()
      setEntries(data as BlacklistEntry[])
    } catch {
      toast('Failed to load blacklist', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const addEntry = async () => {
    if (!releaseTitle.trim()) {
      toast('Enter a release title', 'error')
      return
    }
    try {
      await api.addBlacklistEntry({
        release_title: releaseTitle.trim(),
        reason,
        expires_in_days: 30,
      })
      setReleaseTitle('')
      toast('Blacklist entry added', 'success')
      await load()
    } catch {
      toast('Failed to add blacklist entry', 'error')
    }
  }

  const removeEntry = async (hash: string) => {
    try {
      await api.removeBlacklistEntry(hash)
      toast('Blacklist entry removed', 'success')
      await load()
    } catch {
      toast('Failed to remove blacklist entry', 'error')
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Blacklist</h1>

      <div className="bg-gray-900 rounded-xl p-4 space-y-3">
        <h2 className="text-sm font-semibold">Add Entry</h2>
        <input
          value={releaseTitle}
          onChange={(e) => setReleaseTitle(e.target.value)}
          placeholder="Release title"
          className="w-full px-3 py-2 rounded bg-gray-800 border border-gray-700 text-sm"
        />
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason"
          className="w-full px-3 py-2 rounded bg-gray-800 border border-gray-700 text-sm"
        />
        <button
          onClick={addEntry}
          className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm"
        >
          Add to Blacklist
        </button>
      </div>

      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">
          Entries ({entries.length})
        </div>
        {loading ? (
          <p className="px-4 py-6 text-sm text-gray-400">Loading...</p>
        ) : entries.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-400">No blacklist entries.</p>
        ) : (
          <div className="divide-y divide-gray-800">
            {entries.map((e) => (
              <div key={e.id} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm truncate">{e.release_title}</p>
                  <p className="text-xs text-gray-400">{e.reason || 'n/a'}</p>
                </div>
                <button
                  onClick={() => removeEntry(e.release_hash)}
                  className="px-3 py-1 rounded bg-red-700 hover:bg-red-600 text-xs"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
