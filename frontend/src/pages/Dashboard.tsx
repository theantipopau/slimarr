import { useEffect, useState } from 'react'
import { Film, HardDrive, TrendingDown, Download, Play, RefreshCw } from 'lucide-react'
import StatCard from '@/components/StatCard'
import ActivityItem from '@/components/ActivityItem'
import { useToast } from '@/components/Toast'
import { api } from '@/lib/api'
import { useSocket } from '@/hooks/useSocket'
import type { DashboardStats, ActivityEntry } from '@/lib/types'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts'

function formatGB(bytes: number): string {
  return (bytes / 1e9).toFixed(1) + ' GB'
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [history, setHistory] = useState<{ date: string; savings_bytes: number }[]>([])
  const [cycling, setCycling] = useState(false)
  const [scanning, setScanning] = useState(false)

  const reload = () => {
    api.stats().then(setStats).catch(() => {})
    api.recentActivity(10).then(setActivity).catch(() => {})
    api.savingsHistory(30).then(setHistory).catch(() => {})
  }

  useEffect(() => { reload() }, [])

  // Live updates via Socket.IO
  useSocket('scan:completed', reload)
  useSocket('replace:completed', reload)
  useSocket('download:progress', () => api.stats().then(setStats).catch(() => {}))

  const { toast } = useToast()

  const runCycle = async () => {
    setCycling(true)
    try {
      await api.startCycle()
      toast('Automation cycle started', 'success')
    } catch { toast('Failed to start cycle', 'error') }
    setTimeout(() => { reload(); setCycling(false) }, 2000)
  }

  const scanLibrary = async () => {
    setScanning(true)
    try {
      await api.scanLibrary()
      toast('Library scan started — this may take a minute', 'info')
    } catch { toast('Failed to start scan', 'error') }
    setTimeout(() => { reload(); setScanning(false) }, 8000)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold flex-1">Dashboard</h1>
        <button
          onClick={scanLibrary}
          disabled={scanning}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-sm hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
          {scanning ? 'Scanning…' : 'Scan Library'}
        </button>
        <button
          onClick={runCycle}
          disabled={cycling}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-green text-white text-sm disabled:opacity-50"
        >
          <Play size={14} />
          {cycling ? 'Starting…' : 'Run Cycle'}
        </button>
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

      {history.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 mb-4">Cumulative Space Reclaimed (Last 30 Days)</h2>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={history}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => v.slice(0, 10)} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => `${(v / 1e9).toFixed(1)}G`} />
              <Tooltip
                contentStyle={{ background: '#111827', border: 'none' }}
                formatter={(v: number) => [`${(v / 1e9).toFixed(2)} GB`, 'Total Reclaimed']}
                labelFormatter={(l) => l.slice(0, 10)}
              />
              <Area type="monotone" dataKey="cumulative_bytes" stroke="#4CAF50" fill="#4CAF5033" strokeWidth={2} />
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
