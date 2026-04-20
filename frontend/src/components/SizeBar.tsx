
interface Props {
  original?: number
  current?: number
}

function pct(original?: number, current?: number): number {
  if (!original || !current) return 0
  return Math.max(0, Math.min(100, (current / original) * 100))
}

export default function SizeBar({ original, current }: Props) {
  const p = pct(original, current)
  const savings = original && current ? original - current : 0
  const savingsPct = original ? ((savings / original) * 100).toFixed(1) : '0'

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>Size: {current ? (current / 1e9).toFixed(2) : '—'} GB</span>
        {savings > 0 && (
          <span className="text-green-400">−{savingsPct}%</span>
        )}
      </div>
      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-brand-green rounded-full"
          style={{ width: `${p}%` }}
        />
      </div>
    </div>
  )
}
