import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import type { Movie } from '@/lib/types'
import PosterCard from '@/components/PosterCard'
import { useToast } from '@/components/Toast'
import { useSocket } from '@/hooks/useSocket'
import { Search, RefreshCw } from 'lucide-react'

export default function Library() {
  const [movies, setMovies] = useState<Movie[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const PER_PAGE = 48

  const { toast } = useToast()
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<{ current: number; total: number; title: string } | null>(null)

  useSocket('scan:started', (d) => {
    const data = d as { total_movies: number }
    setScanProgress({ current: 0, total: data.total_movies, title: 'Starting scan…' })
    setScanning(true)
  })
  useSocket('scan:progress', (d) => {
    const data = d as { current: number; total: number; title: string }
    setScanProgress(data)
  })
  useSocket('scan:completed', () => {
    setScanProgress(null)
    setScanning(false)
    load()
  })

  const scan = async () => {
    setScanning(true)
    try {
      await api.scanLibrary()
      toast('Library scan started', 'info')
    } catch {
      toast('Failed to start scan', 'error')
      setScanning(false)
    }
  }

  const load = useCallback(() => {
    setLoading(true)
    api.movies({ page, per_page: PER_PAGE, search, status })
      .then((d: { movies: Movie[]; total: number }) => {
        setMovies(d.movies)
        setTotal(d.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [page, search, status])

  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / PER_PAGE)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <h1 className="text-2xl font-bold flex-1">Library</h1>
        <button
          onClick={scan}
          disabled={scanning}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-sm hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
          {scanning ? 'Scanning…' : 'Scan Library'}
        </button>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search movies…"
            className="pl-9 pr-3 py-2 rounded-lg bg-gray-800 text-sm outline-none w-64"
          />
        </div>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1) }}
          className="bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none"
        >
          <option value="">All Status</option>
          <option value="pending">Pending</option>
          <option value="improved">Improved</option>
          <option value="downloading">Downloading</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {scanProgress && (
        <div className="bg-blue-900/30 border border-blue-500/30 rounded-xl px-4 py-3 flex items-center gap-3">
          <RefreshCw size={14} className="animate-spin text-blue-400 shrink-0" />
          <span className="text-sm text-blue-200 truncate">{scanProgress.title}</span>
          <span className="text-xs text-gray-400 ml-auto shrink-0">{scanProgress.current}/{scanProgress.total}</span>
        </div>
      )}

      <p className="text-sm text-gray-400">{total} movies</p>

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
          {movies.map((m) => <PosterCard key={m.id} movie={m} />)}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex gap-2 justify-center pt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 rounded bg-gray-800 text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <span className="px-3 py-1.5 text-sm text-gray-400">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 rounded bg-gray-800 text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
