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
  last_scanned?: string
  last_searched?: string
}

export interface SearchResultItem {
  id: number
  indexer_name: string
  release_title: string
  size: number
  resolution?: string
  video_codec?: string
  age_days?: number
  score: number
  savings_bytes: number
  savings_pct: number
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
  total_savings_bytes: number
  active_downloads: number
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
  savings_bytes?: number
  savings_pct?: number
  reject_reason?: string
  notes?: string
  created_at?: string
}
