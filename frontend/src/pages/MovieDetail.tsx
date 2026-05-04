import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { Movie, SearchResultItem } from '@/lib/types'
import QualityBadge from '@/components/QualityBadge'
import { ArrowLeft, Search, Zap, Download, Info, X, Lock, Unlock } from 'lucide-react'

function fmt(bytes?: number | null) {
  if (!bytes) return '-'
  return (bytes / 1e9).toFixed(2) + ' GB'
}

function fmtAge(days?: number | null) {
  if (days === undefined || days === null) return 'Unknown'
  if (days === 0) return 'Today'
  if (days < 30) return `${days}d`
  if (days < 365) return `${Math.floor(days / 30)}mo`
  return `${(days / 365).toFixed(1)}y`
}

function fmtFixed(value?: number | null, digits = 1) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-'
}

function pctWidth(value?: number | null) {
  return `${Math.max(0, Math.min(100, value ?? 0))}%`
}

export default function MovieDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const fromLibrary = (location.state as { fromLibrary?: string } | null)?.fromLibrary || '/library'
  const movieId = Number(id)

  const [movie, setMovie] = useState<Movie | null>(null)
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [searching, setSearching] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [selectedResult, setSelectedResult] = useState<SearchResultItem | null>(null)
  const [locking, setLocking] = useState(false)

  useEffect(() => {
    api.movie(movieId).then(setMovie).catch(() => {})
    api.searchResults(movieId).then(setResults).catch(() => {})
  }, [movieId])

  const { toast } = useToast()

  const doSearch = async () => {
    setSearching(true)
    try {
      await api.triggerSearch(movieId)
      toast('Search started - results will appear shortly', 'info')
      setTimeout(() => {
        api.searchResults(movieId).then(setResults).finally(() => setSearching(false))
      }, 3000)
    } catch {
      toast('Search failed', 'error')
      setSearching(false)
    }
  }

  const doProcess = async () => {
    setProcessing(true)
    try {
      await api.triggerProcess(movieId)
      toast('Processing best match...', 'info')
      setTimeout(() => api.movie(movieId).then(setMovie), 5000)
    } catch {
      toast('Process failed', 'error')
    } finally {
      setProcessing(false)
    }
  }

  const doDownloadResult = async (resultId: number) => {
    setDownloadingId(resultId)
    try {
      await api.downloadResult(movieId, resultId)
      toast('Download queued - check Queue page for progress', 'success')
      setTimeout(() => api.movie(movieId).then(setMovie), 3000)
    } catch {
      toast('Failed to queue download', 'error')
    } finally {
      setDownloadingId(null)
    }
  }

  const doToggleLock = async () => {
    if (!movie) return
    setLocking(true)
    try {
      if (movie.slimarr_locked) {
        await api.unlockMovie(movieId)
        toast('Movie unlocked — Slimarr will include it in future cycles', 'success')
      } else {
        await api.lockMovie(movieId)
        toast('Movie locked — Slimarr will skip it in future cycles', 'info')
      }
      api.movie(movieId).then(setMovie)
    } catch {
      toast('Failed to update lock', 'error')
    } finally {
      setLocking(false)
    }
  }

  if (!movie) return <div className="text-gray-400">Loading...</div>

  const posterUrl = movie.poster_path ? `/api/v1/images/${movie.id}/poster` : null
  const accepted = results.filter((r) => r.decision === 'accept')

  return (
    <div className="space-y-6">
      <button onClick={() => navigate(fromLibrary)} className="flex items-center gap-2 text-gray-400 hover:text-white text-sm">
        <ArrowLeft size={16} /> Back to Library
      </button>

      <div className="flex gap-6 flex-wrap">
        {posterUrl && (
          <img src={posterUrl} alt={movie.title} className="w-40 rounded-xl" />
        )}
        <div className="flex-1 min-w-0">
          <h1 className="text-3xl font-bold">{movie.title}</h1>
          <p className="text-gray-400">{movie.year}</p>
          <p className="text-sm text-gray-500 mt-2 line-clamp-3">{movie.overview}</p>

          <div className="flex gap-2 mt-3 flex-wrap">
            {movie.resolution && <QualityBadge type="res" value={movie.resolution} />}
            {movie.video_codec && <QualityBadge type="codec" value={movie.video_codec} />}
          </div>

          <div className="mt-3 text-sm text-gray-400 space-y-1">
            <p>Size: {fmt(movie.file_size)}</p>
            {movie.original_file_size && movie.original_file_size !== movie.file_size && (
              <p className="text-green-400">
                Saved: {fmt(movie.original_file_size - (movie.file_size ?? 0))}
              </p>
            )}
            <p>Status: <span className="capitalize text-white">{movie.status}</span></p>
          </div>

          <div className="flex gap-3 mt-4">
            <button
              onClick={doSearch}
              disabled={searching}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 text-sm hover:bg-gray-700 disabled:opacity-50"
            >
              <Search size={16} /> {searching ? 'Searching...' : 'Search'}
            </button>
            <button
              onClick={doProcess}
              disabled={processing || accepted.length === 0}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-green text-white text-sm disabled:opacity-50"
            >
              <Zap size={16} /> {processing ? 'Processing...' : 'Download Best'}
            </button>
            <button
              onClick={doToggleLock}
              disabled={locking}
              title={movie.slimarr_locked ? 'Unlock: allow Slimarr to replace this movie' : 'Lock: prevent Slimarr from replacing this movie'}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm disabled:opacity-50 ${
                movie.slimarr_locked
                  ? 'bg-yellow-600 hover:bg-yellow-500 text-white'
                  : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
              }`}
            >
              {movie.slimarr_locked ? <Lock size={16} /> : <Unlock size={16} />}
              {movie.slimarr_locked ? 'Locked' : 'Lock'}
            </button>
          </div>
        </div>
      </div>

      {results.length > 0 && (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">
            Search Results ({results.length} - {accepted.length} accepted)
          </div>
          <div className="hidden md:grid grid-cols-[minmax(0,1fr)_5rem_5rem_6rem_5rem_5rem_7rem] gap-4 px-4 py-2 border-b border-gray-800 text-xs uppercase text-gray-500">
            <span>Release</span>
            <span>Res</span>
            <span>Age</span>
            <span className="text-right">Size</span>
            <span>Score</span>
            <span>Confidence</span>
            <span />
          </div>
          <div className="divide-y divide-gray-800">
            {results.map((r) => (
              <div key={r.id} className="px-4 py-3 grid grid-cols-[auto_minmax(0,1fr)_auto] md:grid-cols-[auto_minmax(0,1fr)_5rem_5rem_6rem_5rem_5rem_7rem] items-center gap-3 md:gap-4 text-sm">
                <div className={`w-2 h-2 rounded-full shrink-0 ${r.decision === 'accept' ? 'bg-green-500' : 'bg-red-500'}`} />
                <div className="flex-1 min-w-0">
                  <p className="truncate">{r.release_title}</p>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500 md:hidden">
                    <span>{r.resolution || 'Unknown res'}</span>
                    <span>{fmtAge(r.age_days)}</span>
                    <span>{fmt(r.size)}</span>
                    <span>score {fmtFixed(r.score)}</span>
                    {r.confidence_score !== undefined && r.confidence_score !== null && <span>confidence {fmtFixed(r.confidence_score, 0)}</span>}
                  </div>
                  {r.reject_reason && <p className="text-xs text-red-400">{r.reject_reason}</p>}
                </div>
                <div className="hidden md:block text-gray-300">{r.resolution || '-'}</div>
                <div className="hidden md:block text-gray-400">{fmtAge(r.age_days)}</div>
                <div className="hidden md:block text-right shrink-0">
                  <p>{fmt(r.size)}</p>
                  {(r.savings_pct ?? 0) > 0 && (
                    <p className="text-green-400 text-xs">-{fmtFixed(r.savings_pct)}%</p>
                  )}
                </div>
                <div className="hidden md:block text-xs text-gray-500 shrink-0">{fmtFixed(r.score)}</div>
                <div className="hidden md:block text-xs text-gray-500 shrink-0">{fmtFixed(r.confidence_score, 0)}</div>
                <div className="flex items-center gap-2 justify-end">
                  <button
                    onClick={() => setSelectedResult(r)}
                    className="p-1.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700"
                    title="Show candidate details"
                  >
                    <Info size={13} />
                  </button>
                  {r.decision === 'accept' && (
                  <button
                    onClick={() => doDownloadResult(r.id)}
                    disabled={downloadingId === r.id}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-brand-green text-white text-xs disabled:opacity-50 hover:bg-green-600 shrink-0"
                  >
                    <Download size={12} />
                    {downloadingId === r.id ? '...' : 'Download'}
                  </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelectedResult(null)}>
          <div className="w-full max-w-2xl rounded-xl border border-gray-800 bg-gray-950 p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-semibold">Candidate Details</h2>
                <p className="mt-1 break-words text-sm text-gray-400">{selectedResult.release_title}</p>
              </div>
              <button onClick={() => setSelectedResult(null)} className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-gray-900 p-3">
                <p className="text-xs uppercase text-gray-500">Decision</p>
                <p className={selectedResult.decision === 'accept' ? 'text-green-400 font-semibold' : 'text-red-400 font-semibold'}>{selectedResult.decision}</p>
                {selectedResult.reject_reason && <p className="mt-2 text-sm text-red-300">{selectedResult.reject_reason}</p>}
              </div>
              <div className="rounded-lg bg-gray-900 p-3">
                <p className="text-xs uppercase text-gray-500">Savings</p>
                <p className="font-semibold">{fmt(selectedResult.savings_bytes)} ({fmtFixed(selectedResult.savings_pct)}%)</p>
              </div>
              <div className="rounded-lg bg-gray-900 p-3">
                <p className="text-xs uppercase text-gray-500">Release</p>
                <p className="text-sm">{selectedResult.resolution || 'Unknown resolution'} / {selectedResult.video_codec || 'Unknown codec'} / {fmtAge(selectedResult.age_days)}</p>
              </div>
              <div className="rounded-lg bg-gray-900 p-3">
                <p className="text-xs uppercase text-gray-500">Confidence</p>
                <p className="font-semibold">{typeof selectedResult.confidence_score === 'number' ? `${fmtFixed(selectedResult.confidence_score, 0)} / 100` : 'Not scored'}</p>
              </div>
            </div>
            {selectedResult.confidence_breakdown && Object.keys(selectedResult.confidence_breakdown).length > 0 && (
              <div className="mt-4 space-y-2">
                {Object.entries(selectedResult.confidence_breakdown).map(([key, value]) => (
                  <div key={key}>
                    <div className="mb-1 flex justify-between text-xs text-gray-400">
                      <span className="capitalize">{key.replace(/_/g, ' ')}</span>
                      <span>{fmtFixed(value, 0)}</span>
                    </div>
                    <div className="h-2 rounded bg-gray-800">
                      <div className="h-2 rounded bg-brand-green" style={{ width: pctWidth(value) }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
