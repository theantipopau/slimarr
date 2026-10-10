import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import { useToast } from '@/components/Toast'
import { useNasPresetManager } from '@/hooks/useNasPreset'
import type { DecisionAuditEntry, DuplicateCleanupPreview, HealthMatrix, NasPressure, PersistentJobsSnapshot, PreflightResult, ReplacementRecoverySnapshot, StorageOperationsSnapshot, StoragePreflight, UtilitiesMaintenanceInsights } from '@/lib/types'
import { Play, Square, RefreshCw, Database, Clock, Server, CheckCircle, XCircle, Trash2, ArrowUpCircle, ShieldCheck, Sparkles, GaugeCircle, HardDrive, ShieldAlert, SlidersHorizontal } from 'lucide-react'
import ConfirmDialog from '@/components/ConfirmDialog'
import StorageStateMark from '@/components/StorageStateMark'
import { formatBytes as fmtBytes } from '@/lib/format'

interface ServiceHealth {
  success: boolean
  error?: string
  version?: string
  movie_count?: number
  server_name?: string
  indexer_count?: number
}

interface RecyclingBinInfo {
  enabled: boolean
  path: string
  exists: boolean
  files: number
  bytes: number
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

function fmtPct(value: number) {
  return `${Math.max(0, Math.min(100, value)).toFixed(0)}%`
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
  const [healthMatrix, setHealthMatrix] = useState<HealthMatrix | null>(null)
  const [decisionAudit, setDecisionAudit] = useState<DecisionAuditEntry[]>([])
  const [starting, setStarting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<{ update_available: boolean; latest?: string; release_url?: string } | null>(null)
  const [recyclingInfo, setRecyclingInfo] = useState<RecyclingBinInfo | null>(null)
  const [quickStats, setQuickStats] = useState<{ active_downloads?: number; total_movies?: number; improved?: number } | null>(null)
  const [recyclingLoading, setRecyclingLoading] = useState(false)
  const [recyclingPurging, setRecyclingPurging] = useState(false)
  const [preflight, setPreflight] = useState<PreflightResult | null>(null)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [cleanupPreview, setCleanupPreview] = useState<DuplicateCleanupPreview | null>(null)
  const [cleanupPreviewLoading, setCleanupPreviewLoading] = useState(false)
  const [maintenanceInsights, setMaintenanceInsights] = useState<UtilitiesMaintenanceInsights | null>(null)
  const [nasPressure, setNasPressure] = useState<NasPressure | null>(null)
  const [storageGuard, setStorageGuard] = useState<StoragePreflight | null>(null)
  const [storageGuardLoading, setStorageGuardLoading] = useState(false)
  const [storageOperations, setStorageOperations] = useState<StorageOperationsSnapshot | null>(null)
  const [replacementRecovery, setReplacementRecovery] = useState<ReplacementRecoverySnapshot | null>(null)
  const [persistentJobs, setPersistentJobs] = useState<PersistentJobsSnapshot | null>(null)
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    title: string
    message: string
    confirmLabel?: string
    destructive?: boolean
    children?: React.ReactNode
    onConfirm: () => void
    onCancel?: () => void
  }>({ open: false, title: '', message: '', onConfirm: () => {} })

  const loadStatus = () => api.systemStatus().then(setStatus).catch(() => {})
  const loadServices = () => api.servicesHealth().then(setServices).catch(() => {})
  const loadHealthMatrix = () => api.healthMatrix().then(setHealthMatrix).catch(() => {})
  const loadDecisionAudit = () => api.decisionAudit({ limit: 8 }).then((rows) => setDecisionAudit(rows as DecisionAuditEntry[])).catch(() => {})
  const loadCleanupPreview = (showLoading = false, force = false) => {
    if (showLoading) setCleanupPreviewLoading(true)
    return api.cleanupPreview({ force })
      .then((data) => setCleanupPreview(data as DuplicateCleanupPreview))
      .catch(() => {})
      .finally(() => {
        if (showLoading) setCleanupPreviewLoading(false)
      })
  }
  const loadMaintenanceInsights = () => api.utilitiesMaintenanceInsights().then((data) => setMaintenanceInsights(data as UtilitiesMaintenanceInsights)).catch(() => {})
  const loadNasPressure = () => api.nasPressure().then((data) => setNasPressure(data as NasPressure)).catch(() => {})
  const loadStorageOperations = () => api.storageOperations({ limit: 8 }).then((data) => setStorageOperations(data as StorageOperationsSnapshot)).catch(() => {})
  const loadReplacementRecovery = () => api.replacementRecovery({ status: 'active', limit: 8 }).then((data) => setReplacementRecovery(data as ReplacementRecoverySnapshot)).catch(() => {})
  const loadPersistentJobs = () => api.jobs({ status: 'all', limit: 8 }).then((data) => setPersistentJobs(data as PersistentJobsSnapshot)).catch(() => {})
  const loadRecyclingInfo = (showLoading = false) => {
    if (showLoading) setRecyclingLoading(true)
    return api.recyclingBinInfo()
      .then(setRecyclingInfo)
      .catch(() => {})
      .finally(() => {
        if (showLoading) setRecyclingLoading(false)
      })
  }

  useEffect(() => {
    loadStatus()
    api.systemInfo().then(setInfo).catch(() => {})
    api.stats().then((d) => setQuickStats(d as { active_downloads?: number; total_movies?: number; improved?: number })).catch(() => {})
    api.updateCheck().then(setUpdateInfo).catch(() => {})
    loadServices().finally(loadHealthMatrix)
    loadDecisionAudit()
    void loadCleanupPreview(true)
    loadMaintenanceInsights()
    loadNasPressure()
    loadStorageOperations()
    loadReplacementRecovery()
    loadPersistentJobs()
    void loadRecyclingInfo(true)
    const iv = setInterval(loadStatus, 10000)
    const recycleIv = setInterval(() => {
      if (!document.hidden) {
        void loadRecyclingInfo()
      }
    }, 60000)
    const healthIv = setInterval(() => {
      if (!document.hidden) {
        loadHealthMatrix()
        loadDecisionAudit()
        loadStorageOperations()
        loadReplacementRecovery()
        loadPersistentJobs()
      }
    }, 30000)
    const nasIv = setInterval(() => {
      if (!document.hidden) loadNasPressure()
    }, 60000)
    const servicesIv = setInterval(() => {
      if (!document.hidden) loadServices()
    }, 120000)
    const maintenanceIv = setInterval(() => {
      if (!document.hidden) loadMaintenanceInsights()
    }, 300000)
    return () => {
      clearInterval(iv)
      clearInterval(recycleIv)
      clearInterval(healthIv)
      clearInterval(nasIv)
      clearInterval(servicesIv)
      clearInterval(maintenanceIv)
    }
  }, [])

  useSocket('scan:started', () => setScanning(true))
  useSocket('scan:completed', () => { setScanning(false); loadStatus() })
  useSocket('orchestrator:status', (d) => {
    const data = d as { running: boolean }
    if (!data.running) setStarting(false)
    loadStatus()
  })

  const { toast } = useToast()

  const {
    applyNasPreset,
    restorePreviousNasProfile,
    applying: nasPresetApplying,
    hasSnapshot: hasPresetSnapshot,
  } = useNasPresetManager(loadNasPressure)

  const runPreflight = async () => {
    setPreflightLoading(true)
    try {
      const result = await api.preflight() as PreflightResult
      setPreflight(result)
      return result
    } catch {
      toast('Preflight check failed', 'error')
      return null
    } finally {
      setPreflightLoading(false)
    }
  }

  const startCycle = async () => {
    setStarting(true)
    try {
      const result = await runPreflight()
      if (!result) {
        setStarting(false)
        return
      }
      if (result.status === 'block') {
        const blocked = result.checks.filter((item) => item.status === 'block').map((item) => item.name).join(', ')
        toast(`Preflight blocked automation: ${blocked}`, 'error')
        setStarting(false)
        return
      }
      if (result.status === 'warn') {
        const warnings = result.checks.filter((item) => item.status === 'warn')
        setConfirmDialog({
          open: true,
          title: 'Preflight found warnings',
          message: 'Review the warnings below, then decide whether to proceed.',
          confirmLabel: 'Start Anyway',
          destructive: false,
          children: (
            <ul className="space-y-1">
              {warnings.map((item) => (
                <li key={item.name}>
                  <span className="font-medium text-amber-300">{item.name}:</span>{' '}
                  <span className="text-gray-300">{item.message}</span>
                </li>
              ))}
            </ul>
          ),
          onConfirm: async () => {
            setConfirmDialog((d) => ({ ...d, open: false }))
            try {
              await api.startCycle()
              toast('Automation cycle started', 'success')
            } catch {
              toast('Failed to start cycle', 'error')
              setStarting(false)
            }
            setTimeout(loadStatus, 1500)
          },
          onCancel: () => setStarting(false),
        })
        return
      }
      await api.startCycle()
      toast('Automation cycle started', 'success')
    } catch {
      toast('Failed to start cycle', 'error')
      setStarting(false)
    }
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
    const previewState = cleanupPreview ?? await api.cleanupPreview() as DuplicateCleanupPreview
    const reclaimable = previewState?.estimated_reclaimable_bytes ?? 0
    const duplicates = previewState?.duplicates_found ?? 0
    setConfirmDialog({
      open: true,
      title: 'Start duplicate cleanup?',
      message: `Found ${duplicates} potential duplicate(s), estimated ${fmtBytes(reclaimable)} reclaimable. Files may be moved to your recycling folder (if configured) or deleted permanently.`,
      confirmLabel: 'Start Cleanup',
      onConfirm: async () => {
        setConfirmDialog((d) => ({ ...d, open: false }))
        setCleaning(true)
        try {
          const result = await api.cleanupDuplicates(true) as { status?: string }
          if (result?.status === 'confirmation_required') {
            toast('Cleanup requires explicit confirmation', 'error')
          } else {
            toast('Duplicate cleanup started — check logs for detailed progress', 'info')
          }
          void loadCleanupPreview(true, true)
          loadMaintenanceInsights()
        } catch { toast('Failed to start duplicate scan', 'error') }
        setTimeout(() => setCleaning(false), 8000)
      },
    })
  }

  const purgeRecyclingBin = () => {
    const path = recyclingInfo?.path
    if (!recyclingInfo?.enabled || !recyclingInfo?.exists || !path) {
      toast('Recycling bin is not configured', 'error')
      return
    }
    setConfirmDialog({
      open: true,
      title: 'Purge recycling folder?',
      message: `Permanently delete all ${recyclingInfo.files} file(s) in the recycling folder (${fmtBytes(recyclingInfo.bytes)}). This cannot be undone.`,
      confirmLabel: 'Purge',
      onConfirm: async () => {
        setConfirmDialog((d) => ({ ...d, open: false }))
        setRecyclingPurging(true)
        try {
          const result = await api.emptyRecyclingBin()
          const freed = Number((result as Record<string, unknown>)?.freed_bytes ?? 0)
          toast(`Recycling folder purged (${fmtBytes(freed)} freed)`, 'success')
          await loadRecyclingInfo(true)
        } catch {
          toast('Failed to purge recycling folder', 'error')
        } finally {
          setRecyclingPurging(false)
        }
      },
    })
  }

  const runStorageGuardCheck = async () => {
    const path = recyclingInfo?.path || nasPressure?.nas_prefixes?.[0] || 'data'
    setStorageGuardLoading(true)
    try {
      const result = await api.storagePreflight({
        path,
        purpose: 'system_storage_guard',
      }) as StoragePreflight
      setStorageGuard(result)
      toast(`Storage preflight: ${result.status}`, result.status === 'block' ? 'error' : result.status === 'warn' ? 'info' : 'success')
    } catch {
      toast('Storage preflight failed', 'error')
    } finally {
      setStorageGuardLoading(false)
    }
  }

  const cycle = (status?.cycle as Record<string, boolean>) ?? {}
  const jobs = (status?.jobs as Array<{ id: string; next_run: string }>) ?? []
  const healthComponents = Object.entries(healthMatrix?.components ?? {})
  const confidence = cleanupPreview?.confidence ?? {}
  const confidenceTotal = (confidence.high ?? 0) + (confidence.medium ?? 0) + (confidence.low ?? 0)

  // Matches the emerald/amber/rose "healthy/degraded/failed" convention used
  // by every other status indicator on this page (maintenance, NAS pressure,
  // storage guard, recovery, jobs) instead of a separate green/yellow/red set.
  const matrixStatusClass = (value?: string) => {
    if (value === 'healthy') return 'text-emerald-300'
    if (value === 'degraded') return 'text-amber-300'
    if (value === 'disabled') return 'text-gray-500'
    return 'text-rose-300'
  }

  const preflightStatusClass = (value?: string) => {
    if (value === 'ok') return 'text-emerald-300'
    if (value === 'warn') return 'text-amber-300'
    return 'text-rose-300'
  }

  const maintenanceStateClass = useMemo(() => {
    const state = maintenanceInsights?.maintenance_state
    if (state === 'excellent') return 'text-emerald-300'
    if (state === 'good') return 'text-cyan-300'
    if (state === 'attention') return 'text-amber-300'
    return 'text-rose-300'
  }, [maintenanceInsights?.maintenance_state])

  const nasPressureClass = useMemo(() => {
    const state = nasPressure?.pressure_state
    if (state === 'low') return 'text-emerald-300'
    if (state === 'medium') return 'text-amber-300'
    return 'text-rose-300'
  }, [nasPressure?.pressure_state])

  const storageGuardState = storageGuard?.status ?? 'ready'
  const storageGuardClass = storageGuardState === 'ok'
    ? 'text-emerald-300'
    : storageGuardState === 'warn'
      ? 'text-amber-300'
      : storageGuardState === 'block'
        ? 'text-rose-300'
        : 'text-cyan-200'
  const nasPolicy = storageOperations?.nas_policy
  const recentStorageFailures = storageOperations?.recent_failures ?? []
  const storageCompleted = (storageOperations?.counters['move:completed'] ?? 0) + (storageOperations?.counters['remove:completed'] ?? 0)
  const storageFailed = (storageOperations?.counters['move:failed'] ?? 0) + (storageOperations?.counters['remove:failed'] ?? 0)
  const storageCooldownClass = nasPolicy?.cooldown_active ? 'text-amber-300' : 'text-emerald-300'
  const persistedStorage = storageOperations?.persisted
  const recoveryRecords = replacementRecovery?.records ?? []
  const recoveryRequired = recoveryRecords.filter((record) => record.status === 'recovery_required').length
  const runningRecovery = recoveryRecords.filter((record) => record.status === 'running').length
  const recoveryState = replacementRecovery?.status ?? 'clear'
  const recoveryClass = recoveryState === 'clear'
    ? 'text-emerald-300'
    : recoveryState === 'recovery_required'
      ? 'text-rose-300'
      : 'text-amber-300'
  const latestRecoveryRecord = recoveryRecords[0]
  const jobRows = persistentJobs?.jobs ?? []
  const activeJobCount = jobRows.filter((job) => ['queued', 'running', 'cancelling'].includes(job.status)).length
  const failedJobCount = jobRows.filter((job) => ['failed', 'recovery_required'].includes(job.status)).length
  const latestJob = jobRows[0]
  const jobStateClass = failedJobCount > 0 ? 'text-rose-300' : activeJobCount > 0 ? 'text-amber-300' : 'text-emerald-300'

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/75">Operations center</p>
          <h1 className="text-2xl font-bold">System</h1>
        </div>
        <p className="text-xs text-gray-400">Storage-safe automation, maintenance health, and recovery signals</p>
      </div>

      <div className="rounded-2xl border border-cyan-500/30 bg-[linear-gradient(135deg,rgba(8,47,73,0.7),rgba(17,24,39,0.92),rgba(67,20,7,0.4))] p-5 shadow-[0_18px_60px_rgba(3,7,18,0.45)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/80">Maintenance Intelligence</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Premium Utilities Health</h2>
            <p className="mt-1 text-xs text-gray-300">Telemetry-aware maintenance scoring with safe-action recommendations.</p>
          </div>
          <button
            onClick={loadMaintenanceInsights}
            className="flex items-center gap-1 rounded-md border border-cyan-400/40 px-2.5 py-1 text-xs text-cyan-200 hover:bg-cyan-500/10"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-gray-400"><GaugeCircle size={12} /> Score</div>
            <p className={`mt-1 text-2xl font-bold ${maintenanceStateClass}`}>{fmtPct(maintenanceInsights?.maintenance_score ?? 0)}</p>
            <p className="text-[11px] text-gray-400">{maintenanceInsights?.maintenance_state ?? 'unknown'}</p>
          </div>
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-gray-400"><HardDrive size={12} /> Reclaimable</div>
            <p className="mt-1 text-xl font-semibold text-white">{fmtBytes(cleanupPreview?.estimated_reclaimable_bytes ?? 0)}</p>
            <p className="text-[11px] text-gray-400">from {cleanupPreview?.duplicates_found ?? 0} duplicate titles</p>
          </div>
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-gray-400"><Sparkles size={12} /> Confidence</div>
            <p className="mt-1 text-xl font-semibold text-white">{confidenceTotal}</p>
            <p className="text-[11px] text-gray-400">high {confidence.high ?? 0} · medium {confidence.medium ?? 0} · low {confidence.low ?? 0}</p>
          </div>
        </div>
        {(maintenanceInsights?.recommendations?.length ?? 0) > 0 && (
          <div className="mt-4 rounded-xl border border-amber-500/25 bg-amber-500/10 p-3">
            <p className="text-xs font-medium text-amber-200">Recommended next actions</p>
            <div className="mt-1.5 space-y-1">
              {maintenanceInsights?.recommendations.slice(0, 2).map((item) => (
                <p key={`${item.title}-${item.priority}`} className="text-xs text-amber-100/90">{item.title}: {item.detail}</p>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-emerald-500/25 bg-[linear-gradient(135deg,rgba(6,78,59,0.45),rgba(17,24,39,0.92),rgba(8,47,73,0.45))] p-5 shadow-[0_18px_60px_rgba(3,7,18,0.45)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-emerald-200/80">NAS Pressure</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Network Share Stability</h2>
            <p className="mt-1 text-xs text-gray-300">Tracks recent NAS-targeted replacements and policy blocks, then recommends a safe profile.</p>
          </div>
          <button
            onClick={loadNasPressure}
            className="flex items-center gap-1 rounded-md border border-emerald-400/40 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/10"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-400">Pressure</p>
            <p className={`mt-1 text-xl font-semibold capitalize ${nasPressureClass}`}>{nasPressure?.pressure_state ?? 'unknown'}</p>
          </div>
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-400">NAS Replacements (24h)</p>
            <p className="mt-1 text-xl font-semibold text-white">{nasPressure?.recent?.replacements_24h ?? 0}</p>
          </div>
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-400">Writes (24h)</p>
            <p className="mt-1 text-xl font-semibold text-white">{fmtBytes(nasPressure?.recent?.replacement_bytes_24h ?? 0)}</p>
          </div>
          <div className="rounded-xl border border-gray-700/70 bg-gray-900/55 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-400">Policy Blocks (24h)</p>
            <p className="mt-1 text-xl font-semibold text-white">{nasPressure?.recent?.nas_rejects_24h ?? 0}</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {(['gentle', 'balanced', 'aggressive'] as const).map((preset) => (
            <button
              key={preset}
              onClick={() => { void applyNasPreset(preset) }}
              disabled={!!nasPresetApplying}
              className={`flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs capitalize disabled:opacity-60 ${nasPressure?.recommended_preset === preset ? 'border-emerald-300/60 bg-emerald-300/15 text-emerald-100' : 'border-gray-600 text-gray-200 hover:bg-gray-700/50'}`}
              title={preset === 'gentle' ? 'Best for unstable NAS links' : preset === 'balanced' ? 'Recommended default profile' : 'Higher throughput on stable NAS setups'}
            >
              <SlidersHorizontal size={12} />
              {nasPresetApplying === preset ? `Applying ${preset}...` : `${preset} preset`}
            </button>
          ))}
          <button
            onClick={() => { void restorePreviousNasProfile() }}
            disabled={!hasPresetSnapshot || !!nasPresetApplying}
            className="flex items-center gap-1 rounded-md border border-gray-600 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-700/50 disabled:opacity-40"
            title="Restore schedule/NAS values from before the last preset apply"
          >
            <SlidersHorizontal size={12} />
            {nasPresetApplying === 'restore' ? 'Restoring...' : 'Restore Previous'}
          </button>
        </div>

        <div className="mt-3 rounded-lg border border-gray-700 bg-gray-900/55 p-3">
          <p className="text-xs text-gray-300">Tracked NAS paths: {(nasPressure?.nas_prefixes?.length ?? 0) ? nasPressure?.nas_prefixes.join(', ') : 'none configured; add the real path in Settings'}</p>
          <p className="mt-1 text-xs text-gray-400">NAS policy: {nasPressure?.nas_policy_enabled ? 'enabled' : 'disabled'}</p>
          {(nasPressure?.recommendations?.length ?? 0) > 0 && (
            <div className="mt-2 space-y-1">
              {nasPressure?.recommendations.slice(0, 2).map((item) => (
                <p key={item} className="text-xs text-emerald-100/90">{item}</p>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-cyan-400/25 bg-gray-950/70 p-5 shadow-[0_18px_60px_rgba(3,7,18,0.42)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/80">Storage Safety</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Guarded File Operations</h2>
            <p className="mt-1 max-w-2xl text-xs text-gray-300">
              Replacement, duplicate cleanup, orphan cleanup, failed-download cleanup, and recycle purges now route through locked storage operations.
            </p>
          </div>
          <button
            onClick={() => { void runStorageGuardCheck() }}
            disabled={storageGuardLoading}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-cyan-300/40 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-400/10 disabled:opacity-50"
          >
            <ShieldCheck size={14} className={storageGuardLoading ? 'animate-pulse' : ''} />
            {storageGuardLoading ? 'Checking' : 'Check Path'}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Preflight</p>
            <p className={`mt-1 text-lg font-semibold ${storageGuardClass}`}>{storageGuardState}</p>
            <p className="mt-1 text-[11px] text-gray-500">path, parent, free space</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Path Class</p>
            <p className="mt-1 text-lg font-semibold text-white">{storageGuard?.classification ?? (nasPressure?.nas_policy_enabled ? 'nas-aware' : 'local')}</p>
            <p className="mt-1 truncate text-[11px] text-gray-500">{storageGuard?.matched_prefix ?? nasPressure?.nas_prefixes?.[0] ?? 'no prefix selected'}</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Operation Locks</p>
            <p className={`mt-1 text-lg font-semibold ${storageFailed > 0 ? 'text-amber-300' : 'text-emerald-300'}`}>
              {storageCompleted}
            </p>
            <p className="mt-1 text-[11px] text-gray-500">{storageFailed} failed operations</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">NAS Cooldown</p>
            <p className={`mt-1 text-lg font-semibold ${storageCooldownClass}`}>
              {nasPolicy?.cooldown_active ? `${nasPolicy.cooldown_remaining_seconds}s` : 'clear'}
            </p>
            <p className="mt-1 text-[11px] text-gray-500">{nasPolicy?.active_operations ?? 0} active NAS ops</p>
          </div>
        </div>

        {storageGuard && (
          <div className="mt-4 rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <p className="break-all text-xs text-gray-300">{storageGuard.path}</p>
              <p className="text-xs text-gray-500">{storageGuard.free_bytes != null ? `${fmtBytes(storageGuard.free_bytes)} free` : 'free space unknown'}</p>
            </div>
            {storageGuard.messages.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {storageGuard.messages.slice(0, 4).map((message) => (
                  <span key={message} className="rounded-full border border-gray-700 bg-gray-950/70 px-2 py-1 text-[11px] text-gray-300">{message}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {storageOperations && (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-gray-500">24h NAS Writes</p>
              <p className="mt-1 text-base font-semibold text-white">{fmtBytes(nasPolicy?.write_bytes_used_24h ?? 0)}</p>
              <p className="mt-1 text-[11px] text-gray-500">{nasPolicy?.replacements_24h ?? 0} replacements counted</p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-gray-500">Recent History</p>
              <p className="mt-1 text-base font-semibold text-white">{storageOperations.history_size}</p>
              <p className="mt-1 text-[11px] text-gray-500">
                {persistedStorage?.available ? `${persistedStorage.history_size} persisted records` : 'in-memory operation records'}
              </p>
            </div>
            <button
              onClick={loadStorageOperations}
              className="flex min-h-[82px] items-center justify-center gap-2 rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-xs text-cyan-100 hover:bg-cyan-400/10"
            >
              <RefreshCw size={14} />
              Refresh storage state
            </button>
          </div>
        )}

        {recentStorageFailures.length > 0 && (
          <div className="mt-4 rounded-lg border border-amber-400/30 bg-amber-950/20 p-3">
            <p className="text-xs font-medium text-amber-100">
              Storage failures in the last {Math.max(1, Math.round((storageOperations?.recent_failure_window_seconds ?? 3600) / 60))} minutes
            </p>
            <div className="mt-2 space-y-2">
              {recentStorageFailures.slice(0, 3).map((item) => (
                <div key={`${item.operation}-${item.started_at}-${item.source_path}`} className="flex flex-col gap-1 border-t border-amber-400/10 pt-2 first:border-t-0 first:pt-0">
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-amber-100/90">
                    <span className="rounded-full border border-amber-300/30 px-2 py-0.5">{item.operation}</span>
                    <span>{item.purpose}</span>
                    <span className="text-amber-200/60">{item.source_classification}</span>
                  </div>
                  <p className="break-all text-[11px] text-gray-300">{item.error || item.source_path}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-amber-400/25 bg-gray-950/70 p-5 shadow-[0_18px_60px_rgba(3,7,18,0.38)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/80">Replacement Recovery</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Interrupted Operation Watch</h2>
            <p className="mt-1 max-w-2xl text-xs text-gray-300">
              Tracks risky replacement phases that moved originals, staged backups, or still need operator review after an interruption.
            </p>
          </div>
          <button
            onClick={loadReplacementRecovery}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-amber-300/40 px-3 py-1.5 text-xs text-amber-100 hover:bg-amber-400/10"
          >
            <RefreshCw size={14} />
            Refresh recovery
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">State</p>
            <p className={`mt-1 text-lg font-semibold capitalize ${recoveryClass}`}>{recoveryState.replace(/_/g, ' ')}</p>
            <p className="mt-1 text-[11px] text-gray-500">{recoveryRecords.length} active record(s)</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Needs Review</p>
            <p className={`mt-1 text-lg font-semibold ${recoveryRequired > 0 ? 'text-rose-300' : 'text-emerald-300'}`}>{recoveryRequired}</p>
            <p className="mt-1 text-[11px] text-gray-500">recovery-required replacements</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Running</p>
            <p className={`mt-1 text-lg font-semibold ${runningRecovery > 0 ? 'text-amber-300' : 'text-gray-300'}`}>{runningRecovery}</p>
            <p className="mt-1 text-[11px] text-gray-500">filesystem phases tracked</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Latest Phase</p>
            <div className="mt-1 truncate text-lg font-semibold">
              <StorageStateMark phase={latestRecoveryRecord?.phase} />
            </div>
            <p className="mt-1 truncate text-[11px] text-gray-500">{latestRecoveryRecord?.movie_title ?? 'no active replacement'}</p>
          </div>
        </div>

        {latestRecoveryRecord && (
          <div className={`mt-4 rounded-lg border p-3 ${latestRecoveryRecord.status === 'recovery_required' ? 'border-rose-400/30 bg-rose-950/20' : 'border-amber-400/25 bg-amber-950/15'}`}>
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium text-white">{latestRecoveryRecord.movie_title ?? `Replacement #${latestRecoveryRecord.id}`}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-gray-400">
                  <StorageStateMark phase={latestRecoveryRecord.phase} />
                  {latestRecoveryRecord.updated_at ? <span>updated {new Date(latestRecoveryRecord.updated_at).toLocaleString()}</span> : null}
                </p>
              </div>
              <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${latestRecoveryRecord.status === 'recovery_required' ? 'border-rose-300/40 text-rose-100' : 'border-amber-300/40 text-amber-100'}`}>
                {latestRecoveryRecord.status.replace(/_/g, ' ')}
              </span>
            </div>
            <div className="mt-3 grid gap-2 text-[11px] text-gray-300 sm:grid-cols-2">
              <p className="break-all"><span className="text-gray-500">target:</span> {latestRecoveryRecord.target_path ?? latestRecoveryRecord.mapped_path ?? 'unknown'}</p>
              <p className="break-all"><span className="text-gray-500">backup:</span> {latestRecoveryRecord.recycle_path ?? latestRecoveryRecord.fallback_backup_path ?? 'none recorded'}</p>
            </div>
            {latestRecoveryRecord.error_message && (
              <p className="mt-2 break-words text-xs text-rose-200">{latestRecoveryRecord.error_message}</p>
            )}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-sky-400/25 bg-gray-950/70 p-5 shadow-[0_18px_60px_rgba(3,7,18,0.36)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.22em] text-sky-200/80">Persistent Jobs</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Work Timeline</h2>
            <p className="mt-1 max-w-2xl text-xs text-gray-300">
              Manual scans, automation cycles, duplicate previews, cleanup runs, and scheduler actions now write durable job records.
            </p>
          </div>
          <button
            onClick={loadPersistentJobs}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-sky-300/40 px-3 py-1.5 text-xs text-sky-100 hover:bg-sky-400/10"
          >
            <RefreshCw size={14} />
            Refresh jobs
          </button>
          <Link
            to="/system/operations"
            className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600"
          >
            View all →
          </Link>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Recent Jobs</p>
            <p className="mt-1 text-lg font-semibold text-white">{jobRows.length}</p>
            <p className="mt-1 text-[11px] text-gray-500">latest persisted records</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Active</p>
            <p className={`mt-1 text-lg font-semibold ${activeJobCount > 0 ? 'text-amber-300' : 'text-emerald-300'}`}>{activeJobCount}</p>
            <p className="mt-1 text-[11px] text-gray-500">queued/running/cancelling</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Attention</p>
            <p className={`mt-1 text-lg font-semibold ${failedJobCount > 0 ? 'text-rose-300' : 'text-emerald-300'}`}>{failedJobCount}</p>
            <p className="mt-1 text-[11px] text-gray-500">failed or recovery-required</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Latest</p>
            <p className={`mt-1 truncate text-lg font-semibold capitalize ${jobStateClass}`}>{latestJob?.status?.replace(/_/g, ' ') ?? 'none'}</p>
            <p className="mt-1 truncate text-[11px] text-gray-500">{latestJob?.kind?.replace(/_/g, ' ') ?? 'no job history'}</p>
          </div>
        </div>

        <div className="mt-4 divide-y divide-gray-800 overflow-hidden rounded-lg border border-gray-800 bg-gray-900/60">
          {jobRows.length === 0 ? (
            <p className="px-3 py-4 text-sm text-gray-500">No persistent job history yet.</p>
          ) : (
            jobRows.slice(0, 5).map((job) => (
              <div key={job.id} className="px-3 py-2.5 text-xs">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-100">{job.kind.replace(/_/g, ' ')}</p>
                    <p className="mt-0.5 truncate text-gray-500">{job.id}</p>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 capitalize ${['failed', 'recovery_required'].includes(job.status) ? 'border-rose-300/40 text-rose-100' : ['queued', 'running', 'cancelling'].includes(job.status) ? 'border-amber-300/40 text-amber-100' : 'border-emerald-300/40 text-emerald-100'}`}>
                    {job.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="mt-1 text-gray-500">
                  attempt {job.attempt}/{job.max_attempts}
                  {job.created_at ? ` / queued ${new Date(job.created_at).toLocaleString()}` : ''}
                  {job.error_message ? ` / ${job.error_message}` : ''}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

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
      {quickStats && (
        <div className="bg-gray-900 rounded-xl p-5 grid grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-gray-400">Active Downloads</p>
            <p className="text-xl font-semibold">{quickStats.active_downloads ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Movies</p>
            <p className="text-xl font-semibold">{quickStats.total_movies ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Improved</p>
            <p className="text-xl font-semibold">{quickStats.improved ?? 0}</p>
          </div>
        </div>
      )}

      {/* Integration health */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold flex items-center justify-between">
          Integration Status
          <button onClick={loadServices} aria-label="Refresh integration status" title="Refresh" className="text-xs text-gray-400 hover:text-white">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="divide-y divide-gray-800">
          {(['plex', 'sabnzbd', 'nzbget', 'radarr', 'sonarr', 'prowlarr', 'tmdb'] as const).map((svc) => {
            const h = services?.[svc]
            const label = { plex: 'Plex', sabnzbd: 'SABnzbd', nzbget: 'NZBGet', radarr: 'Radarr', sonarr: 'Sonarr', prowlarr: 'Prowlarr', tmdb: 'TMDB' }[svc]
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

      {/* End-to-end health matrix */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold flex items-center justify-between">
          Health Matrix
          <button onClick={loadHealthMatrix} aria-label="Refresh health matrix" title="Refresh" className="text-xs text-gray-400 hover:text-white">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="px-4 py-2 text-xs text-gray-500">
          Overall: <span className={matrixStatusClass(healthMatrix?.status)}>{healthMatrix?.status ?? 'unknown'}</span>
        </div>
        <div className="divide-y divide-gray-800">
          {healthComponents.length === 0 ? (
            <p className="px-4 py-4 text-gray-500 text-sm">No health data yet.</p>
          ) : (
            healthComponents.map(([name, component]) => {
              const comp = component as { status?: string; detail?: string }
              return (
                <div key={name} className="px-4 py-3 flex items-center gap-3 text-sm">
                  {comp.status === 'healthy' ? (
                    <CheckCircle size={14} className="text-green-400 shrink-0" />
                  ) : comp.status === 'degraded' ? (
                    <XCircle size={14} className="text-yellow-300 shrink-0" />
                  ) : comp.status === 'disabled' ? (
                    <span className="w-3.5 h-3.5 rounded-full bg-gray-600 shrink-0" />
                  ) : (
                    <XCircle size={14} className="text-red-400 shrink-0" />
                  )}
                  <span className="w-32 font-medium capitalize">{name.replace(/_/g, ' ')}</span>
                  <span className="text-xs text-gray-400 truncate">{comp.detail ?? 'No details'}</span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Decision audit log */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold flex items-center justify-between">
          Release Decision Audit
          <button onClick={loadDecisionAudit} aria-label="Refresh decision audit" title="Refresh" className="text-xs text-gray-400 hover:text-white">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="divide-y divide-gray-800">
          {decisionAudit.length === 0 ? (
            <p className="px-4 py-4 text-gray-500 text-sm">No decision history yet.</p>
          ) : (
            decisionAudit.map((entry) => (
              <div key={entry.id} className="px-4 py-3 text-sm space-y-1">
                <div className="flex items-center gap-2">
                  {entry.decision === 'accept' ? (
                    <CheckCircle size={14} className="text-green-400 shrink-0" />
                  ) : (
                    <XCircle size={14} className="text-red-400 shrink-0" />
                  )}
                  <span className="font-medium truncate">{entry.release_title}</span>
                </div>
                <p className="text-xs text-gray-400">
                  {(entry.movie_title ?? 'Unknown movie')} · score {Number(entry.score ?? 0).toFixed(1)} · savings {Number(entry.savings_pct ?? 0).toFixed(1)}%
                </p>
                {entry.reject_reason && (
                  <p className="text-xs text-red-300">{entry.reject_reason}</p>
                )}
                {!entry.reject_reason && entry.notes && (
                  <p className="text-xs text-gray-500 truncate">{entry.notes}</p>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Recycling folder */}
      <div className="bg-gray-900 rounded-xl p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="font-semibold">Recycling Folder</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {recyclingInfo?.enabled && recyclingInfo?.path
              ? `Recycling folder is ${fmtBytes(recyclingInfo?.bytes ?? 0)}${recyclingInfo?.files ? ` across ${recyclingInfo.files} files` : ''} — click purge to permanently delete everything in that folder.`
              : 'No recycling folder configured.'}
          </p>
          {recyclingInfo?.path && (
            <p className="text-xs text-gray-500 mt-1 break-all">{recyclingInfo.path}</p>
          )}
        </div>
        <div className="flex w-full gap-2 sm:w-auto sm:shrink-0">
          <button
            onClick={() => { void loadRecyclingInfo(true) }}
            disabled={recyclingLoading || recyclingPurging}
            className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50 sm:flex-none"
          >
            <RefreshCw size={14} className={recyclingLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={purgeRecyclingBin}
            disabled={
              recyclingPurging
              || !recyclingInfo?.enabled
              || !recyclingInfo?.exists
              || (recyclingInfo?.files ?? 0) === 0
            }
            className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-red-700 text-sm text-white hover:bg-red-600 disabled:opacity-50 sm:flex-none"
          >
            <Trash2 size={14} />
            {recyclingPurging ? 'Purging…' : 'Purge'}
          </button>
        </div>
      </div>

      {/* Scan library */}
      <div className="bg-gray-900 rounded-xl p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-semibold">Library Scan</h2>
          <p className="text-xs text-gray-400 mt-0.5">Sync movies from Plex and enrich with TMDB metadata</p>
        </div>
        <button
          onClick={scanNow}
          disabled={scanning}
          className="flex items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
          {scanning ? 'Scanning…' : 'Scan Now'}
        </button>
      </div>

      {/* Duplicate cleanup */}
      <div className="bg-gray-900 rounded-xl p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="font-semibold">Duplicate File Cleanup</h2>
          <p className="text-xs text-gray-400 mt-0.5">Preview-first workflow. Estimate reclaimable space and confidence before any deletion or recycle action.</p>
          {cleanupPreview?.status === 'ok' && (
            <p className="text-xs text-gray-500 mt-1">
              {cleanupPreview.duplicates_found} duplicate titles · {fmtBytes(cleanupPreview.estimated_reclaimable_bytes)} recoverable
              {cleanupPreview.truncated ? ' (sampled scan)' : ''}
            </p>
          )}
          {cleanupPreview?.status === 'error' && (
            <p className="text-xs text-rose-300 mt-1">Preview error: {cleanupPreview.reason ?? 'Unknown error'}</p>
          )}
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <button
            onClick={() => { void loadCleanupPreview(true, true) }}
            disabled={cleanupPreviewLoading || cleaning}
            className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50 sm:flex-none"
          >
            <RefreshCw size={14} className={cleanupPreviewLoading ? 'animate-spin' : ''} />
            {cleanupPreviewLoading ? 'Loading…' : 'Preview'}
          </button>
          <button
            onClick={cleanDuplicates}
            disabled={cleaning}
            className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-100 text-gray-900 text-sm hover:bg-white disabled:opacity-50 sm:flex-none"
          >
            <ShieldAlert size={14} className={cleaning ? 'animate-pulse' : ''} />
            {cleaning ? 'Starting…' : 'Run Safe Cleanup'}
          </button>
        </div>
      </div>

      {cleanupPreview?.sample?.length ? (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold">Duplicate Preview Samples</div>
          <div className="divide-y divide-gray-800">
            {cleanupPreview.sample.slice(0, 6).map((item) => (
              <div key={`${item.title}-${item.best_file}`} className="px-4 py-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium truncate">{item.title}</p>
                  <span className="text-xs text-gray-400">{item.duplicate_count} extra file(s)</span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{fmtBytes(item.estimated_reclaimable_bytes)} reclaimable · confidence {item.confidence}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Automation cycle */}
      <div className="bg-gray-900 rounded-xl p-5 space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-semibold">Automation Cycle</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {cycle.running ? '🟢 Running' : '⚪ Idle'}
            {cycle.stop_requested ? ' — stop requested' : ''}
          </p>
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          <button
            onClick={() => { void runPreflight() }}
            disabled={preflightLoading || starting || !!cycle.running}
            className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-gray-700 text-sm hover:bg-gray-600 disabled:opacity-50 sm:flex-none"
          >
            <ShieldCheck size={14} />
            {preflightLoading ? 'Checking...' : 'Preflight'}
          </button>
          {cycle.running ? (
            <button
              onClick={stopCycle}
              className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-red-700 text-sm text-white hover:bg-red-600 sm:flex-none"
            >
              <Square size={14} /> Stop
            </button>
          ) : (
            <button
              onClick={startCycle}
              disabled={starting}
              className="flex flex-1 items-center justify-center gap-2 px-3 py-1.5 rounded bg-brand-green text-white text-sm disabled:opacity-50 sm:flex-none"
            >
              <Play size={14} /> {starting ? 'Starting…' : 'Run Now'}
            </button>
          )}
        </div>
        </div>

        {preflight && (
          <div className="rounded-lg bg-gray-800/70 border border-gray-700 overflow-hidden">
            <div className="px-3 py-2 text-xs flex items-center justify-between gap-3 border-b border-gray-700">
              <span className="font-medium">Last preflight</span>
              <span className={preflightStatusClass(preflight.status)}>{preflight.status}</span>
            </div>
            <div className="divide-y divide-gray-700">
              {preflight.checks.map((item) => (
                <div key={`${item.name}-${item.message}`} className="px-3 py-2 text-xs flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                  <span className={`w-14 uppercase text-[11px] ${preflightStatusClass(item.status)}`}>{item.status}</span>
                  <span className="font-medium text-gray-200 sm:w-40">{item.name}</span>
                  <span className="text-gray-400 break-words">{item.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
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

      {/* Shared confirm dialog — used for destructive actions and preflight-warning confirmations */}
      <ConfirmDialog
        open={confirmDialog.open}
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmLabel={confirmDialog.confirmLabel ?? 'Confirm'}
        destructive={confirmDialog.destructive ?? true}
        loading={recyclingPurging || cleaning}
        onConfirm={confirmDialog.onConfirm}
        children={confirmDialog.children}
        onCancel={() => {
          setConfirmDialog((d) => ({ ...d, open: false }))
          confirmDialog.onCancel?.()
        }}
      />
    </div>
  )
}

