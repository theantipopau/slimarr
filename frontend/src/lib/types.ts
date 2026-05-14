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
  warnings: Array<{ timestamp: string; message: string; detail?: Record<string, unknown> }>
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
