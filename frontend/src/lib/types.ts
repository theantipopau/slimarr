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
  started_at?: string
  completed_at?: string
  error_message?: string
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
