export interface Movie {
  id: number
  title: string
  year?: number
  tmdb_id?: number
  imdb_id?: string
  overview?: string
  poster_path?: string
  file_path?: string
  file_size?: number
  original_file_size?: number
  resolution?: string
  video_codec?: string
  audio_codec?: string
  status: string
  slimarr_locked?: boolean
  preferred_release_title?: string | null
  quality_intent?: 'space_saver' | 'balanced' | 'premium' | 'reference' | 'locked' | 'pinned'
  force_keep?: boolean
  allow_larger_replacements?: boolean
  quality_profile_overrides?: Record<string, unknown>
  last_scanned?: string
  last_searched?: string
}

export interface SearchResultItem {
  id: number
  indexer_name: string
  release_title: string
  size?: number | null
  resolution?: string
  video_codec?: string
  audio_codec?: string | null
  audio_channels?: string | null
  source?: string | null
  age_days?: number
  hdr?: string | null
  languages?: string[]
  media_health_score?: number | null
  media_health_rating?: string | null
  media_health_reasons?: string[]
  score?: number | null
  confidence_score?: number | null
  confidence_breakdown?: Record<string, number | null>
  savings_bytes?: number | null
  savings_pct?: number | null
  decision: 'accept' | 'reject'
  reject_reason?: string
}

