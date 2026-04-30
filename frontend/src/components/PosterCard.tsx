import type { Movie } from '@/lib/types'
import QualityBadge from './QualityBadge'
import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle, Loader } from 'lucide-react'

interface Props {
  movie: Movie
}

function formatGB(bytes?: number): string {
  if (!bytes) return '--'
  return (bytes / 1_073_741_824).toFixed(1) + ' GB'
}

const statusBorder: Record<string, string> = {
  improved: 'border-green-500',
  downloading: 'border-blue-400',
  pending: 'border-gray-700',
  failed: 'border-red-500',
}

export default function PosterCard({ movie }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const posterUrl = movie.poster_path
    ? `/api/v1/images/${movie.id}/poster`
    : null

  return (
    <div
      className={`bg-gray-900 rounded-lg overflow-hidden cursor-pointer border ${statusBorder[movie.status] ?? 'border-gray-700'} hover:-translate-y-1 hover:border-gray-500 hover:shadow-2xl hover:shadow-black/30 transition-all relative group`}
      onClick={() => navigate(`/library/${movie.id}`, { state: { fromLibrary: `${location.pathname}${location.search}` } })}
    >
      {posterUrl ? (
        <img src={posterUrl} alt={movie.title} className="w-full aspect-[2/3] object-cover" loading="lazy" />
      ) : (
        <div className="w-full aspect-[2/3] bg-gray-800 flex items-center justify-center text-gray-600 text-xs text-center p-2">
          {movie.title}
        </div>
      )}

      {movie.status === 'improved' && (
        <div className="absolute top-1.5 right-1.5">
          <CheckCircle size={18} className="text-green-400 drop-shadow-lg" />
        </div>
      )}
      {movie.status === 'downloading' && (
        <div className="absolute top-1.5 right-1.5">
          <Loader size={18} className="text-blue-400 animate-spin drop-shadow-lg" />
        </div>
      )}
      {movie.status === 'failed' && (
        <div className="absolute top-1.5 left-1.5 bg-red-600 rounded text-xs px-1 py-0.5 text-white font-bold leading-none">
          ERR
        </div>
      )}

      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2">
        <p className="text-xs font-semibold text-white leading-tight">{movie.title}</p>
        {movie.year && <p className="text-xs text-gray-300">{movie.year}</p>}
      </div>

      <div className="p-2">
        <p className="text-xs font-semibold truncate">{movie.title}</p>
        <div className="flex items-center justify-between mt-0.5">
          <p className="text-xs text-gray-400">{movie.year}</p>
          <p className="text-xs text-gray-500">{formatGB(movie.file_size)}</p>
        </div>
        {(movie.resolution || movie.video_codec) && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {movie.resolution && <QualityBadge type="res" value={movie.resolution} />}
            {movie.video_codec && <QualityBadge type="codec" value={movie.video_codec} />}
          </div>
        )}
      </div>
    </div>
  )
}
