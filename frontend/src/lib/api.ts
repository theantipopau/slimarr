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

  // Activity
  activity: (params?: Record<string, unknown>) =>
    client.get('/activity', { params }).then((r) => r.data),

  // Queue
  activeDownloads: () => client.get('/queue/active').then((r) => r.data),
  recentDownloads: (limit = 20) =>
    client.get(`/queue/recent?limit=${limit}`).then((r) => r.data),

  // Settings
  getSettings: () => client.get('/settings').then((r) => r.data),
  updateSettings: (data: unknown) =>
    client.put('/settings', data).then((r) => r.data),
  testConnection: (service: string, body?: unknown) =>
    client.post(`/settings/test/${service}`, body ?? null).then((r) => r.data),

  // System
  systemStatus: () => client.get('/system/status').then((r) => r.data),
  systemInfo: () => client.get('/system/info').then((r) => r.data),
  servicesHealth: () => client.get('/system/health/services').then((r) => r.data),
  scanLibrary: () => client.post('/system/scan').then((r) => r.data),
  tasks: () => client.get('/system/tasks').then((r) => r.data),
  runTask: (id: string) =>
    client.post(`/system/tasks/${id}/run`).then((r) => r.data),
  startCycle: () => client.post('/system/cycle/start').then((r) => r.data),
  stopCycle: () => client.post('/system/cycle/stop').then((r) => r.data),
}
