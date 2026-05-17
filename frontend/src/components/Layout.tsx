import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import { useSocket } from '@/hooks/useSocket'
import { useToast } from './Toast'

export default function Layout() {
  const { toast } = useToast()

  useSocket('search:warning', (payload) => {
    const warning = payload as { message?: string; detail?: { indexer?: string; provider?: string } }
    if (warning.message !== 'Indexer API quota or rate limit reached.') return

    const source = warning.detail?.indexer || warning.detail?.provider || 'Indexer'
    toast(`${source} API quota or rate limit reached. Check Search Diagnostics.`, 'error')
  })

  return (
    <div className="flex h-screen overflow-hidden bg-[#090d12] text-gray-100">
      <Sidebar />
      <main className="relative flex-1 overflow-y-auto">
        <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.035),rgba(255,255,255,0)_22rem)]" />
        <div className="relative p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
