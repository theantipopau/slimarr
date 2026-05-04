// API client
import axios from 'axios'

const BASE = '/api/v1'

const client = axios.create({ baseURL: BASE })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const api = {
  // Auth
  authCheck: () => client.get('/auth/check').then((r) => r.data),
  login: (username: string, password: string) =>
    client.post('/auth/login', { username, password }).then((r) => r.data),
  register: (username: string, password: string) =>
    client.post('/auth/register', { username, password }).then((r) => r.data),

  // Dashboard
  stats: () => client.get('/dashboard/stats').then((r) => r.data),
  savingsHistory: (days = 30) =>
    client.get(`/dashboard/savings-history?days=${days}`).then((r) => r.data),
  recentActivity: (limit = 20) =>
    client.get(`/dashboard/recent-activity?limit=${limit}`).then((r) => r.data),

  // Library
  movies: (params?: Record<string, unknown>) =>
    client.get('/library/movies', { params }).then((r) => r.data),
  movie: (id: number) => client.get(`/library/movies/${id}`).then((r) => r.data),
  searchResults: (id: number) =>
    client.get(`/library/movies/${id}/search-results`).then((r) => r.data),
  triggerSearch: (id: number) =>
    client.post(`/library/movies/${id}/search`).then((r) => r.data),
  triggerProcess: (id: number) =>
    client.post(`/library/movies/${id}/process`).then((r) => r.data),
  downloadResult: (movieId: number, resultId: number) =>
    client.post(`/library/movies/${movieId}/search-results/${resultId}/download`).then((r) => r.data),
  lockMovie: (id: number) =>
    client.post(`/library/movies/${id}/lock`).then((r) => r.data),
  unlockMovie: (id: number) =>
    client.post(`/library/movies/${id}/unlock`).then((r) => r.data),

  // Activity
  activity: (params?: Record<string, unknown>) =>
    client.get('/activity', { params }).then((r) => r.data),

  // Queue
  activeDownloads: () => client.get('/queue/active').then((r) => r.data),
  recentDownloads: (limit = 20) =>
    client.get(`/queue/recent?limit=${limit}`).then((r) => r.data),
  failedDownloads: (limit = 50) =>
    client.get(`/queue/failed?limit=${limit}`).then((r) => r.data),
  cleanupFailedDownload: (downloadId: number) =>
    client.post(`/queue/${downloadId}/cleanup`).then((r) => r.data),
  retryFailedDownload: (downloadId: number) =>
    client.post(`/queue/${downloadId}/retry`).then((r) => r.data),
  resumeDownloads: () => client.post('/queue/resume').then((r) => r.data),
  orphanedDownloads: (limit = 100) =>
    client.get(`/queue/orphaned?limit=${limit}`).then((r) => r.data),
  cleanupOrphanedDownload: (orphanId: number) =>
    client.post(`/queue/orphaned/${orphanId}/cleanup`).then((r) => r.data),

  // Settings
  getSettings: () => client.get('/settings').then((r) => r.data),
  downloadClientCapabilities: () => client.get('/settings/download-clients/capabilities').then((r) => r.data),
  updateSettings: (data: unknown) =>
    client.put('/settings', data).then((r) => r.data),
  testConnection: (service: string, body?: unknown) =>
    client.post(`/settings/test/${service}`, body ?? null).then((r) => r.data),
  getBlacklist: () => client.get('/settings/blacklist').then((r) => r.data),
  addBlacklistEntry: (data: {
    release_title: string
    uploader?: string
    indexer_name?: string
    reason?: string
    expires_in_days?: number
  }) => client.post('/settings/blacklist', data).then((r) => r.data),
  removeBlacklistEntry: (releaseHash: string) =>
    client.delete(`/settings/blacklist/${releaseHash}`).then((r) => r.data),

  // System
  systemStatus: () => client.get('/system/status').then((r) => r.data),
  systemInfo: () => client.get('/system/info').then((r) => r.data),
  servicesHealth: () => client.get('/system/health/services').then((r) => r.data),
  integrationMatrix: () => client.get('/system/integrations/matrix').then((r) => r.data),
  healthMatrix: () => client.get('/system/health/matrix').then((r) => r.data),
  preflight: () => client.get('/system/preflight').then((r) => r.data),
  decisionAudit: (params?: { limit?: number; decision?: 'accept' | 'reject' }) =>
    client.get('/system/decision-audit', { params }).then((r) => r.data),
  updateCheck: () => client.get('/system/update-check').then((r) => r.data),
  scanLibrary: () => client.post('/system/scan').then((r) => r.data),
  tasks: () => client.get('/system/tasks').then((r) => r.data),
  runTask: (id: string) =>
    client.post(`/system/tasks/${id}/run`).then((r) => r.data),
  startCycle: () => client.post('/system/cycle/start').then((r) => r.data),
  stopCycle: () => client.post('/system/cycle/stop').then((r) => r.data),
  cleanupDuplicates: () => client.post('/system/cleanup').then((r) => r.data),
  triggerUpdate: () => client.post('/system/update').then((r) => r.data),
  recyclingBinInfo: () => client.get('/system/recycling-bin').then((r) => r.data),
  emptyRecyclingBin: () => client.post('/system/recycling-bin/empty').then((r) => r.data),

  // TV Shows
  tvShows: (params?: Record<string, unknown>) =>
    client.get('/tv/shows', { params }).then((r) => r.data),
  deleteShow: (
    ratingKey: string,
    body: { plex_rating_key: string; title: string; unmonitor_sonarr: boolean },
  ) => client.delete(`/tv/shows/${ratingKey}`, { data: body }).then((r) => r.data),
}
