import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import { useToast } from '@/components/Toast'
import { Play, Square, RefreshCw, Database, Clock, Server, CheckCircle, XCircle, Trash2, ArrowUpCircle } from 'lucide-react'

interface ServiceHealth {
  success: boolean
  error?: string
  version?: string
  movie_count?: number
  server_name?: string
  indexer_count?: number
}

interface IndexerHealth {
  name: string
  success: boolean
  error?: string
}

function fmtUptime(secs: number) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1048576).toFixed(1)} MB`
}

interface SystemInfo {
  version: string
  python: string
  platform: string
  uptime_seconds: number
  db_size_bytes: number
  port: number
}

export default function System() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [services, setServices] = useState<Record<string, ServiceHealth> | null>(null)
  const [starting, setStarting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<{ update_available: boolean; latest?: string; release_url?: string } | null>(null)

  const loadStatus = () => api.systemStatus().then(setStatus).catch(() => {})
  const loadServices = () => api.servicesHealth().then(setServices).catch(() => {})

  useEffect(() => {
    loadStatus()
    api.systemInfo().then(setInfo).catch(() => {})
    api.updateCheck().then(setUpdateInfo).catch(() => {})
    loadServices()
    const iv = setInterval(loadStatus, 10000)
    return () => clearInterval(iv)
  }, [])

  useSocket('scan:started', () => setScanning(true))
  useSocket('scan:completed', () => { setScanning(false); loadStatus() })
  useSocket('orchestrator:status', (d) => {
    const data = d as { running: boolean }
    if (!data.running) setStarting(false)
    loadStatus()
  })

  const { toast } = useToast()

  const startCycle = async () => {
    setStarting(true)
    try {
      await api.startCycle()
      toast('Automation cycle started', 'success')
    } catch { toast('Failed to start cycle', 'error') }
    setTimeout(loadStatus, 1500)
  }

  const stopCycle = async () => {
    try {
      await api.stopCycle()
      toast('Stop requested', 'info')
    } catch { toast('Failed to stop cycle', 'error') }
    setTimeout(loadStatus, 1000)
  }

  const scanNow = async () => {
    setScanning(true)
    try {
      await api.scanLibrary()
      toast('Library scan started', 'info')
    } catch { toast('Scan failed to start', 'error') }
  }

  const cleanDuplicates = async () => {
    setCleaning(true)
    try {
      await api.cleanupDuplicates()
      toast('Duplicate scan started — check logs for results', 'info')
    } catch { toast('Failed to start duplicate scan', 'error') }
    setTimeout(() => setCleaning(false), 8000)
  }

  const cycle = (status?.cycle as Record<string, boolean>) ?? {}
  const jobs = (status?.jobs as Array<{ id: string; next_run: string }>) ?? []

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">System</h1>

      {/* System info */}
      {info && (
        <div className="bg-gray-900 rounded-xl p-5 grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3">
            <Server size={16} className="text-gray-400" />
            <div>
              <p className="text-xs text-gray-400">Version</p>
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Slimarr {info.version}</p>
                {updateInfo?.update_available && (
                  <a
                    href={updateInfo.release_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs bg-yellow-500/20 text-yellow-300 border border-yellow-500/40 rounded-full px-2 py-0.5 hover:bg-yellow-500/30"
                    title={`v${updateInfo.latest} available`}
                  >
                    <ArrowUpCircle size={11} />
                    v{updateInfo.latest} available
                  </a>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Clock size={16} className="text-gray-400" />
            <div>
              <p className="text-xs text-gray-400">Uptime</p>
              <p className="text-sm font-medium">{fmtUptime(info.uptime_seconds)}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Database size={16} className="text-gray-400" />
            <div>
              <p className="text-xs text-gray-400">Database</p>
              <p className="text-sm font-medium">{fmtBytes(info.db_size_bytes)}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Server size={16} className="text-gray-400" />
            <div>
              <p className="text-xs text-gray-400">Python / Port</p>
              <p className="text-sm font-medium">{info.python} · :{info.port}</p>
            </div>
          </div>
        </div>
      )}

      {/* Integration health */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold flex items-center justify-between">
          Integration Status
          <button onClick={loadServices} className="text-xs text-gray-400 hover:text-white">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="divide-y divide-gray-800">
          {(['plex', 'sabnzbd', 'radarr', 'sonarr', 'prowlarr', 'tmdb'] as const).map((svc) => {
            const h = services?.[svc]
            const label = { plex: 'Plex', sabnzbd: 'SABnzbd', radarr: 'Radarr', sonarr: 'Sonarr', prowlarr: 'Prowlarr', tmdb: 'TMDB' }[svc]
            const isDisabled = h && !h.success && h.error === 'Disabled'
            const detail = isDisabled
              ? 'Disabled'
              : h?.success
                ? (h.server_name ?? (h.version ? `v${h.version}` + (h.movie_count !== undefined ? ` · ${h.movie_count} movies` : '') : h.movie_count !== undefined ? `${h.movie_count} movies` : h.indexer_count !== undefined ? `${h.indexer_count} indexers` : 'Connected'))
                : (h?.error ?? 'Checking…')
            return (
              <div key={svc} className="px-4 py-3 flex items-center gap-3 text-sm">
                {h === undefined ? (
                  <RefreshCw size={14} className="text-gray-500 animate-spin shrink-0" />
                ) : isDisabled ? (
                  <span className="w-3.5 h-3.5 rounded-full bg-gray-600 shrink-0" />
                ) : h.success ? (
                  <CheckCircle size={14} className="text-green-400 shrink-0" />
                ) : (
                  <XCircle size={14} className="text-red-400 shrink-0" />
                )}
                <span className="w-20 font-medium">{label}</span>
                <span className={`text-xs truncate ${isDisabled ? 'text-gray-600' : 'text-gray-400'}`}>{detail}</span>
              </div>
            )
          })}
        </div>
        {/* Indexers */}
        {services && (services['indexers'] as unknown as IndexerHealth[] | undefined)?.length ? (
          <>
            <div className="px-4 py-2 border-t border-gray-800 text-xs text-gray-500 font-medium uppercase tracking-wide">Indexers</div>
            {(services['indexers'] as unknown as IndexerHealth[]).map((idx) => (
              <div key={idx.name} className="px-4 py-2.5 flex items-center gap-3 text-sm border-t border-gray-800">
                {idx.success ? (
                  <CheckCircle size={14} className="text-green-400 shrink-0" />
                ) : (
                  <XCircle size={14} className="text-red-400 shrink-0" />
                )}
                <span className="font-medium">{idx.name}</span>
                {!idx.success && idx.error && (
                  <span className="text-xs text-gray-500 truncate">{idx.error}</span>
                )}
              </div>
            ))}
          </>
        ) : null}
      </div>

      {/* Scan library */}
      <div className="bg-gray-900 rounded-xl p-5 flex items-center justify-between">
        <div>
          <h2 className="font-semibold">Library Scan</h2>
          <p className="text-xs text-gray-400 mt-0.5">Sync movies from Plex and enrich with TMDB metadata</p>
        </div>
        <button
          onClick={scanNow}
          disabled={scanning}
          className="flex items-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
          {scanning ? 'Scanning…' : 'Scan Now'}
        </button>
      </div>

      {/* Duplicate cleanup */}
      <div className="bg-gray-900 rounded-xl p-5 flex items-center justify-between">
        <div>
          <h2 className="font-semibold">Duplicate File Cleanup</h2>
          <p className="text-xs text-gray-400 mt-0.5">Find movies with multiple files and delete the lower-quality copy. Uses your recycling bin if configured.</p>
        </div>
        <button
          onClick={cleanDuplicates}
          disabled={cleaning}
          className="flex items-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50"
        >
          <Trash2 size={14} className={cleaning ? 'animate-pulse' : ''} />
          {cleaning ? 'Scanning…' : 'Find Duplicates'}
        </button>
      </div>

      {/* Automation cycle */}
      <div className="bg-gray-900 rounded-xl p-5 flex items-center justify-between">
        <div>
          <h2 className="font-semibold">Automation Cycle</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {cycle.running ? '🟢 Running' : '⚪ Idle'}
            {cycle.stop_requested ? ' — stop requested' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          {cycle.running ? (
            <button
              onClick={stopCycle}
              className="flex items-center gap-2 px-3 py-1.5 rounded bg-red-700 text-sm text-white hover:bg-red-600"
            >
              <Square size={14} /> Stop
            </button>
          ) : (
            <button
              onClick={startCycle}
              disabled={starting}
              className="flex items-center gap-2 px-3 py-1.5 rounded bg-brand-green text-white text-sm disabled:opacity-50"
            >
              <Play size={14} /> {starting ? 'Starting…' : 'Run Now'}
            </button>
          )}
        </div>
      </div>

      {/* Scheduled tasks */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Scheduled Tasks</div>
        <div className="divide-y divide-gray-800">
          {jobs.length === 0 && (
            <p className="px-4 py-4 text-gray-500 text-sm">No scheduled tasks.</p>
          )}
          {jobs.map((job) => (
            <div key={job.id} className="px-4 py-3 flex items-center gap-4 text-sm">
              <div className="flex-1">
                <p className="font-medium">{job.id.replace(/_/g, ' ')}</p>
                {job.next_run && (
                  <p className="text-xs text-gray-400">Next: {new Date(job.next_run).toLocaleString()}</p>
                )}
              </div>
              <button
                onClick={() => api.runTask(job.id)
                  .then(() => toast('Task queued', 'success'))
                  .catch(() => toast('Failed to run task', 'error'))
                }
                className="px-3 py-1 rounded bg-gray-700 text-xs hover:bg-gray-600"
              >
                Run
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

