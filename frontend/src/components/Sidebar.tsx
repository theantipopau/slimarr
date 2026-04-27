import { NavLink } from 'react-router-dom'
import logoSrc from '@/assets/logo.png'
import {
  LayoutDashboard,
  Film,
  Tv2,
  Activity,
  Download,
  AlertCircle,
  Settings,
  Server,
  LogOut,
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
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/system', icon: Server, label: 'System' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-brand-blue flex flex-col py-6 gap-1">
      {/* Logo */}
      <div className="px-4 mb-6 flex items-center gap-2">
        <img src={logoSrc} alt="Slimarr" className="h-8 w-auto" />
        <span className="text-xl font-bold">
          <span className="text-brand-green">Slim</span>
          <span className="text-white">arr</span>
        </span>
      </div>

      {links.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-3 px-4 py-2 rounded-lg mx-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-brand-green text-white'
                : 'text-gray-300 hover:bg-white/10'
            )
          }
        >
          <Icon size={18} />
          {label}
        </NavLink>
      ))}

      <div className="mt-auto mx-2 flex flex-col gap-1">
        <button
          onClick={() => {
            auth.removeToken()
            window.location.href = '/login'
          }}
          className="flex items-center gap-3 px-4 py-2 rounded-lg text-sm text-gray-400 hover:bg-white/10 w-full"
        >
          <LogOut size={18} />
          Sign Out
        </button>

        {/* Donate */}
        <a
          href="https://www.paypal.com/donate/?business=XH8CKYF8T7EBU&no_recurring=0&item_name=Thank+you+for+your+generous+donation%2C+this+will+allow+me+to+continue+developing+my+programs.&currency_code=AUD"
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-center gap-1.5 px-4 py-1.5 rounded-lg text-xs text-yellow-400 hover:bg-white/10 w-full transition-colors"
        >
          ☕ Donate
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
