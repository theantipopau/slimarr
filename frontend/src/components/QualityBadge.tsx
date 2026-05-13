import clsx from 'clsx'

interface Props {
  type: 'res' | 'codec' | 'status' | 'hdr' | 'health' | 'language'
  value: string
}

const resColors: Record<string, string> = {
  '2160p': 'bg-purple-700 text-purple-100',
  '1080p': 'bg-blue-700 text-blue-100',
  '720p': 'bg-green-700 text-green-100',
  '480p': 'bg-gray-600 text-gray-100',
}

const codecColors: Record<string, string> = {
  hevc: 'bg-orange-700 text-orange-100',
  h265: 'bg-orange-700 text-orange-100',
  av1: 'bg-pink-700 text-pink-100',
  avc: 'bg-sky-700 text-sky-100',
  h264: 'bg-sky-700 text-sky-100',
}

const hdrColors: Record<string, string> = {
  'dolby vision': 'bg-red-700 text-red-100',
  'dolby vision + hdr10': 'bg-yellow-700 text-yellow-100',
  hdr10: 'bg-emerald-700 text-emerald-100',
  'hdr10+': 'bg-emerald-700 text-emerald-100',
  sdr: 'bg-gray-600 text-gray-100',
}

const healthColors: Record<string, string> = {
  excellent: 'bg-green-700 text-green-100',
  good: 'bg-emerald-700 text-emerald-100',
  acceptable: 'bg-blue-700 text-blue-100',
  risky: 'bg-yellow-700 text-yellow-100',
  reject: 'bg-red-700 text-red-100',
}

export default function QualityBadge({ type, value }: Props) {
  const lv = value.toLowerCase()
  let cls = 'bg-gray-700 text-gray-200'

  if (type === 'res') cls = resColors[lv] ?? cls
  if (type === 'codec') cls = codecColors[lv] ?? cls
  if (type === 'hdr') cls = hdrColors[lv] ?? cls
  if (type === 'health') cls = healthColors[lv] ?? cls
  if (type === 'language') cls = lv === 'english' ? 'bg-green-800 text-green-100' : 'bg-gray-700 text-gray-200'

  return (
    <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded uppercase', cls)}>
      {value}
    </span>
  )
}
