import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Clock, Download, Film, HardDrive, HeartPulse, Inbox, Play, RefreshCw, TrendingDown, XCircle } from 'lucide-react'
import StatCard from '@/components/StatCard'
import ActivityItem from '@/components/ActivityItem'
import { useToast } from '@/components/Toast'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import { useNasPresetManager } from '@/hooks/useNasPreset'
import type { DashboardStats, ActivityEntry, IntegrationMatrix, NasPressure } from '@/lib/types'
import { formatGB } from '@/lib/format'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts'

function formatDate(value?: string): string {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [history, setHistory] = useState<{ date: string; savings_bytes: number }[]>([])
  const [matrix, setMatrix] = useState<IntegrationMatrix | null>(null)
  const [nasPressure, setNasPressure] = useState<NasPressure | null>(null)
  const [cycling, setCycling] = useState(false)
  const [scanning, setScanning] = useState(false)

  const reload = () => {
    api.stats().then(setStats).catch(() => {})
    api.recentActivity(10).then(setActivity).catch(() => {})
    api.savingsHistory(30).then(setHistory).catch(() => {})
    api.integrationMatrix().then(setMatrix).catch(() => {})
    api.nasPressure().then((d) => setNasPressure(d as NasPressure)).catch(() => {})
  }

  const {
    applyNasPreset,
    restorePreviousNasProfile,
    applying: presetApplying,
    hasSnapshot: hasPresetSnapshot,
  } = useNasPresetManager(reload)

  useEffect(() => {
    reload()
  }, [])

  // Live updates via Socket.IO
  useSocket('scan:started', () => setScanning(true))
  useSocket('scan:completed', () => {
    setScanning(false)
    reload()
  })
  useSocket('replace:completed', reload)
  useSocket('download:progress', () => api.stats().then(setStats).catch(() => {}))
  useSocket('orchestrator:status', (payload) => {
    const state = payload as { running?: boolean }
    setCycling(Boolean(state.running))
    if (!state.running) reload()
  })

  const { toast } = useToast()

  const runCycle = async () => {
    setCycling(true)
    try {
      await api.startCycle()
      toast('Automation cycle started', 'success')
    } catch {
      setCycling(false)
      toast('Failed to start cycle', 'error')
    }
  }

  const scanLibrary = async () => {
    setScanning(true)
    try {
      await api.scanLibrary()
      toast('Library scan started — this may take a minute', 'info')
    } catch {
      setScanning(false)
      toast('Failed to start scan', 'error')
    }
  }

  const checklist = [
    {
      key: 'plex',
      label: 'Connect Plex',
      done: !!matrix?.services?.some((s) => s.key === 'plex' && s.status === 'connected'),
      href: '/settings#connections',
    },
    {
      key: 'provider',
      label: 'Configure Search Provider',
      done: !!matrix?.services?.some((s) => (s.key === 'prowlarr' || s.key === 'indexers') && (s.status === 'connected' || s.status === 'degraded')),
      href: '/settings#indexers',
    },
    {
      key: 'nas',
      label: 'Set NAS Movie Path',
      done: (nasPressure?.nas_prefixes?.length ?? 0) > 0,
      href: '/settings#files',
    },
    {
      key: 'scan',
      label: 'Run First Library Scan',
      done: !!stats?.last_successful_scan,
      href: '/library',
    },
  ]
  const completedChecklist = checklist.filter((item) => item.done).length

  const systemSummary = [
    {
      label: 'Integrations',
      value: matrix?.status ?? 'unknown',
      tone:
        matrix?.status === 'connected'
          ? 'text-emerald-300 border-emerald-400/30 bg-emerald-500/10'
          : matrix?.status === 'degraded'
            ? 'text-amber-300 border-amber-400/30 bg-amber-500/10'
            : 'text-rose-300 border-rose-400/30 bg-rose-500/10',
    },
    {
      label: 'NAS Pressure',
      value: nasPressure?.pressure_state ?? 'unknown',
      tone:
        nasPressure?.pressure_state === 'low'
          ? 'text-emerald-300 border-emerald-400/30 bg-emerald-500/10'
          : nasPressure?.pressure_state === 'medium'
            ? 'text-amber-300 border-amber-400/30 bg-amber-500/10'
            : 'text-rose-300 border-rose-400/30 bg-rose-500/10',
    },
    {
      label: 'Cycle',
      value: cycling ? 'starting' : 'ready',
      tone: cycling ? 'text-cyan-300 border-cyan-400/30 bg-cyan-500/10' : 'text-gray-200 border-white/15 bg-white/5',
    },
  ]

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/10 bg-[linear-gradient(135deg,rgba(31,191,143,0.10),rgba(245,158,11,0.06)_38%,rgba(17,24,39,0.76)_100%)] p-5 md:p-6 shadow-[0_26px_46px_-34px_rgba(0,0,0,0.9)]">
        <div className="flex flex-col gap-4 md:flex-row md:items-center">
          <div className="flex-1">
            <h1 className="text-2xl font-bold">Dashboard</h1>
            <p className="mt-1 text-sm text-gray-300/90">Monitor cycle health, trigger scans, and review improvement momentum.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={scanLibrary}
              disabled={scanning}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800/85 text-sm hover:bg-gray-700 disabled:opacity-50 border border-white/10"
            >
              <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
              {scanning ? 'Scanning…' : 'Scan Library'}
            </button>
            <button
              onClick={runCycle}
              disabled={cycling}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-green text-white text-sm disabled:opacity-50 shadow-[0_12px_24px_-14px_rgba(31,191,143,0.85)]"
            >
              <Play size={14} />
              {cycling ? 'Starting…' : 'Run Cycle'}
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-gray-900/70 p-3">
        <div className="grid gap-2 sm:grid-cols-3">
          {systemSummary.map((item) => (
            <div key={item.label} className={`rounded-md border px-3 py-2 ${item.tone}`}>
              <p className="text-[10px] uppercase tracking-wide opacity-80">{item.label}</p>
              <p className="mt-0.5 text-sm font-semibold capitalize">{item.value}</p>
            </div>
          ))}
        </div>
      </div>

      {(nasPressure?.pressure_state === 'high' || nasPressure?.pressure_state === 'medium') && (
        <div className={`rounded-xl border p-4 ${nasPressure?.pressure_state === 'high' ? 'border-rose-400/40 bg-rose-500/10' : 'border-amber-400/35 bg-amber-500/10'}`}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold">
                {nasPressure.pressure_state === 'high' ? 'NAS pressure is high' : 'NAS pressure is elevated'}
              </p>
              <p className="text-xs text-gray-300 mt-1">
                {nasPressure.recent.replacements_24h} NAS replacements in 24h, {formatGB(nasPressure.recent.replacement_bytes_24h)} written.
                Apply a safer profile to reduce Z-drive churn.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => { void applyNasPreset('gentle') }}
                disabled={!!presetApplying}
                className="px-3 py-1.5 rounded-md text-xs bg-gray-800 border border-white/10 hover:bg-gray-700 disabled:opacity-60"
              >
                {presetApplying === 'gentle' ? 'Applying...' : 'Apply Gentle'}
              </button>
              <button
                onClick={() => { void applyNasPreset('balanced') }}
                disabled={!!presetApplying}
                className="px-3 py-1.5 rounded-md text-xs bg-brand-green text-white disabled:opacity-60"
              >
                {presetApplying === 'balanced' ? 'Applying...' : 'Apply Balanced'}
              </button>
              <button
                onClick={() => { void restorePreviousNasProfile() }}
                disabled={!hasPresetSnapshot || !!presetApplying}
                className="px-3 py-1.5 rounded-md text-xs bg-gray-800 border border-white/10 hover:bg-gray-700 disabled:opacity-40"
              >
                {presetApplying === 'restore' ? 'Restoring...' : 'Restore Previous'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-white/10 bg-gray-900/80 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-100">Quick Start Checklist</h2>
            <p className="text-xs text-gray-400 mt-1">{completedChecklist}/{checklist.length} completed</p>
          </div>
          {completedChecklist < checklist.length && (
            <button
              onClick={() => { void scanLibrary() }}
              disabled={scanning}
              className="px-3 py-1.5 rounded-md text-xs bg-gray-800 border border-white/10 hover:bg-gray-700 disabled:opacity-60"
            >
              {scanning ? 'Scanning...' : 'Run Scan'}
            </button>
          )}
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {checklist.map((item) => (
            <div key={item.key} className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/60 px-3 py-2">
              <div className="flex items-center gap-2 text-sm">
                {item.done ? (
                  <CheckCircle2 size={14} className="text-green-400" />
                ) : (
                  <AlertTriangle size={14} className="text-amber-300" />
                )}
                <span>{item.label}</span>
              </div>
              {!item.done && (
                <Link to={item.href} className="text-xs text-cyan-300 hover:text-cyan-200">Open</Link>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard label="Total Movies" value={stats?.total_movies ?? '—'} icon={Film} />
        <StatCard label="Improved" value={stats?.improved ?? '—'} icon={TrendingDown} color="text-green-400" />
        <StatCard
          label="Total Savings"
          value={stats ? formatGB(stats.total_savings_bytes) : '—'}
          icon={HardDrive}
          color="text-blue-400"
        />
        <StatCard label="Active Downloads" value={stats?.active_downloads ?? '—'} icon={Download} color="text-orange-400" />
      </div>

      {stats && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard label="Library Size" value={formatGB(stats.library_size_bytes)} icon={HardDrive} />
          <StatCard label="Pending Candidates" value={stats.pending} icon={Inbox} color="text-blue-400" />
          <StatCard label="Failed Items" value={stats.failed_items} icon={AlertTriangle} color="text-red-400" />
          <StatCard label="Last Scan" value={formatDate(stats.last_successful_scan)} icon={Clock} color="text-purple-300" />
        </div>
      )}

      {matrix && (
        <div className="bg-gray-900 rounded-xl p-5">
          <div className="mb-4 flex items-center gap-3">
            <HeartPulse size={18} className={matrix.status === 'connected' ? 'text-green-400' : matrix.status === 'degraded' ? 'text-yellow-400' : 'text-red-400'} />
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-gray-200">Integration Matrix</h2>
              <p className="text-xs text-gray-500">Active downloader: {matrix.active_download_client.toUpperCase()}</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {matrix.services.map((service) => {
              const Icon = service.status === 'connected' ? CheckCircle2 : service.status === 'disabled' ? XCircle : AlertTriangle
              const color = service.status === 'connected' ? 'text-green-400' : service.status === 'disabled' ? 'text-gray-500' : service.status === 'degraded' ? 'text-yellow-400' : 'text-red-400'
              return (
                <div key={service.key} className="rounded-lg border border-gray-800 bg-gray-950/40 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <Icon size={15} className={color} />
                    <span className="font-medium text-sm">{service.name}</span>
                    {service.required && <span className="ml-auto rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] uppercase text-red-300">required</span>}
                  </div>
                  <p className="text-xs leading-5 text-gray-400">{service.purpose}</p>
                  <p className={`mt-2 text-xs font-semibold capitalize ${color}`}>{service.status}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 mb-4">Cumulative Space Reclaimed (Last 30 Days)</h2>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={history}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => v.slice(0, 10)} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => `${(v / 1024 ** 3).toFixed(1)}G`} />
              <Tooltip
                contentStyle={{ background: '#111827', border: 'none' }}
                formatter={(v: number) => [formatGB(v, 2), 'Total Reclaimed']}
                labelFormatter={(l) => l.slice(0, 10)}
              />
              <Area type="monotone" dataKey="cumulative_bytes" stroke="#1fbf8f" fill="#1fbf8f33" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="bg-gray-900 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-400 mb-2">Recent Activity</h2>
        {activity.length === 0 ? (
          <p className="text-gray-600 text-sm">No activity yet.</p>
        ) : (
          activity.map((entry) => <ActivityItem key={entry.id} entry={entry} />)
        )}
      </div>
    </div>
  )
}
