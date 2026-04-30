import type { LucideIcon } from 'lucide-react'

interface Props {
  label: string
  value: string | number
  icon: LucideIcon
  sub?: string
  color?: string
}

export default function StatCard({ label, value, icon: Icon, sub, color = 'text-brand-green' }: Props) {
  return (
    <div className="group flex items-center gap-4 rounded-xl border border-white/5 bg-gray-900/80 p-5 shadow-lg shadow-black/20 backdrop-blur transition-colors hover:border-white/10 hover:bg-gray-900">
      <div className={`rounded-lg border border-white/5 bg-gray-800/90 p-3 shadow-inner ${color}`}>
        <Icon size={24} />
      </div>
      <div>
        <p className="text-sm text-gray-400">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
        {sub && <p className="text-xs text-gray-500">{sub}</p>}
      </div>
    </div>
  )
}
