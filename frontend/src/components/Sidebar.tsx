import { NavLink } from 'react-router-dom'
import logoSrc from '@/assets/logo.png'
import {
  LayoutDashboard,
  Film,
  Tv2,
  Activity,
  Download,
  AlertCircle,
  Radar,
  ShieldBan,
  Settings,
  Server,
  Container,
  LogOut,
  Coffee,
} from 'lucide-react'
import { auth } from '@/lib/auth'
import clsx from 'clsx'

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/library', icon: Film, label: 'Library' },
  { to: '/tv', icon: Tv2, label: 'TV Shows' },
  { to: '/activity', icon: Activity, label: 'Activity' },
  { to: '/queue', icon: Download, label: 'Queue' },
  { to: '/queue/failed', icon: AlertCircle, label: 'Failed Downloads' },
  { to: '/queue/orphaned', icon: AlertCircle, label: 'Orphaned Downloads' },
  { to: '/system/search-diagnostics', icon: Radar, label: 'Search Diagnostics' },
  { to: '/system/container', icon: Container, label: 'Container' },
  { to: '/settings/blacklist', icon: ShieldBan, label: 'Blacklist' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/system', icon: Server, label: 'System' },
]

export default function Sidebar() {
  return (
    <aside className="flex h-full min-h-0 w-56 flex-col gap-1 border-r border-white/10 bg-[#0d1721] py-6 shadow-2xl shadow-black/30">
      {/* Logo */}
      <div className="px-4 mb-6 flex items-center gap-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
          <img src={logoSrc} alt="Slimarr" className="h-7 w-auto" />
        </div>
        <span className="text-xl font-bold">
          <span className="text-brand-green">Slim</span>
          <span className="text-white">arr</span>
        </span>
      </div>

      <nav className="flex-1 min-h-0 overflow-y-auto px-2">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-green text-white shadow-lg shadow-green-950/30'
                  : 'text-gray-300 hover:bg-white/[0.07] hover:text-white'
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto mx-2 flex flex-col gap-1">
        <button
          onClick={() => {
            auth.removeToken()
            window.location.href = '/login'
          }}
          className="flex w-full items-center gap-3 rounded-lg px-4 py-2 text-sm text-gray-400 hover:bg-white/[0.07] hover:text-white"
        >
          <LogOut size={18} />
          Sign Out
        </button>

        {/* Donate */}
        <a
          href="https://www.paypal.com/donate/?business=XH8CKYF8T7EBU&no_recurring=0&item_name=Thank+you+for+your+generous+donation%2C+this+will+allow+me+to+continue+developing+my+programs.&currency_code=AUD"
          target="_blank"
          rel="noreferrer"
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-1.5 text-xs text-yellow-200 transition-colors hover:bg-yellow-500/10"
        >
          <Coffee size={14} />
          Donate
        </a>

        {/* Creator credit */}
        <a
          href="https://matthurley.dev"
          target="_blank"
          rel="noreferrer"
          className="block text-center text-xs text-gray-600 hover:text-gray-400 transition-colors px-2 py-2"
        >
          Created by Matt Hurley
        </a>
      </div>
    </aside>
  )
}
