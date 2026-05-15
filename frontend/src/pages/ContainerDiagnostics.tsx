import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Server, HardDrive, Container, AlertTriangle, CheckCircle, XCircle, RefreshCw, Copy } from 'lucide-react'

interface DirCheck {
  label: string
  path: string
  ok: boolean
  error?: string
}

interface DiskInfo {
  path: string
  free_bytes: number | null
  free_gb: number | null
  status: 'ok' | 'warn' | 'critical' | 'unknown'
}

interface RuntimeInfo {
  os: string
  os_release: string
  arch: string
  python: string
  in_docker: boolean
  container_id: string
  pid: number
}

interface ConfigSummary {
  config_file: string
  config_file_exists: boolean
  env_overrides: string[]
  active_providers: string[]
  download_client: string
  schedule_mode: string
  dry_run: boolean
  port: number
}

interface StartupContext {
  started_at: string
  version: string
  runtime: RuntimeInfo
  directories: DirCheck[]
  disk: DiskInfo
  config: ConfigSummary
}

interface StartupPayload {
  context: StartupContext
  warnings: string[]
}

function fmtBytes(b: number | null): string {
  if (b == null) return 'unknown'
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`
  return `${(b / 1073741824).toFixed(2)} GB`
}

function StatusIcon({ ok, warn }: { ok: boolean; warn?: boolean }) {
  if (!ok) return <XCircle className="w-4 h-4 text-red-400 shrink-0" />
  if (warn) return <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />
  return <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
}

function DiskStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok: 'bg-green-900/40 text-green-300',
    warn: 'bg-yellow-900/40 text-yellow-300',
    critical: 'bg-red-900/40 text-red-300',
    unknown: 'bg-gray-700 text-gray-400',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${map[status] ?? map.unknown}`}>
      {status}
    </span>
  )
}

const DOCKER_COMPOSE_EXAMPLE = `services:
  slimarr:
    image: ghcr.io/theantipopau/slimarr:latest
    container_name: slimarr
    restart: unless-stopped
    ports:
      - "9494:9494"
    environment:
      SLIMARR_PLEX_URL: "http://192.168.1.100:32400"
      SLIMARR_PLEX_TOKEN: "your_plex_token"
      SLIMARR_PROWLARR_URL: "http://192.168.1.100:9696"
      SLIMARR_PROWLARR_API_KEY: "your_prowlarr_key"
      SLIMARR_SABNZBD_URL: "http://192.168.1.100:8080"
      SLIMARR_SABNZBD_API_KEY: "your_sabnzbd_key"
      TZ: "America/New_York"
    volumes:
      - slimarr_data:/app/data
      - ./config:/app/config
      # - /mnt/media/movies:/media/movies:ro
volumes:
  slimarr_data:`

