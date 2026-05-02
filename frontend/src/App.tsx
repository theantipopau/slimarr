import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import Layout from '@/components/Layout'
import { ToastProvider } from '@/components/Toast'
import ErrorBoundary from '@/components/ErrorBoundary'

const Login = lazy(() => import('@/pages/Login'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Library = lazy(() => import('@/pages/Library'))
const MovieDetail = lazy(() => import('@/pages/MovieDetail'))
const Activity = lazy(() => import('@/pages/Activity'))
const Queue = lazy(() => import('@/pages/Queue'))
const FailedDownloads = lazy(() => import('@/pages/FailedDownloads'))
const OrphanedDownloads = lazy(() => import('@/pages/OrphanedDownloads'))
const BlacklistManagement = lazy(() => import('@/pages/BlacklistManagement'))
const Settings = lazy(() => import('@/pages/Settings'))
const System = lazy(() => import('@/pages/System'))
const TVShows = lazy(() => import('@/pages/TVShows'))

function PageLoader() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-400 flex items-center justify-center text-sm">
      Loading...
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="library" element={<Library />} />
                <Route path="library/:id" element={<MovieDetail />} />
                <Route path="activity" element={<Activity />} />
                <Route path="queue" element={<Queue />} />
                <Route path="queue/failed" element={<FailedDownloads />} />
                <Route path="queue/orphaned" element={<OrphanedDownloads />} />
                <Route path="settings/blacklist" element={<BlacklistManagement />} />
                <Route path="settings" element={<Settings />} />
                <Route path="system" element={<System />} />
                <Route path="tv" element={<TVShows />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ErrorBoundary>
    </ToastProvider>
  )
}
