import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, RefreshCw, Search, Timer, XCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import { useToast } from '@/components/Toast'
import type {
  SearchDiagnostics as SearchDiagnosticsType,
  SearchDiagnosticsHistoryResponse,
  SearchTestResponse,
} from '@/lib/types'

function fmtMs(value: unknown) {
  const n = Number(value ?? 0)
  return `${n.toFixed(0)} ms`
}

function fmtTime(value: unknown) {
  if (!value) return 'Never'
  try {
    return new Date(String(value)).toLocaleString()
  } catch {
    return String(value)
  }
}

function count(value: unknown) {
  return Number(value ?? 0)
}

export default function SearchDiagnostics() {
  const [data, setData] = useState<SearchDiagnosticsType | null>(null)
  const [loading, setLoading] = useState(false)
  const [testTitle, setTestTitle] = useState('')
  const [testYear, setTestYear] = useState('')
  const [testImdb, setTestImdb] = useState('')
  const [testResult, setTestResult] = useState<SearchTestResponse | null>(null)
  const [testing, setTesting] = useState(false)
  const [history, setHistory] = useState<SearchDiagnosticsHistoryResponse | null>(null)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyQuery, setHistoryQuery] = useState('')
  const [historyType, setHistoryType] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const { toast } = useToast()

  const load = () => {
    setLoading(true)
    api.searchDiagnostics()
      .then((result) => setData(result as SearchDiagnosticsType))
      .catch(() => toast('Failed to load search diagnostics', 'error'))
      .finally(() => setLoading(false))
  }

  const loadHistory = (page = historyPage) => {
    setHistoryLoading(true)
    api.searchDiagnosticsHistory({
      page,
      per_page: 25,
      event_type: historyType || undefined,
      q: historyQuery.trim() || undefined,
    })
      .then((result) => {
        setHistory(result as SearchDiagnosticsHistoryResponse)
        setHistoryPage(page)
      })
      .catch(() => toast('Failed to load diagnostics history', 'error'))
      .finally(() => setHistoryLoading(false))
  }

  useEffect(() => {
    load()
    loadHistory(1)
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [])

  useSocket('search:warning', () => load())
  useSocket('search:results', () => load())

  const events = data?.recent_events ?? []
  const indexerEvents = events.filter((event) => event.type === 'indexer_response' || event.type === 'indexer_request')
  const responseEvents = events.filter((event) => event.type === 'indexer_response')
  const filterEvents = events.filter((event) => event.type === 'filter_summary')
  const heatmap = Object.entries(data?.failure_heatmap ?? {})
  const reliability = Object.entries(data?.indexer_reliability ?? {})
  const degradationTone = data?.degradation.blocking
    ? 'border-red-500/50 bg-red-950/30'
    : data?.degradation.degraded
      ? 'border-yellow-500/50 bg-yellow-950/20'
      : 'border-green-500/30 bg-gray-900'
  const degradationTitle = data?.degradation.blocking
    ? 'Search automation paused'
    : data?.degradation.degraded
      ? 'Search pipeline warning'
      : 'Search pipeline healthy'

  const lastSuccess = useMemo(() => {
    const item = data?.last_successful_search
    if (!item) return 'None recorded'
    return `${String(item.title ?? 'Unknown')} (${fmtTime(item.timestamp)})`
  }, [data])

  const runTest = async () => {
    if (!testTitle.trim()) {
      toast('Enter a movie title first', 'error')
      return
    }
    setTesting(true)
    try {
      const result = await api.runSearchDiagnosticsTest({
        title: testTitle.trim(),
        year: testYear ? Number(testYear) : undefined,
        imdb_id: testImdb.trim() || undefined,
        include_raw: true,
      })
      setTestResult(result as SearchTestResponse)
      toast('Search test complete', 'success')
      load()
    } catch {
      toast('Search test failed', 'error')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Search Diagnostics</h1>
          <p className="text-xs text-gray-400 mt-1">Live indexer requests, parser health, filtering, and degradation warnings.</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className={`rounded-xl border p-4 ${degradationTone}`}>
        <div className="flex items-start gap-3">
          {data?.degradation.degraded ? (
            <AlertTriangle className={`${data.degradation.blocking ? 'text-red-300' : 'text-yellow-300'} shrink-0`} size={20} />
          ) : (
            <CheckCircle className="text-green-400 shrink-0" size={20} />
          )}
          <div className="min-w-0">
            <p className="font-semibold">{degradationTitle}</p>
            <p className="text-sm text-gray-300 mt-1">
              {data?.degradation.reasons?.length ? data.degradation.reasons.join(', ') : 'No suspicious search failure pattern is active.'}
            </p>
            {data?.degradation.degraded && !data.degradation.blocking ? (
              <p className="text-xs text-yellow-100 mt-2">
                Slimarr will keep searching, but this pattern needs attention if it persists across mainstream titles.
              </p>
            ) : null}
            <p className="text-xs text-gray-500 mt-2">
              Zero streak: {data?.degradation.consecutive_zero_searches ?? 0} - Failed-provider streak: {data?.degradation.consecutive_failed_searches ?? 0} - Last success: {lastSuccess}
            </p>
          </div>
        </div>
      </div>

      {data?.warnings?.length ? (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Actionable Warnings</div>
          <div className="divide-y divide-gray-800">
            {data.warnings.slice(0, 5).map((warning) => (
              <div key={`${warning.timestamp}-${warning.message}`} className="px-4 py-3 text-sm">
                <p className="text-yellow-200">{warning.message}</p>
                <p className="text-xs text-gray-500 mt-1">{fmtTime(warning.timestamp)}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Live Requests</p>
          <p className="text-2xl font-semibold mt-1">{indexerEvents.length}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Latest Parsed Results</p>
          <p className="text-2xl font-semibold mt-1">{count(responseEvents[0]?.parsed_count)}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4">
          <p className="text-xs text-gray-400">Latest Latency</p>
          <p className="text-2xl font-semibold mt-1">{fmtMs(responseEvents[0]?.latency_ms)}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Indexer Responses</div>
          <div className="divide-y divide-gray-800 max-h-[520px] overflow-y-auto">
            {indexerEvents.length === 0 ? (
              <p className="px-4 py-4 text-sm text-gray-500">No indexer requests recorded yet.</p>
            ) : indexerEvents.slice(0, 40).map((event, idx) => (
              <div key={`${event.timestamp}-${idx}`} className="px-4 py-3 text-sm space-y-2">
                <div className="flex items-center gap-2">
                  {event.type === 'indexer_request' ? (
                    <RefreshCw size={14} className="text-blue-300" />
                  ) : event.error ? <XCircle size={14} className="text-red-400" /> : <CheckCircle size={14} className="text-green-400" />}
                  <span className="font-medium">{event.indexer_name ?? event.provider ?? 'Indexer'}</span>
                  <span className="text-xs text-gray-500">
                    {event.type === 'indexer_request' ? 'started' : `HTTP ${event.status_code ?? 'n/a'} - ${fmtMs(event.latency_ms)}`}
                  </span>
                  {event.rate_limited ? (
                    <span className="rounded bg-yellow-500/20 px-1.5 py-0.5 text-[11px] text-yellow-100">
                      quota
                    </span>
                  ) : null}
                </div>
                <p className="text-xs text-gray-400 break-all">{event.request_url}</p>
                <p className="text-xs text-gray-500">
                  Raw {event.raw_count ?? 0} - Parsed {event.parsed_count ?? 0}
                  {event.error ? ` - ${event.error}` : ''}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-gray-900 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Filtered vs Accepted</div>
            <div className="divide-y divide-gray-800">
              {filterEvents.length === 0 ? (
                <p className="px-4 py-4 text-sm text-gray-500">No filtering summaries recorded yet.</p>
              ) : filterEvents.slice(0, 8).map((event, idx) => (
                <div key={`${event.timestamp}-${idx}`} className="px-4 py-3 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="font-medium truncate">{event.title ?? 'Unknown movie'}</span>
                    <span className="text-xs text-gray-500">{count(event.accepted_count)}/{count(event.stored_count)} accepted</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Raw {count(event.raw_count)} - Unique {count(event.unique_count)} - Rejected {count(event.rejected_count)}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-gray-900 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Failure Heatmap</div>
            <div className="p-4 flex flex-wrap gap-2">
              {heatmap.length === 0 ? (
                <p className="text-sm text-gray-500">No failures recorded.</p>
              ) : heatmap.map(([key, value]) => (
                <span key={key} className="rounded bg-red-500/20 border border-red-500/30 px-2 py-1 text-xs text-red-100">
                  {key}: {value}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-gray-900 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Indexer Reliability</div>
            <div className="divide-y divide-gray-800">
              {reliability.length === 0 ? (
                <p className="px-4 py-4 text-sm text-gray-500">No reliability data yet.</p>
              ) : reliability.map(([name, item]) => (
                <div key={name} className="px-4 py-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{name}</span>
                    <span className="text-xs text-gray-400">{String(item.success_rate ?? 'n/a')}% success</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Requests {String(item.requests ?? 0)} - Failures {String(item.failures ?? 0)} - Timeouts {String(item.timeouts ?? 0)} - Quota {String(item.rate_limited ?? 0)} - Avg {fmtMs(item.avg_latency_ms)}
                  </p>
                  {item.last_rate_limit_at ? <p className="text-xs text-yellow-200 mt-1">Last quota/rate limit: {fmtTime(item.last_rate_limit_at)}</p> : null}
                  {item.last_error ? <p className="text-xs text-red-300 mt-1 truncate">{String(item.last_error)}</p> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-gray-900 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">Persisted Diagnostics History</h2>
            <p className="text-xs text-gray-400 mt-1">Searchable history survives restarts and is paginated.</p>
          </div>
          <button
            onClick={() => loadHistory(historyPage)}
            disabled={historyLoading}
            className="flex items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50"
          >
            <RefreshCw size={14} className={historyLoading ? 'animate-spin' : ''} />
            Refresh History
          </button>
        </div>

        <div className="grid gap-3 md:grid-cols-[1fr_180px_auto]">
          <input
            value={historyQuery}
            onChange={(e) => setHistoryQuery(e.target.value)}
            placeholder="Search history text"
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
          />
          <select
            value={historyType}
            onChange={(e) => setHistoryType(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
          >
            <option value="">All event types</option>
            <option value="indexer_request">indexer_request</option>
            <option value="indexer_response">indexer_response</option>
            <option value="filter_summary">filter_summary</option>
            <option value="movie_search_completed">movie_search_completed</option>
            <option value="warning">warning</option>
          </select>
          <button
            onClick={() => loadHistory(1)}
            className="px-3 py-2 rounded bg-brand-green text-sm text-white"
          >
            Apply
          </button>
        </div>

        <div className="bg-gray-800 rounded overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-700 text-xs font-semibold">
            {history?.total ?? 0} total history records
          </div>
          <div className="divide-y divide-gray-700 max-h-80 overflow-y-auto">
            {!history?.items?.length ? (
              <p className="px-3 py-3 text-xs text-gray-500">No persisted history records found.</p>
            ) : history.items.map((item, idx) => (
              <div key={`${item.timestamp}-${idx}`} className="px-3 py-2 text-xs">
                <p className="text-gray-200 break-all">{String(item.type || 'event')} - {String(item.indexer_name || item.provider || item.title || 'n/a')}</p>
                <p className="text-gray-400 mt-1 break-all">{String(item.error || item.request_url || '')}</p>
                <p className="text-gray-500 mt-1">{fmtTime(item.timestamp)}</p>
              </div>
            ))}
          </div>
          <div className="px-3 py-2 border-t border-gray-700 flex items-center justify-between text-xs text-gray-400">
            <span>Page {history?.page ?? 1} / {history?.pages ?? 1}</span>
            <div className="flex gap-2">
              <button
                onClick={() => loadHistory(Math.max(1, historyPage - 1))}
                disabled={historyPage <= 1 || historyLoading}
                className="px-2 py-1 rounded bg-gray-700 disabled:opacity-40"
              >
                Prev
              </button>
              <button
                onClick={() => loadHistory(Math.min(history?.pages ?? historyPage, historyPage + 1))}
                disabled={historyLoading || historyPage >= (history?.pages ?? historyPage)}
                className="px-2 py-1 rounded bg-gray-700 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-gray-900 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Search size={18} className="text-gray-400" />
          <h2 className="font-semibold">Search Test Harness</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_120px_170px_auto]">
          <input value={testTitle} onChange={(e) => setTestTitle(e.target.value)} placeholder="Movie title" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <input value={testYear} onChange={(e) => setTestYear(e.target.value)} placeholder="Year" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <input value={testImdb} onChange={(e) => setTestImdb(e.target.value)} placeholder="IMDb ID" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <button onClick={runTest} disabled={testing} className="flex items-center justify-center gap-2 px-3 py-2 rounded bg-brand-green text-sm text-white disabled:opacity-50">
            <Timer size={14} />
            {testing ? 'Testing...' : 'Run Test'}
          </button>
        </div>

        {testResult ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="bg-gray-800 rounded p-3 text-sm">Raw <span className="font-semibold">{testResult.raw_total}</span></div>
              <div className="bg-gray-800 rounded p-3 text-sm">Parsed <span className="font-semibold">{testResult.parsed_total}</span></div>
              <div className="bg-gray-800 rounded p-3 text-sm">Accepted <span className="font-semibold">{testResult.accepted_count}</span></div>
              <div className="bg-gray-800 rounded p-3 text-sm">Rejected <span className="font-semibold">{testResult.rejected_count}</span></div>
            </div>

            <div className="bg-gray-800 rounded overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-700 text-xs font-semibold">Provider Payloads</div>
              <div className="divide-y divide-gray-700">
                {testResult.providers.map((provider, idx) => (
                  <details key={idx} className="px-3 py-2 text-xs">
                    <summary className="cursor-pointer text-gray-200">{String(provider.indexer_name ?? provider.provider ?? 'Provider')} - Raw {String(provider.raw_count ?? 0)} - Parsed {String(provider.parsed_count ?? 0)}</summary>
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-gray-400">{String(provider.raw_response || provider.error || 'No raw payload captured')}</pre>
                  </details>
                ))}
              </div>
            </div>

            <div className="bg-gray-800 rounded overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-700 text-xs font-semibold">Accepted Results</div>
              <div className="divide-y divide-gray-700 max-h-80 overflow-y-auto">
                {testResult.accepted_results.length === 0 ? (
                  <p className="px-3 py-3 text-xs text-gray-500">No accepted results.</p>
                ) : testResult.accepted_results.slice(0, 25).map((result, idx) => (
                  <div key={idx} className="px-3 py-2 text-xs">
                    <p className="text-gray-200 truncate">{String(result.release_title ?? 'Untitled')}</p>
                    <p className="text-green-300 mt-1">
                      {String(result.media_health_rating ?? 'Accepted')} - confidence {String(result.confidence_score ?? 'n/a')}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-gray-800 rounded overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-700 text-xs font-semibold">Rejected Results</div>
              <div className="divide-y divide-gray-700 max-h-80 overflow-y-auto">
                {testResult.rejected_results.length === 0 ? (
                  <p className="px-3 py-3 text-xs text-gray-500">No rejected results.</p>
                ) : testResult.rejected_results.slice(0, 25).map((result, idx) => (
                  <div key={idx} className="px-3 py-2 text-xs">
                    <p className="text-gray-200 truncate">{String(result.release_title ?? 'Untitled')}</p>
                    <p className="text-red-300 mt-1">{String(result.reject_reason ?? 'Rejected')}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
