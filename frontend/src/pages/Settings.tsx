import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import TestConnectionButton from '@/components/TestConnectionButton'

export default function Settings() {
  const { toast } = useToast()
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {})
  }, [])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    try {
      await api.updateSettings(settings)
      toast('Settings saved', 'success')
    } catch {
      toast('Failed to save settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  const set = (path: string[], value: string | number | boolean) => {
    setSettings((prev) => {
      const next = JSON.parse(JSON.stringify(prev))
      let cur: Record<string, unknown> = next
      path.slice(0, -1).forEach((k) => { cur = cur[k] as Record<string, unknown> })
      cur[path[path.length - 1]] = value
      return next
    })
  }

  if (!settings) return <div className="text-gray-400">Loading settings…</div>

  function field(label: string, path: string[], type: string = 'text') {
    const val = path.reduce((o: unknown, k) => (o as Record<string, unknown>)?.[k], settings) as string | number | undefined
    return (
      <div>
        <label className="block text-xs text-gray-400 mb-1">{label}</label>
        <input
          type={type}
          value={val ?? ''}
          onChange={(e) => set(path, e.target.value)}
          className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
          placeholder={type === 'password' ? '••••••••' : ''}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold flex-1">Settings</h1>
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-brand-green text-white text-sm disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      {/* Plex */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Plex</h2>
          <TestConnectionButton service="plex" />
        </div>
        {field('URL', ['plex', 'url'])}
        {field('Token', ['plex', 'token'], 'password')}
      </section>

      {/* TMDB */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">TMDB</h2>
          <TestConnectionButton service="tmdb" />
        </div>
        {field('API Key', ['tmdb', 'api_key'], 'password')}
      </section>

      {/* SABnzbd */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">SABnzbd</h2>
          <TestConnectionButton service="sabnzbd" />
        </div>
        {field('URL', ['sabnzbd', 'url'])}
        {field('API Key', ['sabnzbd', 'api_key'], 'password')}
        {field('Category', ['sabnzbd', 'category'])}
      </section>

      {/* Prowlarr */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Prowlarr (optional)</h2>
          <TestConnectionButton service="prowlarr" />
        </div>
        {field('URL', ['prowlarr', 'url'])}
        {field('API Key', ['prowlarr', 'api_key'], 'password')}
      </section>

      {/* Plex library sections */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <h2 className="font-semibold">Plex Library Sections</h2>
        <p className="text-xs text-gray-400">Comma-separated section names to scan (leave blank to scan all movie libraries)</p>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Library Sections</label>
          <input
            type="text"
            value={((settings?.plex as Record<string,unknown>)?.library_sections as string[] | undefined)?.join(', ') ?? ''}
            onChange={(e) => {
              const val = e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
              set(['plex', 'library_sections'], val as unknown as string)
            }}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            placeholder="Movies, 4K Movies"
          />
        </div>
      </section>

      {/* Comparison */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <h2 className="font-semibold">Comparison Rules</h2>
        {field('Min Savings %', ['comparison', 'min_savings_percent'], 'number')}
        {field('Downgrade Min Savings %', ['comparison', 'downgrade_min_savings_percent'], 'number')}
        {field('Minimum File Size (MB)', ['comparison', 'minimum_file_size_mb'], 'number')}
        {field('Max Candidate Age (days)', ['comparison', 'max_candidate_age_days'], 'number')}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="allow_downgrade"
            checked={!!((settings?.comparison as Record<string,unknown>)?.allow_resolution_downgrade)}
            onChange={(e) => set(['comparison', 'allow_resolution_downgrade'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="allow_downgrade" className="text-sm">Allow resolution downgrade (if savings are large enough)</label>
        </div>
      </section>

      {/* Schedule */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <h2 className="font-semibold">Schedule</h2>
        {field('Nightly Start Time (UTC, HH:MM)', ['schedule', 'start_time'])}
        {field('Nightly End Time (UTC, HH:MM)', ['schedule', 'end_time'])}
        {field('Max Downloads per Night', ['schedule', 'max_downloads_per_night'], 'number')}
        {field('Throttle between downloads (seconds)', ['schedule', 'throttle_seconds'], 'number')}
      </section>
    </div>
  )
}
