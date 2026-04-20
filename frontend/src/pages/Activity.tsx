import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import type { ActivityEntry } from '@/lib/types'
import ActivityItem from '@/components/ActivityItem'

export default function Activity() {
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const PER_PAGE = 50

  const load = useCallback(() => {
    api.activity({ page, per_page: PER_PAGE })
      .then((d: { activity: ActivityEntry[]; total: number }) => {
        setActivity(d.activity)
        setTotal(d.total)
      })
      .catch(() => {})
  }, [page])

  useEffect(() => { load() }, [load])

  // Prepend live events on page 1
  useSocket('activity:new', (data) => {
    if (page === 1) {
      const entry = data as ActivityEntry
      setActivity((prev) => [entry, ...prev.slice(0, PER_PAGE - 1)])
      setTotal((t) => t + 1)
    }
  })
  useSocket('replace:completed', () => { if (page === 1) load() })

  const totalPages = Math.ceil(total / PER_PAGE)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold flex-1">Activity</h1>
        <span className="text-sm text-gray-400">{total} events</span>
      </div>
      <div className="bg-gray-900 rounded-xl p-5">
        {activity.length === 0 ? (
          <p className="text-gray-500 text-sm">No activity yet. Run a cycle or scan your library to get started.</p>
        ) : (
          <div className="divide-y divide-gray-800">
            {activity.map((e) => <ActivityItem key={e.id} entry={e} />)}
          </div>
        )}
      </div>
      {totalPages > 1 && (
        <div className="flex gap-2 justify-center">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1.5 rounded bg-gray-800 text-sm disabled:opacity-40">Previous</button>
          <span className="px-3 py-1.5 text-sm text-gray-400">{page} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-3 py-1.5 rounded bg-gray-800 text-sm disabled:opacity-40">Next</button>
        </div>
      )}
    </div>
  )
}
