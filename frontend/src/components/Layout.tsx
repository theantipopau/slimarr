import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-gray-100">
      <Sidebar />
      <main className="relative flex-1 overflow-y-auto">
        <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_left,rgba(76,175,80,0.10),transparent_32rem),radial-gradient(circle_at_top_right,rgba(33,150,243,0.08),transparent_28rem)]" />
        <div className="relative p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
