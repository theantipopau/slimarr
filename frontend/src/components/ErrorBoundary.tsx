import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="flex min-h-screen items-center justify-center bg-gray-950 px-4 text-center">
          <div className="w-full max-w-md rounded-lg border border-red-500/30 bg-gray-900 p-6 shadow-2xl shadow-black/40">
            <p className="text-red-300 font-semibold">Slimarr could not render this screen</p>
            <p className="mt-2 text-zinc-400 text-sm">{this.state.error?.message}</p>
            <div className="mt-5 flex justify-center gap-3">
              <button
                className="rounded bg-gray-700 px-3 py-2 text-sm text-zinc-100 hover:bg-gray-600"
                onClick={() => window.location.reload()}
              >
                Reload
              </button>
              <button
                className="rounded bg-brand-green px-3 py-2 text-sm font-medium text-white hover:brightness-110"
                onClick={() => this.setState({ hasError: false, error: null })}
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
