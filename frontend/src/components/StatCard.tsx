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
    <div className="bg-gray-900 rounded-xl p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg bg-gray-800 ${color}`}>
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
