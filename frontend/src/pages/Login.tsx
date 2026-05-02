import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import logoSrc from '@/assets/logo.png'

export default function Login() {
  const { login, register, setupRequired, loading: authLoading, error: authError } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (setupRequired) {
        await register(username, password)
      } else {
        await login(username, password)
      }
      navigate('/')
    } catch (err: unknown) {
      const e2 = err as { response?: { data?: { detail?: string } } }
      setError(e2.response?.data?.detail ?? 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm rounded-lg border border-white/10 bg-gray-900 p-8 shadow-2xl shadow-black/40">
        <div className="text-center mb-8">
          <img src={logoSrc} alt="Slimarr" className="h-16 mx-auto mb-3" />
          <h1 className="text-2xl font-bold">
            <span className="text-brand-green">Slim</span>arr
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {authLoading
              ? 'Checking local service...'
              : setupRequired
                ? 'Create your account to get started'
                : 'Sign in to continue'}
          </p>
        </div>

        {authError && (
          <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-100">
            {authError} If this is first launch, give the tray app a few seconds and refresh.
          </div>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
              required
              disabled={authLoading || !!authError}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-green"
              required
              minLength={6}
              disabled={authLoading || !!authError}
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading || authLoading || !!authError}
            className="w-full py-2 rounded-lg bg-brand-green text-white font-semibold disabled:opacity-50"
          >
            {loading || authLoading ? 'Please wait...' : setupRequired ? 'Create Account' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
