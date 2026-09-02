import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import EmptyState from '@/components/EmptyState'
import ConfirmDialog from '@/components/ConfirmDialog'
import { Skeleton } from '@/components/Skeleton'
import type { HandoffOptions, RecommendationCapabilities, RecommendationItem } from '@/lib/types'
import {
  Compass, RefreshCw, X, EyeOff, Bookmark, CheckCircle2, Sparkles,
  Send, Star, Calendar, Info,
} from 'lucide-react'

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w342'

const STATE_LABELS: Record<string, string> = {
  active: 'Suggested',
  dismissed: 'Dismissed',
  hidden: 'Hidden',
  watchlisted: 'Watchlisted',
  actioned: 'Sent',
  already_available: 'Already in Plex',
  already_managed: 'Already Managed',
  expired: 'Expired',
}

const CATEGORY_LABELS: Record<string, string> = {
  collection_completion: 'Collection Gap',
  related_title: 'Related Title',
}

function posterUrl(path?: string | null): string | null {
  return path ? `${TMDB_IMAGE_BASE}${path}` : null
}

function ReasonChip({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-200">
      <Sparkles size={10} />
      {text}
    </span>
  )
}

function RecommendationCard({
  item,
  capabilities,
  onAction,
  onHandoff,
}: {
  item: RecommendationItem
  capabilities: RecommendationCapabilities | null
  onAction: (id: number, action: 'dismiss' | 'hide' | 'watchlist' | 'mark-owned' | 'refresh-availability') => void
  onHandoff: (item: RecommendationItem, service: 'radarr' | 'sonarr') => void
}) {
  const poster = posterUrl(item.poster_path)
  const canSendToRadarr = item.media_type === 'movie' && capabilities?.radarr.available
  const canSendToSonarr = item.media_type === 'tv' && capabilities?.sonarr.available

  return (
    <div className="group relative flex flex-col overflow-hidden rounded-xl border border-white/10 bg-gray-900/70 shadow-[0_16px_32px_-24px_rgba(0,0,0,0.8)] transition-transform hover:-translate-y-0.5">
      <div className="relative aspect-[2/3] w-full bg-gray-800">
        {poster ? (
          <img src={poster} alt={item.title} loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center p-2 text-center text-xs text-gray-500">
            {item.title}
          </div>
        )}
        <div className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
          <Star size={10} className="fill-amber-300" />
          {item.score.toFixed(0)}
        </div>
        {item.already_in_plex ? (
          <div className="absolute right-1.5 top-1.5 rounded-full bg-emerald-600/90 px-2 py-0.5 text-[10px] font-semibold text-white">
            In Plex
          </div>
        ) : item.state !== 'active' ? (
          <div className="absolute right-1.5 top-1.5 rounded-full bg-gray-900/90 px-2 py-0.5 text-[10px] font-semibold text-gray-200">
            {STATE_LABELS[item.state] ?? item.state}
          </div>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div>
          <p className="truncate text-sm font-semibold text-gray-100" title={item.title}>{item.title}</p>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-gray-500">
            {item.year && (
              <span className="flex items-center gap-1"><Calendar size={10} />{item.year}</span>
            )}
            <span className="rounded bg-white/5 px-1.5 py-0.5 uppercase tracking-wide">
              {CATEGORY_LABELS[item.category] ?? item.category}
            </span>
          </div>
        </div>

        {item.reasons.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.reasons.slice(0, 2).map((reason) => (
              <ReasonChip key={reason.reason_code} text={reason.explanation} />
            ))}
          </div>
        )}

        {item.availability.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.availability.slice(0, 3).map((entry) => (
              <span
                key={`${entry.provider_id}-${entry.availability_type}`}
                className={`rounded bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-200 ${entry.stale ? 'opacity-50' : ''}`}
                title={entry.stale ? 'Availability may be stale — refresh to confirm' : undefined}
              >
                {entry.provider_name}
              </span>
            ))}
          </div>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
          <button
            onClick={() => onAction(item.id, 'dismiss')}
            className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5"
            title="Dismiss"
          >
            <X size={12} /> Dismiss
          </button>
          <button
            onClick={() => onAction(item.id, 'hide')}
            className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5"
            title="Hide permanently"
          >
            <EyeOff size={12} /> Hide
          </button>
          <button
            onClick={() => onAction(item.id, 'watchlist')}
            className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5"
            title="Add to watchlist"
          >
            <Bookmark size={12} /> Watchlist
          </button>
          <button
            onClick={() => onAction(item.id, 'mark-owned')}
            className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5"
            title="Mark as already owned"
          >
            <CheckCircle2 size={12} /> Owned
          </button>
          {(canSendToRadarr || canSendToSonarr) && (
            <button
              onClick={() => onHandoff(item, canSendToRadarr ? 'radarr' : 'sonarr')}
              className="flex items-center gap-1 rounded-md border border-emerald-400/20 bg-emerald-400/5 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-400/15"
              title="Choose a root folder and quality profile, then send"
            >
              <Send size={12} /> Send to {canSendToRadarr ? 'Radarr' : 'Sonarr'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function HandoffModal({
  item,
  service,
  onCancel,
  onSent,
}: {
  item: RecommendationItem
  service: 'radarr' | 'sonarr'
  onCancel: () => void
  onSent: (id: number) => void
}) {
  const { toast } = useToast()
  const [options, setOptions] = useState<HandoffOptions | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rootFolderPath, setRootFolderPath] = useState('')
  const [qualityProfileId, setQualityProfileId] = useState<number | ''>('')
  const [monitored, setMonitored] = useState(true)
  const [searchNow, setSearchNow] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    const fetchOptions = service === 'radarr' ? api.radarrHandoffOptions : api.sonarrHandoffOptions
    fetchOptions()
      .then((data: HandoffOptions) => {
        setOptions(data)
        if (data.root_folders.length > 0) setRootFolderPath(data.root_folders[0].path)
        if (data.quality_profiles.length > 0) setQualityProfileId(data.quality_profiles[0].id)
      })
      .catch(() => setLoadError(`Could not load ${service === 'radarr' ? 'Radarr' : 'Sonarr'} root folders and quality profiles.`))
  }, [service])

  const serviceLabel = service === 'radarr' ? 'Radarr' : 'Sonarr'
  const ready = !!options && !!rootFolderPath && qualityProfileId !== ''
  const noOptionsConfigured = !!options && (options.root_folders.length === 0 || options.quality_profiles.length === 0)

  const send = async () => {
    // `ready` already requires qualityProfileId !== '', so this is the only
    // guard needed - TS narrows qualityProfileId to `number` from here on.
    if (!ready) return
    setSending(true)
    try {
      const body = { root_folder_path: rootFolderPath, quality_profile_id: qualityProfileId, monitored, search_now: searchNow }
      if (service === 'radarr') await api.sendRecommendationToRadarr(item.id, body)
      else await api.sendRecommendationToSonarr(item.id, body)
      toast(`Sent "${item.title}" to ${serviceLabel}`, 'success')
      onSent(item.id)
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      toast(message || `Failed to send to ${serviceLabel}`, 'error')
    } finally {
      setSending(false)
    }
  }

  return (
    <ConfirmDialog
      open
      title={`Send "${item.title}" to ${serviceLabel}`}
      message={`${serviceLabel} remains the system of record after this — Slimarr never manages it further.`}
      confirmLabel={sending ? 'Sending…' : 'Send'}
      loading={sending || !ready}
      onConfirm={send}
      onCancel={onCancel}
    >
      {loadError ? (
        <p className="text-rose-300">{loadError}</p>
      ) : !options ? (
        <p className="text-gray-400">Loading root folders and quality profiles…</p>
      ) : noOptionsConfigured ? (
        <p className="text-amber-300">
          No root folders or quality profiles found in {serviceLabel}. Configure at least one of each in {serviceLabel} first.
        </p>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Root Folder</label>
            <select
              value={rootFolderPath}
              onChange={(e) => setRootFolderPath(e.target.value)}
              className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            >
              {options.root_folders.map((f) => (
                <option key={f.path} value={f.path}>{f.path}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Quality Profile</label>
            <select
              value={qualityProfileId}
              onChange={(e) => setQualityProfileId(Number(e.target.value))}
              className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
            >
              {options.quality_profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="handoff_monitored"
              checked={monitored}
              onChange={(e) => setMonitored(e.target.checked)}
              className="w-4 h-4 accent-brand-green"
            />
            <label htmlFor="handoff_monitored" className="text-sm text-gray-200">Monitored</label>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="handoff_search_now"
              checked={searchNow}
              onChange={(e) => setSearchNow(e.target.checked)}
              className="w-4 h-4 accent-brand-green"
            />
            <label htmlFor="handoff_search_now" className="text-sm text-gray-200">Search immediately</label>
          </div>
        </div>
      )}
    </ConfirmDialog>
  )
}

export default function Discovery() {
  const { toast } = useToast()
  const [items, setItems] = useState<RecommendationItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [capabilities, setCapabilities] = useState<RecommendationCapabilities | null>(null)
  const [mediaType, setMediaType] = useState('')
  const [category, setCategory] = useState('')
  const [state, setState] = useState('active')
  const [sort, setSort] = useState('relevance')
  const [disabled, setDisabled] = useState(false)
  const [handoff, setHandoff] = useState<{ item: RecommendationItem; service: 'radarr' | 'sonarr' } | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    api.recommendations({ media_type: mediaType || undefined, category: category || undefined, state, sort, per_page: 60 })
      .then((data) => {
        setItems(data.recommendations)
        setTotal(data.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [mediaType, category, state, sort])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    api.recommendationCapabilities().then(setCapabilities).catch(() => {})
    // The list endpoint returns an empty result set whether the feature is
    // disabled or just has nothing to show yet — check the actual config so
    // the empty state can tell those two apart instead of always saying
    // "no recommendations yet" for a feature the user hasn't turned on.
    api.getSettings()
      .then((settings) => setDisabled(!(settings?.recommendations as { enabled?: boolean } | undefined)?.enabled))
      .catch(() => {})
  }, [])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const result = await api.refreshRecommendations()
      if (result.already_running) {
        toast('A refresh is already running', 'info')
      } else {
        toast('Recommendation refresh started', 'success')
      }
      setTimeout(load, 3000)
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      toast(message || 'Failed to start refresh', 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const handleAction = async (id: number, action: 'dismiss' | 'hide' | 'watchlist' | 'mark-owned' | 'refresh-availability') => {
    const actionMap = {
      dismiss: api.dismissRecommendation,
      hide: api.hideRecommendation,
      watchlist: api.watchlistRecommendation,
      'mark-owned': api.markOwnedRecommendation,
      'refresh-availability': api.refreshRecommendationAvailability,
    } as const
    try {
      await actionMap[action](id)
      if (action === 'refresh-availability') {
        // Unlike the other actions, this never moves the recommendation out
        // of the "active" state - reload to pick up the refreshed
        // availability data instead of removing the card from view.
        load()
        return
      }
      setItems((prev) => prev.filter((item) => item.id !== id))
      setTotal((prev) => Math.max(0, prev - 1))
    } catch {
      toast('Action failed', 'error')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Compass size={20} className="text-emerald-300" />
          <h1 className="text-2xl font-bold">Discovery</h1>
        </div>
        <p className="text-sm text-gray-400">
          Missing sequels, collection gaps, and related titles — nothing here downloads automatically.
        </p>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="ml-auto flex items-center gap-2 rounded-lg bg-brand-green px-3 py-2 text-sm text-white shadow-[0_12px_24px_-14px_rgba(31,191,143,0.85)] disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          {refreshing ? 'Starting…' : 'Refresh'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)} className="rounded-lg bg-gray-800 px-3 py-2 text-sm outline-none">
          <option value="">All Media</option>
          <option value="movie">Movies</option>
          <option value="tv">TV</option>
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg bg-gray-800 px-3 py-2 text-sm outline-none">
          <option value="">All Reasons</option>
          <option value="collection_completion">Collection Gap</option>
          <option value="related_title">Related Title</option>
        </select>
        <select value={state} onChange={(e) => setState(e.target.value)} className="rounded-lg bg-gray-800 px-3 py-2 text-sm outline-none">
          <option value="active">Suggested</option>
          <option value="watchlisted">Watchlisted</option>
          <option value="dismissed">Dismissed</option>
          <option value="hidden">Hidden</option>
          <option value="already_managed">Already Managed</option>
          <option value="">All States</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg bg-gray-800 px-3 py-2 text-sm outline-none">
          <option value="relevance">Sort: Relevance</option>
          <option value="date_added">Sort: Date Added</option>
          <option value="popularity">Sort: Popularity</option>
          <option value="release_date">Sort: Release Date</option>
        </select>
      </div>

      {disabled ? (
        <EmptyState
          icon={Info}
          title="Recommendations are disabled"
          description="Enable recommendations.enabled in Settings to start discovering missing titles from your library."
        />
      ) : loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="aspect-[2/3] overflow-hidden rounded-xl">
              <Skeleton className="h-full w-full" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Compass}
          title="No recommendations yet"
          description="Run a refresh to scan your library for missing collection members and related titles."
        />
      ) : (
        <>
          <p className="text-xs text-gray-500">{total} recommendation{total === 1 ? '' : 's'}</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {items.map((item) => (
              <RecommendationCard
                key={item.id}
                item={item}
                capabilities={capabilities}
                onAction={handleAction}
                onHandoff={(target, service) => setHandoff({ item: target, service })}
              />
            ))}
          </div>
        </>
      )}

      {handoff && (
        <HandoffModal
          item={handoff.item}
          service={handoff.service}
          onCancel={() => setHandoff(null)}
          onSent={(id) => {
            setHandoff(null)
            setItems((prev) => prev.filter((item) => item.id !== id))
            setTotal((prev) => Math.max(0, prev - 1))
          }}
        />
      )}
    </div>
  )
}
