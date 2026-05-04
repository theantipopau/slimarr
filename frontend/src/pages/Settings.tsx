import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import TestConnectionButton from '@/components/TestConnectionButton'
import { CheckCircle, Plus, Trash2, XCircle } from 'lucide-react'

interface Indexer {
  name: string
  url: string
  api_key: string
  categories: number[]
}

interface DownloadClientConfig {
  download_client?: string
  sabnzbd?: { url?: string; api_key?: string; category?: string }
  nzbget?: { url?: string; username?: string; password?: string; category?: string }
}

interface RecyclingBinInfo {
  enabled: boolean
  path: string
  exists: boolean
  files: number
  bytes: number
}

interface DownloadClientCapabilities {
  active: string
  clients: Record<string, Record<string, boolean>>
}

export default function Settings() {
  const { toast } = useToast()
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null)
  const [savedSettings, setSavedSettings] = useState<Record<string, unknown> | null>(null)
  const [saving, setSaving] = useState(false)
  const [recyclingInfo, setRecyclingInfo] = useState<RecyclingBinInfo | null>(null)
  const [recyclingLoading, setRecyclingLoading] = useState(false)
  const [recyclingEmptying, setRecyclingEmptying] = useState(false)
  const [capabilities, setCapabilities] = useState<DownloadClientCapabilities | null>(null)

  const hasUnsaved = settings && savedSettings && JSON.stringify(settings) !== JSON.stringify(savedSettings)

  const isUrl = (value?: unknown) => {
    const text = String(value ?? '').trim()
    return text === '' || text.startsWith('http://') || text.startsWith('https://')
  }

  const read = (path: string[]) =>
    path.reduce((o: unknown, k) => (o as Record<string, unknown>)?.[k], settings)

  const validateSettings = () => {
    if (!settings) return { errors: [] as string[], warnings: [] as string[] }

    const errors: string[] = []
    const warnings: string[] = []
    const activeClient = String(read(['download_client']) ?? 'sabnzbd')
    const indexers = (settings.indexers as Indexer[] | undefined) ?? []

    const urlChecks: Array<[string, string[]]> = [
      ['Plex URL', ['plex', 'url']],
      ['SABnzbd URL', ['sabnzbd', 'url']],
      ['NZBGet URL', ['nzbget', 'url']],
      ['Prowlarr URL', ['prowlarr', 'url']],
      ['Radarr URL', ['radarr', 'url']],
      ['Sonarr URL', ['sonarr', 'url']],
    ]
    urlChecks.forEach(([label, path]) => {
      if (!isUrl(read(path))) errors.push(`${label} must include http:// or https://`)
    })
    indexers.forEach((idx, i) => {
      if (idx.url && !isUrl(idx.url)) errors.push(`Indexer ${i + 1} URL must include http:// or https://`)
      if ((idx.url || idx.name || idx.api_key) && (!idx.name || !idx.url)) {
        errors.push(`Indexer ${i + 1} needs both a name and URL`)
      }
      if (idx.url && idx.categories.length === 0) warnings.push(`Indexer ${i + 1} has no categories configured`)
    })

    const numericChecks: Array<[string, string[], number, number]> = [
      ['Min savings %', ['comparison', 'min_savings_percent'], 0, 100],
      ['Downgrade min savings %', ['comparison', 'downgrade_min_savings_percent'], 0, 100],
      ['Minimum file size MB', ['comparison', 'minimum_file_size_mb'], 1, 1000000],
      ['Max candidate age days', ['comparison', 'max_candidate_age_days'], 1, 36500],
      ['Recycling cleanup days', ['files', 'recycling_bin_cleanup_days'], 1, 3650],
      ['Max downloads per night', ['schedule', 'max_downloads_per_night'], 1, 1000],
      ['Throttle seconds', ['schedule', 'throttle_seconds'], 0, 86400],
      ['Max active download hours', ['schedule', 'max_active_download_hours'], 1, 168],
    ]
    numericChecks.forEach(([label, path, min, max]) => {
      const raw = Number(read(path))
      if (!Number.isFinite(raw) || raw < min || raw > max) {
        errors.push(`${label} must be between ${min} and ${max}`)
      }
    })

    if (activeClient === 'sabnzbd' && (!read(['sabnzbd', 'url']) || !read(['sabnzbd', 'api_key']))) {
      warnings.push('SABnzbd is selected but URL/API key is incomplete')
    }
    if (activeClient === 'nzbget' && !read(['nzbget', 'url'])) {
      warnings.push('NZBGet is selected but URL is incomplete')
    }
    if (!read(['prowlarr', 'url']) && indexers.length === 0) {
      warnings.push('No Prowlarr URL or direct indexers configured; searches will not return results')
    }

    return { errors, warnings }
  }

  const formatBytes = (bytes: number) => {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
    const value = bytes / (1024 ** idx)
    return `${value >= 10 || idx === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[idx]}`
  }

  const loadRecyclingInfo = async (showLoading = false) => {
    if (showLoading) setRecyclingLoading(true)
    try {
      const info = await api.recyclingBinInfo()
      setRecyclingInfo(info)
    } catch {
      if (showLoading) toast('Failed to load recycling bin status', 'error')
    } finally {
      if (showLoading) setRecyclingLoading(false)
    }
  }

  const emptyRecyclingBin = async () => {
    if (!recyclingInfo?.enabled || !recyclingInfo?.path) {
      toast('Set a recycling bin path first', 'error')
      return
    }
    const confirmed = window.confirm('Empty recycling bin now? This permanently deletes all files currently in the bin.')
    if (!confirmed) return

    setRecyclingEmptying(true)
    try {
      const result = await api.emptyRecyclingBin()
      const freed = Number((result as Record<string, unknown>)?.freed_bytes ?? 0)
      toast(`Recycling bin emptied (${formatBytes(freed)} freed)`, 'success')
      await loadRecyclingInfo(true)
    } catch {
      toast('Failed to empty recycling bin', 'error')
    } finally {
      setRecyclingEmptying(false)
    }
  }

  useEffect(() => {
    api.getSettings().then((s) => { setSettings(s); setSavedSettings(s) }).catch(() => {})
    api.downloadClientCapabilities().then((data) => setCapabilities(data as DownloadClientCapabilities)).catch(() => {})
    void loadRecyclingInfo(true)
  }, [])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadRecyclingInfo()
    }, 15000)
    return () => window.clearInterval(intervalId)
  }, [])

  const save = async () => {
    if (!settings) return
    const validation = validateSettings()
    if (validation.errors.length > 0) {
      toast('Fix settings validation errors before saving', 'error')
      return
    }
    setSaving(true)
    try {
      await api.updateSettings(settings)
      setSavedSettings(JSON.parse(JSON.stringify(settings)))
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

  const downloadClient = ((settings as DownloadClientConfig).download_client ?? 'sabnzbd')
  const validation = validateSettings()
  const capabilityLabels: Record<string, string> = {
    submit_url: 'Submit URL',
    queue_status: 'Queue status',
    history_status: 'History status',
    purge: 'Purge jobs',
    categories: 'Categories',
    pause_resume: 'Pause/resume',
    storage_path_lookup: 'Storage paths',
  }

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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <h1 className="text-2xl font-bold flex-1">Settings</h1>
        {hasUnsaved && (
          <span className="text-xs text-yellow-400 font-medium">Unsaved changes — save before testing connections</span>
        )}
        <button
          onClick={save}
          disabled={saving}
          className={`px-4 py-2 rounded-lg text-white text-sm disabled:opacity-50 ${validation.errors.length ? 'bg-red-700' : hasUnsaved ? 'bg-yellow-500 hover:bg-yellow-600' : 'bg-brand-green'}`}
        >
          {saving ? 'Saving…' : hasUnsaved ? 'Save Changes' : 'Save'}
        </button>
      </div>

      {(validation.errors.length > 0 || validation.warnings.length > 0) && (
        <section className="bg-gray-900 rounded-xl p-4 border border-gray-800 space-y-3">
          <h2 className="text-sm font-semibold">Settings Review</h2>
          {validation.errors.length > 0 && (
            <div className="space-y-1">
              {validation.errors.map((item) => (
                <p key={item} className="text-xs text-red-300 flex gap-2">
                  <XCircle size={13} className="shrink-0 mt-0.5" />
                  <span>{item}</span>
                </p>
              ))}
            </div>
          )}
          {validation.warnings.length > 0 && (
            <div className="space-y-1">
              {validation.warnings.map((item) => (
                <p key={item} className="text-xs text-yellow-300 flex gap-2">
                  <XCircle size={13} className="shrink-0 mt-0.5" />
                  <span>{item}</span>
                </p>
              ))}
            </div>
          )}
        </section>
      )}

      <nav className="flex gap-2 overflow-x-auto pb-1 text-xs">
        {[
          ['#connections', 'Connections'],
          ['#indexers', 'Indexers'],
          ['#integrations', 'Integrations'],
          ['#rules', 'Rules'],
          ['#files', 'Files'],
          ['#schedule', 'Schedule'],
        ].map(([href, label]) => (
          <a key={href} href={href} className="shrink-0 rounded-full bg-gray-900 px-3 py-1.5 text-gray-300 hover:bg-gray-800">
            {label}
          </a>
        ))}
      </nav>

      {/* Plex */}
      <section id="connections" className="bg-gray-900 rounded-xl p-5 space-y-3 scroll-mt-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Plex</h2>
          <TestConnectionButton
            service="plex"
            body={{ url: (settings?.plex as Record<string,unknown>)?.url, token: (settings?.plex as Record<string,unknown>)?.token }}
          />
        </div>
        {field('URL', ['plex', 'url'])}
        {field('Token', ['plex', 'token'], 'password')}
      </section>

      {/* TMDB */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">TMDB</h2>
          <TestConnectionButton service="tmdb" body={{ api_key: (settings?.tmdb as Record<string,unknown>)?.api_key }} />
        </div>
        {field('API Key', ['tmdb', 'api_key'], 'password')}
      </section>

      {/* SABnzbd */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">SABnzbd</h2>
          <TestConnectionButton
            service="sabnzbd"
            body={{
              url: (settings?.sabnzbd as Record<string,unknown>)?.url,
              api_key: (settings?.sabnzbd as Record<string,unknown>)?.api_key,
              category: (settings?.sabnzbd as Record<string,unknown>)?.category,
            }}
          />
        </div>
        <p className="text-xs text-gray-400">Default downloader. Best-supported path and current fallback default.</p>
        {field('URL', ['sabnzbd', 'url'])}
        {field('API Key', ['sabnzbd', 'api_key'], 'password')}
        {field('Category', ['sabnzbd', 'category'])}
      </section>

      {/* Download client */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <h2 className="font-semibold">Download Client</h2>
        <p className="text-xs text-gray-400">Choose which Usenet downloader Slimarr sends accepted releases to. SABnzbd remains the default.</p>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Active Download Client</label>
          <select
            value={downloadClient}
            onChange={(e) => set(['download_client'], e.target.value)}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
          >
            <option value="sabnzbd">SABnzbd</option>
            <option value="nzbget">NZBGet</option>
          </select>
        </div>
        {capabilities?.clients?.[downloadClient] && (
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-gray-800/70 p-3 sm:grid-cols-3">
            {Object.entries(capabilityLabels).map(([key, label]) => {
              const supported = !!capabilities.clients[downloadClient]?.[key]
              return (
                <div key={key} className="flex items-center gap-2 text-xs text-gray-300">
                  {supported ? (
                    <CheckCircle size={13} className="text-green-400 shrink-0" />
                  ) : (
                    <XCircle size={13} className="text-gray-500 shrink-0" />
                  )}
                  <span>{label}</span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* NZBGet */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">NZBGet</h2>
          <TestConnectionButton
            service="nzbget"
            body={{
              url: (settings?.nzbget as Record<string,unknown>)?.url,
              username: (settings?.nzbget as Record<string,unknown>)?.username,
              password: (settings?.nzbget as Record<string,unknown>)?.password,
              category: (settings?.nzbget as Record<string,unknown>)?.category,
            }}
          />
        </div>
        <p className="text-xs text-gray-400">Optional second Usenet downloader. Configure it fully before selecting it as the active client.</p>
        {field('URL', ['nzbget', 'url'])}
        {field('Username', ['nzbget', 'username'])}
        {field('Password', ['nzbget', 'password'], 'password')}
        {field('Category', ['nzbget', 'category'])}
      </section>

      {/* Prowlarr */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Prowlarr (optional)</h2>
          <TestConnectionButton
            service="prowlarr"
            body={{ url: (settings?.prowlarr as Record<string,unknown>)?.url, api_key: (settings?.prowlarr as Record<string,unknown>)?.api_key }}
          />
        </div>
        <p className="text-xs text-gray-400">If disabled, Slimarr will use the Newznab indexers configured below instead.</p>
        {field('URL', ['prowlarr', 'url'])}
        {field('API Key', ['prowlarr', 'api_key'], 'password')}
      </section>

      {/* Newznab Indexers */}
      <section id="indexers" className="bg-gray-900 rounded-xl p-5 space-y-4 scroll-mt-4">
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
      <section id="integrations" className="bg-gray-900 rounded-xl p-5 space-y-3 scroll-mt-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Radarr (optional)</h2>
          <TestConnectionButton
            service="radarr"
            body={{ url: (settings?.radarr as Record<string,unknown>)?.url, api_key: (settings?.radarr as Record<string,unknown>)?.api_key }}
          />
        </div>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="radarr_enabled"
            checked={!!((settings?.radarr as Record<string,unknown>)?.enabled)}
            onChange={(e) => set(['radarr', 'enabled'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="radarr_enabled" className="text-sm">Enable Radarr integration</label>
        </div>
        {field('URL', ['radarr', 'url'])}
        {field('API Key', ['radarr', 'api_key'], 'password')}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="radarr_tls_verify"
            checked={(settings?.radarr as Record<string,unknown>)?.tls_verify !== false}
            onChange={(e) => set(['radarr', 'tls_verify'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="radarr_tls_verify" className="text-sm">Verify TLS certificate <span className="text-gray-500 text-xs">(uncheck for self-signed certs)</span></label>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-gray-400">Action after file replacement</label>
          <select
            value={String((settings?.radarr as Record<string,unknown>)?.post_replace_action ?? 'rescan')}
            onChange={(e) => set(['radarr', 'post_replace_action'], e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-green"
          >
            <option value="rescan">Rescan only (Radarr picks up new file)</option>
            <option value="rescan_unmonitor">Rescan + Unmonitor (prevents Radarr re-upgrading)</option>
            <option value="none">None (no Radarr notification)</option>
          </select>
          <p className="text-xs text-gray-500">
            "Rescan + Unmonitor" stops Radarr from downloading a larger version after Slimarr replaces the file.
          </p>
        </div>
      </section>

      {/* Sonarr */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Sonarr (optional)</h2>
          <TestConnectionButton
            service="sonarr"
            body={{ url: (settings?.sonarr as Record<string,unknown>)?.url, api_key: (settings?.sonarr as Record<string,unknown>)?.api_key }}
          />
        </div>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="sonarr_enabled"
            checked={!!((settings?.sonarr as Record<string,unknown>)?.enabled)}
            onChange={(e) => set(['sonarr', 'enabled'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="sonarr_enabled" className="text-sm">Enable Sonarr integration (unmonitors series when TV shows are deleted via TV Shows page)</label>
        </div>
        {field('URL', ['sonarr', 'url'])}
        {field('API Key', ['sonarr', 'api_key'], 'password')}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="sonarr_tls_verify"
            checked={(settings?.sonarr as Record<string,unknown>)?.tls_verify !== false}
            onChange={(e) => set(['sonarr', 'tls_verify'], e.target.checked)}
            className="w-4 h-4 accent-brand-green"
          />
          <label htmlFor="sonarr_tls_verify" className="text-sm">Verify TLS certificate <span className="text-gray-500 text-xs">(uncheck for self-signed certs)</span></label>
        </div>
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
      <section id="rules" className="bg-gray-900 rounded-xl p-5 space-y-3 scroll-mt-4">
        <h2 className="font-semibold">Comparison Rules</h2>
        {field('Min Savings %', ['comparison', 'min_savings_percent'], 'number')}
        {field('Downgrade Min Savings %', ['comparison', 'downgrade_min_savings_percent'], 'number')}
        {field('Minimum File Size (MB)', ['comparison', 'minimum_file_size_mb'], 'number')}
        {field('Max Candidate Age (days)', ['comparison', 'max_candidate_age_days'], 'number')}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Preferred Language</label>
          <select
            value={((settings?.comparison as Record<string,unknown>)?.preferred_language as string) ?? 'english'}
            onChange={(e) => set(['comparison', 'preferred_language'], e.target.value)}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
          >
            <option value="english">English</option>
            <option value="french">French</option>
            <option value="german">German</option>
            <option value="spanish">Spanish</option>
            <option value="italian">Italian</option>
            <option value="russian">Russian</option>
            <option value="">Any (no language filter)</option>
          </select>
          <p className="text-xs text-gray-500 mt-1">Candidates explicitly tagged with a different language will be rejected. Releases with no language tag are always allowed through.</p>
        </div>
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
      <section id="files" className="bg-gray-900 rounded-xl p-5 space-y-3 scroll-mt-4">
        <h2 className="font-semibold">Files</h2>
        {field('Recycling Bin Path', ['files', 'recycling_bin'])}
        {field('Recycling Bin Cleanup (days)', ['files', 'recycling_bin_cleanup_days'], 'number')}
        <div className="mt-2 bg-gray-800/70 rounded-lg p-3 space-y-3 border border-gray-700">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-gray-200">Recycling Bin Status</p>
              <p className="text-xs text-gray-400">Live usage, auto-refreshes every 15 seconds</p>
            </div>
            <button
              onClick={() => { void loadRecyclingInfo(true) }}
              disabled={recyclingLoading || recyclingEmptying}
              className="px-3 py-1.5 rounded-md text-xs bg-gray-700 hover:bg-gray-600 disabled:opacity-50"
            >
              {recyclingLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-gray-900 rounded-md p-2">
              <p className="text-xs text-gray-400">Files</p>
              <p className="font-semibold text-gray-100">{recyclingInfo?.files ?? 0}</p>
            </div>
            <div className="bg-gray-900 rounded-md p-2">
              <p className="text-xs text-gray-400">Size</p>
              <p className="font-semibold text-gray-100">{formatBytes(recyclingInfo?.bytes ?? 0)}</p>
            </div>
          </div>

          <p className="text-xs text-gray-500 break-all">
            {recyclingInfo?.path ? `Path: ${recyclingInfo.path}` : 'Path not configured. Set "Recycling Bin Path" and save settings.'}
          </p>

          <button
            onClick={() => { void emptyRecyclingBin() }}
            disabled={
              recyclingEmptying
              || !recyclingInfo?.enabled
              || !recyclingInfo?.exists
              || (recyclingInfo?.files ?? 0) === 0
            }
            className="px-3 py-2 rounded-lg text-sm bg-red-600 hover:bg-red-700 text-white disabled:opacity-40"
          >
            {recyclingEmptying ? 'Emptying…' : 'Empty Recycling Bin'}
          </button>
        </div>
      </section>

      {/* Path Mappings */}
      <section className="bg-gray-900 rounded-xl p-5 space-y-3">
        <div>
          <h2 className="font-semibold">Path Mappings</h2>
          <p className="text-xs text-gray-400 mt-1">
            If Plex reports file paths that Slimarr can't access directly (e.g. different machine or mount point),
            map the Plex-reported prefix to the locally accessible equivalent.
            Example: Plex path <code className="text-gray-300">/data/media</code> → Local path <code className="text-gray-300">E:/media</code>
          </p>
        </div>
        {((settings?.files as Record<string,unknown>)?.plex_path_mappings as Array<{plex_path:string,local_path:string}> | undefined ?? []).map((mapping, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input
              type="text"
              placeholder="Plex path (e.g. /data/media)"
              value={mapping.plex_path}
              onChange={(e) => {
                const maps = [...((settings?.files as Record<string,unknown>)?.plex_path_mappings as Array<{plex_path:string,local_path:string}> ?? [])]
                maps[i] = { ...maps[i], plex_path: e.target.value }
                set(['files', 'plex_path_mappings'], maps as unknown as string)
              }}
              className="flex-1 bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            />
            <span className="text-gray-500 text-sm">→</span>
            <input
              type="text"
              placeholder="Local path (e.g. E:/media)"
              value={mapping.local_path}
              onChange={(e) => {
                const maps = [...((settings?.files as Record<string,unknown>)?.plex_path_mappings as Array<{plex_path:string,local_path:string}> ?? [])]
                maps[i] = { ...maps[i], local_path: e.target.value }
                set(['files', 'plex_path_mappings'], maps as unknown as string)
              }}
              className="flex-1 bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            />
            <button
              onClick={() => {
                const maps = ((settings?.files as Record<string,unknown>)?.plex_path_mappings as Array<{plex_path:string,local_path:string}> ?? []).filter((_, j) => j !== i)
                set(['files', 'plex_path_mappings'], maps as unknown as string)
              }}
              className="text-red-400 hover:text-red-300 px-2 text-lg leading-none"
              title="Remove mapping"
            >×</button>
          </div>
        ))}
        <button
          onClick={() => {
            const maps = [...((settings?.files as Record<string,unknown>)?.plex_path_mappings as Array<{plex_path:string,local_path:string}> ?? []), { plex_path: '', local_path: '' }]
            set(['files', 'plex_path_mappings'], maps as unknown as string)
          }}
          className="text-sm text-brand-green hover:text-green-300"
        >+ Add Mapping</button>
      </section>

      {/* Schedule */}
      <section id="schedule" className="bg-gray-900 rounded-xl p-5 space-y-3 scroll-mt-4">
        <h2 className="font-semibold">Schedule</h2>
        {field('Nightly Start Time (UTC, HH:MM)', ['schedule', 'start_time'])}
        {field('Nightly End Time (UTC, HH:MM)', ['schedule', 'end_time'])}
        {field('Max Downloads per Night', ['schedule', 'max_downloads_per_night'], 'number')}
        {field('Throttle between downloads (seconds)', ['schedule', 'throttle_seconds'], 'number')}
        {field('Max Active Download Hours', ['schedule', 'max_active_download_hours'], 'number')}
      </section>
    </div>
  )
}
