import clsx from 'clsx'

interface Props {
  type: 'res' | 'codec' | 'status'
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

export default function QualityBadge({ type, value }: Props) {
  const lv = value.toLowerCase()
  let cls = 'bg-gray-700 text-gray-200'

  if (type === 'res') cls = resColors[lv] ?? cls
  if (type === 'codec') cls = codecColors[lv] ?? cls

  return (
    <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded uppercase', cls)}>
      {value}
    </span>
  )
}