export interface Download {
  id: number
  movie_id: number
  release_title: string
  status: string
  progress_pct?: number
  expected_size?: number
  nzo_id?: string
  storage_path?: string
  cleanup_status?: string
  retry_count?: number
  grabbed_at?: string
  last_error_at?: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

export interface OrphanedDownload {
  id: number
  downloader_name: string
  downloader_job_id: string
  release_name?: string
  storage_path?: string
  found_at?: string
  age_hours?: number
}

export interface QueueSummary {
  active: number
  failed: number
  orphaned: number
}

export interface BlacklistEntry {
  id: number
  release_title: string
  release_hash: string
  uploader?: string
  indexer_name?: string
  reason?: string
  manual?: boolean
  added_at?: string
  expires_at?: string
}

export interface ActivityEntry {
  id: number
  event: string
  movie_id?: number
  movie_title?: string
  old_file_path?: string
  new_file_path?: string
  old_size?: number
  new_size?: number
  savings_bytes?: number
  savings_pct?: number
  created_at: string
}

export interface DashboardStats {
  total_movies: number
  improved: number
  pending: number
  failed_items: number
  library_size_bytes: number
  total_savings_bytes: number
  active_downloads: number
  last_successful_scan?: string
}

export interface IntegrationMatrixService {
  key: string
  name: string
  required: boolean
  active: boolean
  purpose: string
  status: 'connected' | 'degraded' | 'disabled' | 'unavailable'
  detail?: Record<string, unknown>
}

export interface IntegrationMatrix {
  status: 'connected' | 'degraded' | 'unavailable'
  active_download_client: string
  checked_at: string
  services: IntegrationMatrixService[]
}

export interface HealthMatrixComponent {
  status: 'healthy' | 'degraded' | 'down' | 'disabled'
  detail: string
  [key: string]: unknown
}

export interface HealthMatrix {
  status: 'healthy' | 'degraded' | 'down'
  checked_at: string
  components: Record<string, HealthMatrixComponent>
}

export interface PreflightCheck {
  status: 'ok' | 'warn' | 'block'
  name: string
  message: string
  detail?: Record<string, unknown>
}

export interface PreflightResult {
  status: 'ok' | 'warn' | 'block'
  checked_at: string
  checks: PreflightCheck[]
}

export interface DecisionAuditEntry {
  id: number
  movie_id?: number
  movie_title?: string
  indexer_name?: string
  release_title: string
  candidate_size?: number
  local_size?: number
  decision: 'accept' | 'reject'
  score?: number
  confidence_score?: number
  confidence_breakdown?: Record<string, number>
  savings_bytes?: number
  savings_pct?: number
  reject_reason?: string
  notes?: string
  created_at?: string
}

export interface SearchDiagnosticEvent {
  type: string
  timestamp: string
  indexer_name?: string
  provider?: string
  title?: string
  query?: string
  request_url?: string
  status_code?: number | null
  latency_ms?: number
  raw_count?: number
  parsed_count?: number
  accepted_count?: number
  rejected_count?: number
  error?: string | null
  malformed?: boolean
  rate_limited?: boolean
  rejection_reasons?: Record<string, number>
  [key: string]: unknown
}

export interface SearchDiagnostics {
  checked_at: string
  degradation: {
    degraded: boolean
    blocking: boolean
    reasons: string[]
    warning_reasons?: string[]
    blocking_reasons?: string[]
    consecutive_zero_searches: number
    consecutive_failed_searches: number
    last_successful_search?: Record<string, unknown> | null
  }
  recent_events: SearchDiagnosticEvent[]
  warnings: Array<{ timestamp: string; message: string; code?: string; detail?: Record<string, unknown> }>
  failure_heatmap: Record<string, number>
  indexer_reliability: Record<string, Record<string, unknown>>
  last_successful_search?: Record<string, unknown> | null
}

export interface SearchDiagnosticsHistoryResponse {
  page: number
  per_page: number
  total: number
  pages: number
  items: SearchDiagnosticEvent[]
}

export interface SearchTestResponse {
  query: Record<string, unknown>
  providers: Array<Record<string, unknown>>
  raw_total: number
  parsed_total: number
  accepted_count: number
  rejected_count: number
  accepted_results: Array<Record<string, unknown>>
  rejected_results: Array<Record<string, unknown>>
  filtering_stages: Array<Record<string, unknown>>
}

export interface DuplicateCleanupSample {
  title: string
  best_file: string
  duplicate_count: number
  estimated_reclaimable_bytes: number
  confidence: 'high' | 'medium' | 'low' | string
}

export interface DuplicateCleanupPreview {
  status: string
  reason?: string
  movies_scanned: number
  duplicates_found: number
  estimated_reclaimable_bytes: number
  confidence: Record<string, number>
  sample: DuplicateCleanupSample[]
  truncated?: boolean
}

export interface MaintenanceInsightSignal {
  key: string
  state: string
  impact: number
  detail: string
}

export interface StoragePreflight {
  purpose: string
  path: string
  classification: string
  matched_prefix?: string | null
  exists: boolean
  parent_path?: string | null
  parent_exists: boolean
  free_bytes?: number | null
  required_bytes: number
  status: string
  messages: string[]
}

export interface StorageOperationItem {
  operation: string
  purpose: string
  source_path?: string | null
  target_path?: string | null
  source_classification: string
  target_classification?: string | null
  status: string
  bytes_estimated: number
  messages: string[]
  error?: string | null
  started_at?: string | null
  completed_at?: string | null
  duration_ms?: number | null
  job_id?: string | null
}

export interface StorageOperationsSnapshot {
  recent: StorageOperationItem[]
  recent_failures: StorageOperationItem[]
  recent_failure_window_seconds: number
  counters: Record<string, number>
  history_size: number
  nas_policy: {
    active_operations: number
    cooldown_active: boolean
    cooldown_remaining_seconds: number
    last_failure?: Record<string, unknown> | null
    write_bytes_used_24h: number
    replacements_24h: number
  }
  persisted?: {
    recent: StorageOperationItem[]
    counters: Record<string, number>
    history_size: number
    available: boolean
    error?: string
  }
}

export interface ReplacementRecoveryRecord {
  id: number
  download_id?: number | null
  movie_id?: number | null
  movie_title?: string | null
  status: string
  phase?: string | null
  original_path?: string | null
  mapped_path?: string | null
  target_path?: string | null
  video_file_path?: string | null
  storage_path?: string | null
  recycle_path?: string | null
  fallback_backup_path?: string | null
  error_message?: string | null
  details?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
  completed_at?: string | null
}

export interface ReplacementRecoverySnapshot {
  status: 'clear' | 'active' | 'recovery_required' | string
  checked_at: string
  records: ReplacementRecoveryRecord[]
}

export interface PersistentJob {
  id: string
  kind: string
  status: string
  priority: number
  payload: Record<string, unknown>
  progress_current: number
  progress_total: number
  heartbeat_at?: string | null
  attempt: number
  max_attempts: number
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  cancel_requested_at?: string | null
  events?: Array<Record<string, unknown>>
}

export interface PersistentJobsSnapshot {
  jobs: PersistentJob[]
  active_statuses: string[]
}

export interface MaintenanceInsightRecommendation {
  priority: 'high' | 'medium' | 'low' | string
  category: string
  title: string
  detail: string
}

export interface UtilitiesMaintenanceInsights {
  generated_at: string
  maintenance_score: number
  maintenance_state: 'excellent' | 'good' | 'attention' | 'critical' | string
  signals: MaintenanceInsightSignal[]
  recommendations: MaintenanceInsightRecommendation[]
  telemetry: Record<string, unknown>
}

export interface NasPressureTopMovie {
  title: string
  count: number
  written_bytes: number
}

export interface NasPressure {
  checked_at: string
  pressure_state: 'low' | 'medium' | 'high' | string
  recommended_preset: 'gentle' | 'balanced' | 'aggressive' | string
  nas_prefixes: string[]
  nas_policy_enabled: boolean
  recent: {
    replacements_24h: number
    replacement_bytes_24h: number
    nas_rejects_24h: number
    unique_movies_replaced_24h: number
  }
  top_movies: NasPressureTopMovie[]
  recommendations: string[]
}

export interface RecommendationReason {
  reason_code: string
  explanation: string
  source_movie_id?: number | null
  source_provider?: string | null
  weight?: number | null
}

export interface StreamingAvailabilityEntry {
  region: string
  provider_id: number
  provider_name: string
  display_priority?: number | null
  availability_type: 'flatrate' | 'rent' | 'buy' | 'ads' | 'free' | string
  source: string
  source_url?: string | null
  checked_at?: string | null
  stale: boolean
}

export type RecommendationState =
  | 'active'
  | 'dismissed'
  | 'hidden'
  | 'watchlisted'
  | 'actioned'
  | 'already_available'
  | 'already_managed'
  | 'expired'

export interface RecommendationItem {
  id: number
  candidate_id: number
  media_type: 'movie' | 'tv'
  title: string
  year?: number | null
  tmdb_id: number
  imdb_id?: string | null
  poster_path?: string | null
  backdrop_path?: string | null
  overview?: string | null
  popularity?: number | null
  vote_average?: number | null
  category: string
  score: number
  state: RecommendationState
  created_at?: string | null
  expires_at?: string | null
  reasons: RecommendationReason[]
  availability: StreamingAvailabilityEntry[]
  already_in_plex: boolean
}

export interface RecommendationListResponse {
  total: number
  page: number
  per_page: number
  recommendations: RecommendationItem[]
}

export interface RecommendationCapability {
  available: boolean
  reason?: string | null
}

export interface RecommendationCapabilities {
  radarr: RecommendationCapability
  sonarr: RecommendationCapability
  seerr: RecommendationCapability
}

export interface HandoffQualityProfile {
  id: number
  name: string
}

export interface HandoffRootFolder {
  path: string
}

export interface HandoffOptions {
  root_folders: HandoffRootFolder[]
  quality_profiles: HandoffQualityProfile[]
}

export interface RecommendationProviderOption {
  provider_id: number
  provider_name: string
}
