import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import TestConnectionButton from '@/components/TestConnectionButton'
import { Plus, Trash2 } from 'lucide-react'

interface Indexer {
  name: string
  url: string
  api_key: string
  categories: number[]
}

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
        <p className="text-xs text-gray-400">If disabled, Slimarr will use the Newznab indexers configured below instead.</p>
        {field('URL', ['prowlarr', 'url'])}
        {field('API Key', ['prowlarr', 'api_key'], 'password')}
      </section>

      {/* Newznab Indexers */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold">Newznab Indexers</h2>
            <p className="text-xs text-gray-400 mt-1">Add your Usenet indexers directly. Used when Prowlarr is disabled or returns no results.</p>
          </div>
          <button
            onClick={() => {
              const indexers = ((settings?.indexers as Indexer[]) ?? []).slice()
              indexers.push({ name: '', url: '', api_key: '', categories: [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060] })
              setSettings((prev) => ({ ...prev!, indexers }))
            }}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-brand-green text-white text-xs hover:bg-green-600"
          >
            <Plus size={14} /> Add Indexer
          </button>
        </div>
        {((settings?.indexers as Indexer[]) ?? []).length === 0 && (
          <p className="text-sm text-gray-500 italic">No indexers configured. Click &quot;Add Indexer&quot; to get started.</p>
        )}
        {((settings?.indexers as Indexer[]) ?? []).map((idx, i) => (
          <div key={i} className="bg-gray-800 rounded-lg p-4 space-y-3 relative">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-300">Indexer {i + 1}{idx.name ? ` — ${idx.name}` : ''}</span>
              <div className="flex items-center gap-2">
                <TestConnectionButton
                  service={`indexer-${i}`}
                  body={{ name: idx.name, url: idx.url, api_key: idx.api_key, categories: idx.categories }}
                />
                <button
                  onClick={() => {
                    const indexers = ((settings?.indexers as Indexer[]) ?? []).filter((_, j) => j !== i)
                    setSettings((prev) => ({ ...prev!, indexers }))
                  }}
                  className="p-1.5 rounded hover:bg-red-900/50 text-red-400"
                  title="Remove indexer"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Name</label>
                <input
                  type="text"
                  value={idx.name}
                  onChange={(e) => {
                    const indexers = ((settings?.indexers as Indexer[]) ?? []).slice()
                    indexers[i] = { ...indexers[i], name: e.target.value }
                    setSettings((prev) => ({ ...prev!, indexers }))
                  }}
                  className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
                  placeholder="NZBgeek"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">URL</label>
                <input
                  type="text"
                  value={idx.url}
                  onChange={(e) => {
                    const indexers = ((settings?.indexers as Indexer[]) ?? []).slice()
                    indexers[i] = { ...indexers[i], url: e.target.value }
                    setSettings((prev) => ({ ...prev!, indexers }))
                  }}
                  className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
                  placeholder="https://api.nzbgeek.info"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">API Key</label>
              <input
                type="password"
                value={idx.api_key}
                onChange={(e) => {
                  const indexers = ((settings?.indexers as Indexer[]) ?? []).slice()
                  indexers[i] = { ...indexers[i], api_key: e.target.value }
                  setSettings((prev) => ({ ...prev!, indexers }))
                }}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
                placeholder="••••••••"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Categories (comma-separated Newznab IDs)</label>
              <input
                type="text"
                value={idx.categories.join(', ')}
                onChange={(e) => {
                  const indexers = ((settings?.indexers as Indexer[]) ?? []).slice()
                  const cats = e.target.value.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n))
                  indexers[i] = { ...indexers[i], categories: cats }
                  setSettings((prev) => ({ ...prev!, indexers }))
                }}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
                placeholder="2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060"
              />
            </div>
          </div>
        ))}
      </section>

      {/* Radarr */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Radarr (optional)</h2>
          <TestConnectionButton service="radarr" />
        </div>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="radarr_enabled"
            checked={!!((settings?.radarr as Record<string,unknown>)?.enabled)}
            onChange={(e) => set(['radarr', 'enabled'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="radarr_enabled" className="text-sm">Enable Radarr integration (triggers rescan after file replacement)</label>
        </div>
        {field('URL', ['radarr', 'url'])}
        {field('API Key', ['radarr', 'api_key'], 'password')}
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
        <div>
          <label className="block text-xs text-gray-400 mb-1">Preferred Codecs (comma-separated, e.g. av1, h265)</label>
          <input
            type="text"
            value={((settings?.comparison as Record<string,unknown>)?.preferred_codecs as string[] | undefined)?.join(', ') ?? ''}
            onChange={(e) => {
              const val = e.target.value.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
              set(['comparison', 'preferred_codecs'], val as unknown as string)
            }}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            placeholder="av1, h265"
          />
        </div>
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

      {/* Files */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <h2 className="font-semibold">Files</h2>
        {field('Recycling Bin Path', ['files', 'recycling_bin'])}
        {field('Recycling Bin Cleanup (days)', ['files', 'recycling_bin_cleanup_days'], 'number')}
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