export default function ContainerDiagnostics() {
  const [data, setData] = useState<StartupPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  const load = () => {
    setLoading(true)
    api.startupContext()
      .then((d) => setData(d as StartupPayload))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const copyCompose = async () => {
    await navigator.clipboard.writeText(DOCKER_COMPOSE_EXAMPLE)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const ctx = data?.context
  const warnings = data?.warnings ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-2">
            <Container className="w-5 h-5 text-indigo-400" />
            Container &amp; Environment
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Runtime environment, volume validation, and deployment reference
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Startup warnings */}
      {warnings.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-4 space-y-1">
          <p className="text-sm font-medium text-yellow-300 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" />
            {warnings.length} startup warning{warnings.length > 1 ? 's' : ''}
          </p>
          {warnings.map((w, i) => (
            <p key={i} className="text-xs text-yellow-200/80 ml-5">{w}</p>
          ))}
        </div>
      )}

      {loading && !ctx && (
        <div className="text-sm text-gray-500 animate-pulse">Loading environment info…</div>
      )}

      {ctx && (
        <>
          {/* Runtime */}
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2 mb-3">
              <Server className="w-4 h-4 text-indigo-400" />
              Runtime
            </h2>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
              {[
                ['OS', `${ctx.runtime.os} ${ctx.runtime.os_release}`],
                ['Architecture', ctx.runtime.arch],
                ['Python', ctx.runtime.python],
                ['Docker', ctx.runtime.in_docker ? 'Yes' : 'No'],
                ['Container ID', ctx.runtime.container_id || '—'],
                ['PID', String(ctx.runtime.pid)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-gray-500 text-xs">{k}</dt>
                  <dd className="text-white font-mono text-xs mt-0.5">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          {/* Directories */}
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2 mb-3">
              <HardDrive className="w-4 h-4 text-indigo-400" />
              Data Directories
            </h2>
            <div className="space-y-2">
              {ctx.directories.map((d) => (
                <div key={d.label} className="flex items-center gap-2 text-sm">
                  <StatusIcon ok={d.ok} />
                  <span className="text-gray-400 w-28 shrink-0">{d.label}</span>
                  <code className="text-gray-300 text-xs font-mono">{d.path}</code>
                  {d.error && (
                    <span className="text-red-400 text-xs ml-2">{d.error}</span>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Disk space */}
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2 mb-3">
              <HardDrive className="w-4 h-4 text-indigo-400" />
              Disk Space
            </h2>
            <div className="flex items-center gap-3 text-sm">
              <DiskStatusBadge status={ctx.disk.status} />
              <span className="text-gray-300">{fmtBytes(ctx.disk.free_bytes)} free</span>
              <span className="text-gray-500 text-xs">at {ctx.disk.path}</span>
            </div>
            {ctx.disk.status === 'critical' && (
              <p className="text-xs text-red-400 mt-2">
                Critically low disk space. Downloads will likely fail. Free up space or extend the volume.
              </p>
            )}
            {ctx.disk.status === 'warn' && (
              <p className="text-xs text-yellow-400 mt-2">
                Low disk space. Consider expanding the data volume soon.
              </p>
            )}
          </section>

          {/* Config summary */}
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Configuration</h2>
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
              {[
                ['Config file', ctx.config.config_file],
                ['File exists', ctx.config.config_file_exists ? 'Yes' : 'No (using defaults)'],
                ['Download client', ctx.config.download_client],
                ['Schedule mode', ctx.config.schedule_mode],
                ['Dry run', ctx.config.dry_run ? 'Enabled' : 'Disabled'],
                ['Port', String(ctx.config.port)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-gray-500 text-xs">{k}</dt>
                  <dd className="text-white font-mono text-xs mt-0.5">{v}</dd>
                </div>
              ))}
            </dl>
            {ctx.config.active_providers.length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-gray-500 mb-1">Active providers</p>
                <div className="flex flex-wrap gap-1.5">
                  {ctx.config.active_providers.map((p) => (
                    <span key={p} className="text-xs bg-indigo-900/40 text-indigo-300 px-2 py-0.5 rounded">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {ctx.config.env_overrides.length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-gray-500 mb-1">
                  Active environment overrides ({ctx.config.env_overrides.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {ctx.config.env_overrides.map((e) => (
                    <span key={e} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded font-mono">
                      {e}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {/* Docker Compose reference */}
      <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-300">Docker Compose Quick-Start</h2>
          <button
            onClick={copyCompose}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors"
          >
            <Copy className="w-3.5 h-3.5" />
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <pre className="text-xs text-gray-300 font-mono bg-gray-950 rounded p-3 overflow-x-auto">
          {DOCKER_COMPOSE_EXAMPLE}
        </pre>
        <p className="text-xs text-gray-500 mt-2">
          All connection settings can be passed as <code className="text-gray-400">SLIMARR_*</code> environment
          variables instead of editing config.yaml. See{' '}
          <code className="text-gray-400">.env.example</code> for the full list.
        </p>
      </section>

      {/* Volume & permissions guide */}
      <section className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
        <h2 className="text-sm font-semibold text-gray-300">Linux Volume &amp; Permissions</h2>
        <div className="text-xs text-gray-400 space-y-1.5">
          <p>
            The Slimarr container runs as UID/GID <code className="text-gray-300">1000:1000</code> by default.
            If your media volumes use a different owner, rebuild with <code className="text-gray-300">--build-arg PUID=&lt;uid&gt;</code>
            {' '}or start the container with <code className="text-gray-300">--user &lt;uid&gt;:&lt;gid&gt;</code>.
          </p>
          <p>
            SMB/NFS mounts should be mounted on the <strong className="text-gray-300">host</strong> and
            bind-mounted into the container. Avoid mounting network shares directly inside the container.
          </p>
          <p>
            Data volume permissions can be fixed by running:
          </p>
          <pre className="bg-gray-950 rounded p-2 text-gray-300">
{`docker exec slimarr chown -R 1000:1000 /app/data`}
          </pre>
        </div>
      </section>
    </div>
  )
}
