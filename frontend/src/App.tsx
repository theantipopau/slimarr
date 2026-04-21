import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import Layout from '@/components/Layout'
import { ToastProvider } from '@/components/Toast'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import Library from '@/pages/Library'
import MovieDetail from '@/pages/MovieDetail'
import Activity from '@/pages/Activity'
import Queue from '@/pages/Queue'
import Settings from '@/pages/Settings'
import System from '@/pages/System'
import TVShows from '@/pages/TVShows'

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
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
            <Route path="settings" element={<Settings />} />
            <Route path="system" element={<System />} />
            <Route path="tv" element={<TVShows />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
