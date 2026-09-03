<p align="center">
  <img src="images/header-logo.PNG" alt="Slimarr" width="420" />
</p>

<p align="center">
  <strong>Automatically shrink your Plex library - find smaller, better-compressed releases on Usenet and replace bloated files overnight.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11--3.13-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/fastapi-0.115-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Docker%20%7C%20Windows-0ea5e9" />
  <img src="https://img.shields.io/badge/release-2.0.0.0-success" />
</p>

<p align="center">
  <a href="https://theantipopau.github.io/slimarr/">Project Website (GitHub Pages)</a>
</p>

---

## What is Slimarr?

Plex libraries accumulate large files over time - bloated remuxes, old h264 Blu-ray rips, and poorly compressed encodes. Modern codecs like **h265/HEVC** and **AV1** deliver equivalent or better visual quality at a fraction of the file size.

**Slimarr automates the entire replacement workflow:**

```
Scan Plex library -> Search Usenet indexers -> Compare releases
-> Queue download via SABnzbd or NZBGet -> Replace file -> Refresh Plex -> Log savings
```

**Core rule: save space safely.** A release is normally accepted only when it is smaller than your existing copy. Slimarr can make a bounded exception for clearly poor local media such as CAM/TS, weak 720p, or suspiciously low-bitrate files when the candidate is a strong 1080p quality upgrade.

Slimarr is designed to look and feel like a native member of the **\*arr ecosystem** (Radarr, Sonarr, Prowlarr). If you're familiar with those tools, you'll feel right at home.

Current release: **2.0.0.0** (2026-09-03).

### What's New in 2.0.0.0 - Discovery & Recommendations, Backend Audit, ARR Platform Gap Analysis

- **New: Discovery & Recommendations.** A new page suggests titles related
  to what you already own - missing collection entries, sequels/prequels,
  and related titles - each with a deterministic score and a transparent,
  human-readable reason. No AI is required or contacted by default
  (`recommendations.enabled: false` out of the box).
- **New: region-specific streaming availability**, sourced only from TMDB's
  own `/watch/providers` endpoint - no streaming service is ever scraped or
  asked for credentials - timestamped and treated as stale after 24 hours.
- **New: explicit, capability-checked hand-off to Radarr/Sonarr** from a
  recommendation. Sending a title requires you to confirm the root folder
  and quality profile; it's never automatic, and it's duplicate-checked
  against the live instance first. Seerr hand-off is intentionally not
  implemented this release - see `docs/RECOMMENDATION_INTEGRATIONS.md`.
- **New: optional, provider-neutral AI reranking abstraction**, disabled by
  default with only a no-op provider shipped. It can only rerank a
  candidate list Slimarr already sourced or produce short explanations - it
  cannot invent titles or availability, cannot see your Plex token or file
  paths, and every AI-returned ID is re-validated against TMDB. See
  `docs/RECOMMENDATION_PRIVACY.md`.
- **Full backend/frontend audit** against the actual implementation (not
  README claims), plus a competitive gap analysis against Radarr, Sonarr,
  Prowlarr, Seerr, Bazarr, Tautulli, and Recyclarr for transferable
  architectural patterns. See `docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md`
  and `docs/ARR_PLATFORM_GAP_ANALYSIS.md`.
- **Fixed:** a failed orphan-file removal could still delete its own
  tracking row, silently losing track of the orphan. Cleanup is now
  success-gated.
- **Fixed:** two SABnzbd error paths could log an API key embedded in a
  request URL. Errors are now redacted before logging.
- **Fixed:** a path containing an embedded `..` could evade NAS-prefix
  classification, and classification was case-folded even on case-sensitive
  filesystems - both could bypass or falsely trigger NAS budget/throttle
  protection.
- **Fixed:** a cross-device NAS copy whose final source-cleanup step failed
  after the copy itself succeeded was reported as a failed move (leaving a
  duplicate and a misleading status) instead of a completed one with a
  warning.
- **Fixed:** the image-proxy endpoint could leak a raw exception, and a
  job's event timeline had no upper bound. TMDB/Radarr/Sonarr's original
  methods now reuse the app's pooled HTTP client for connection reuse.

Upgrade notes: `docs/UPGRADE_NOTES_2.0.0.md`. No existing config key, API
route, or behavior changed - the new feature is entirely opt-in.

### What's New in 1.9.0.0 - Full Codebase Review, Config Correctness, and Navigation Rework

- **Fixed `exclusions:` in config.yaml silently doing nothing.** The whole
  section (movie IDs, title keywords, folders, codecs, resolutions, a
  minimum file size, a maximum library age) was defined and validated but
  never read anywhere — personal footage living in the same Plex library as
  movies (home videos, wedding films) was being sent as search queries to
  public Usenet indexers every cycle. Exclusions are now checked before a
  search is ever issued, with a full Settings UI section to configure them.
- **Fixed the root cause of "database is locked" failures during
  downloads.** SQLite was running in its default rollback-journal mode,
  which takes an exclusive lock for the duration of any write. WAL mode
  plus a busy-timeout are now set on every connection.
- **Fixed `Movie.source_type` never being populated,** which silently
  weakened the comparer's source-quality upgrade checks for every movie.
  It's now set from the actual release title on replacement, and guessed
  from the filename during scans for movies not yet replaced.
- **Fixed uploader-health scoring blocking the event loop and always
  returning the default score on PostgreSQL** — replaced a per-candidate
  synchronous SQLite query (100+ times per movie search) with one batched
  async query per search that works on either database.
- Fixed the rate-limit toast never firing for one of its two trigger paths,
  fixed the same file size showing different numbers on different pages,
  and fixed TV endpoints swallowing errors without logging them.
- **Sidebar navigation regrouped** into labeled sections (Library, Activity,
  System, Settings) with live failed/orphaned/active download badge counts,
  instead of 13 links in a flat list.
- Self-hosted the UI font instead of pulling it from Google Fonts on every
  page load, replaced the last native `window.confirm` dialog with the
  app's own styled confirmation modal, and unified the brand accent color.

Full standalone release notes: `docs/CHANGELOG_v1.9.0.0.md`.

### What's New in 1.8.0.0 - Optimization, Observability, and Premium Polish Pass

- **Fixed the replace-loop bug for real this time.** The 1.7.1.0 fix only
  re-probed a replaced file's resolution/codec/bitrate when
  `files.enable_media_probe` was explicitly turned on — but that setting
  defaults to off, so anyone who hadn't enabled it got no benefit at all.
  The post-replacement probe now always runs (it's one file, not a bulk
  scan), and the scanner no longer lets a possibly-stale Plex read clobber
  it on the next pass.
- **Fixed a second, still-active replace-loop cause found in live logs:** a
  movie failing to replace every night because the existing file was
  briefly locked by another process (`[WinError 32]`) — both the recycle
  move and the fallback backup-move now retry a few times before giving up,
  since this kind of lock is almost always transient.
- **Performance:** the Plex library scan no longer blocks the whole app
  (API requests, scheduler, live updates) for its full duration; the retry
  ladder's blacklist check went from one query per candidate to one query
  total; the orphan scanner's per-history-item DB checks (up to 5,000 items)
  are now a single batched query; the NAS-pressure panel no longer pulls
  every rejection reason into Python just to count a substring match.
- **Observability:** silently-swallowed Radarr/uploader-health errors now
  log with context; a dead download client no longer floods the log with
  an identical warning every 5 seconds; a movie whose TMDB lookup
  permanently 404s no longer retries every single scan forever.
- **UI/UX polish pass:** unified inconsistent status-color palettes and
  loading/empty states across most pages, fixed a sidebar nav bug that
  double-highlighted parent/child routes, deduplicated ~200 lines of
  copy-pasted NAS-preset logic between Dashboard and System into a shared
  hook, memoized several list components, and fixed a login-page bug where
  a transient startup connectivity error permanently locked out the form
  until a manual refresh.

Full standalone release notes: `docs/CHANGELOG_v1.8.0.0.md`.

### What's New in 1.7.1.0 - Replacement-Loop Fix and UI Correctness Patches

- **Fixed the root cause of movies being endlessly re-downloaded and
  replaced.** `replace_file()` updated a movie's tracked file path/size after
  a replacement but never its resolution/codec/bitrate, so the recorded
  quality stayed stuck at the previous file's values forever — making the
  (correctly-replaced) local copy look perpetually upgradeable and
  triggering another replacement every cycle. It now re-probes the file at
  its final location and persists the real values.
- Added a `(decision, created_at)` composite index for the NAS
  storage-pressure dashboard query, which was taking up to 6.4 seconds in
  production because the existing index wasn't being used for this query
  shape.
- Fixed a Movie Detail bug where navigating to a different movie shortly
  after triggering a search/process/download could let the previous movie's
  stale response overwrite the new movie's on-screen data.
- Fixed a Library search race that could show results for an earlier,
  superseded query when typing quickly.
- Fixed the System page "Run Now" button getting stuck on "Starting…"
  indefinitely when starting the automation cycle failed outright.

Full standalone release notes: `docs/CHANGELOG_v1.7.1.0.md`.

### What's New in 1.7.0.0 - Storage-Safe Automation and Persistent Jobs

- **Fixed the root cause of NAS freezes/crashes during file replacement.**
  Blocking filesystem calls (`shutil.disk_usage`, `os.makedirs`,
  `os.path.exists`/`getsize`, directory walks) were running directly on the
  asyncio event loop in the replace/cleanup path — on a slow or sleeping NAS
  share, those calls could block the *entire app* for seconds at a time. All
  blocking filesystem access in that path now runs on worker threads,
  matching the pattern already used elsewhere in the NAS-safety code.
- Added a shared storage-safety layer (`backend/core/storage.py`) that all
  replacement, duplicate-cleanup, failed-download, orphan, and recycling
  operations now route through: path classification, preflight checks,
  per-path locks, NAS write/replacement budgets, failure cooldowns, and
  persisted operation telemetry that survives restarts.
- Added a persistent job runtime (durable `jobs`/`job_events` tables) so
  scans, automation cycles, duplicate previews/cleanup, and scheduled tasks
  survive a restart instead of losing progress as in-memory state.
- Added replacement recovery tracking so interrupted replacements (original
  recycled but new file not yet placed, etc.) are visible and recoverable
  instead of silently leaving the library half-updated.
- Added a dedicated Operations page (`/system/operations`) for active and
  historical jobs, storage operation history, NAS budget status, and guarded
  retry/cancel/purge actions.
- Implemented `files.verify_after_download` (previously a no-op that warned
  on every startup): downloads are now rejected before replacement if the
  file is empty, with an optional media-stream check when media probing is
  enabled.
- Unified destructive-action confirmation across the UI (TV show delete,
  blacklist removal, orphan cleanup, recycling purge, duplicate cleanup) on
  one shared confirm dialog, and added consistent loading-skeleton and
  empty-state treatment across Library, Queue, Operations, Orphaned
  Downloads, and Blacklist.
- Hardened error handling and SQL-identifier safety in a security/code-health
  pass; see `CHANGELOG.md` for the full list.
- Updated `docs/DOCKER.md` with the full NAS-safety environment variable set
  and new Prometheus metrics, which were previously undocumented even though
  `.env.example` and the Compose templates already supported them.

Deeper visual redesign of Dashboard/Library/Movie Detail/Settings and new
release artwork are still in progress and will land in a follow-up release —
see `docs/VERSION_1_7_ROADMAP.md` for status. Full standalone release notes:
`docs/CHANGELOG_v1.7.0.0.md`.

### What's New in 1.6.1.0 - NAS Resilience and UI Polish

- Added NAS-safe pacing controls (`min_cycle_interval_minutes`, `max_downloads_per_night`, and `throttle_seconds`) to reduce bursty read/write pressure.
- Added NAS-aware replacement policy (`files.nas_path_prefixes` + `comparison.min_savings_mb_for_nas`) so low-value churn replacements are blocked on network-mounted libraries.
- Added optional media-probe reduction (`files.enable_media_probe`) and recycle-bin stats caching to lower background storage pressure.
- Added a System NAS Pressure panel with 24-hour pressure telemetry, recommendations, and one-click gentle/balanced/aggressive presets.
- Added Dashboard polish: NAS pressure recommendation banner, quick-start checklist, compact system-health strip, and preset rollback (`Restore Previous`).
- Added first-run Welcome Setup to apply safe defaults quickly for NAS path and stability profile.
- Added audio-quality pills on movie cards/detail headers plus global audio preference ordering (`comparison.preferred_audio_codecs`).
- Added optional strict audio mode (`comparison.require_preferred_audio_match`) to reject candidates that do not match preferred audio formats.

### What's New in 1.5.0.0 - Foundation

- Optional PostgreSQL backend support through `SLIMARR_DB_URL` while SQLite remains the default
- Per-movie quality intent controls for Space Saver, Balanced, Premium, Reference, Locked, and Pinned behavior
- Force-keep and lock safeguards so protected titles are skipped consistently by automation
- Profile-aware compare decisions with override controls for resolution floor, preferred codec, preferred sources, release-group rejects, and size-increase limits
- Search diagnostics now detect indexer/Prowlarr quota and rate-limit responses and notify users immediately
- Windows installer/startup launchers now start the tray app path so the tray icon appears on first launch

### What's New in 1.4.0.0 - Containerised

- Official Docker-first deployment model with multi-stage Docker build and compose templates
- New environment-variable config model (`SLIMARR_*`) with precedence:
  env vars -> config.yaml -> defaults
- Linux-ready startup validation with mount/write checks, disk-space warnings,
  runtime/architecture detection, and startup diagnostics
- Prometheus-compatible metrics endpoint (`/api/v1/system/metrics`) and improved
  health endpoint behavior for degraded startup conditions
- Container diagnostics UI (`System -> Container`) showing runtime, mount health,
  disk state, and copyable compose reference
- New deployment docs for Docker, reverse proxy, Unraid, Synology, and migration

See `docs/DOCKER.md` for full deployment guidance.

### What's New in 1.3.0.0

- Search Diagnostics page and Search Test Harness for inspecting live Prowlarr/Newznab requests, redacted request URLs, status codes, latency, raw/parsed counts, parser failures, filtered results, and rejection reasons
- Degraded-search detection that warns on suspicious zero-result streaks and pauses automation when all configured providers repeatedly fail
- Quality Intelligence V2 for detecting poor existing copies and preferring good 1080p WEB-DL, BluRay, WEBRip, and efficient encodes
- Dolby Vision safety mode enabled by default to avoid DV-only releases unless an HDR fallback is explicitly allowed
- Expanded language/audio/subtitle safeguards for English audio requirements, hardcoded subtitle blocking, and dual/multi-audio visibility
- Media Health scoring with Excellent, Good, Acceptable, Risky, and Reject ratings on candidates and decision audit records

### What's New in 1.2.0.0

- Dashboard command-center stats for library size, total savings, pending candidates, active downloads, failed items, last scan, and integration health
- Integration Matrix covering Plex, Radarr, Sonarr, Prowlarr, SABnzbd, NZBGet, TMDB, and direct indexers
- Candidate confidence scoring with component breakdowns and clearer rejection reasons
- Dry-run and review-required safety modes for inspecting accepted candidates before downloading/replacing
- Candidate details drawer on Movie Detail search results
- Settings connection tests now use unsaved form values for every major integration

---

## Screenshots

| Dashboard | Movie Detail |
|-----------|--------------|
| ![Dashboard](images/dashboard.png) | ![Movie Detail](images/moviedetails.png) |

| Activity | System |
|----------|--------|
| ![Activity](images/activity.png) | ![System](images/system.png) |

---

## Features

- **Docker-first deployment** - official multi-stage image, compose templates, and non-root runtime
- **Full Linux support** - validated startup checks, mount awareness, and container-safe defaults
- **Environment-variable config** - `SLIMARR_*` overrides for secrets and runtime settings
- **Operational observability** - health endpoints, startup diagnostics, and Prometheus metrics
- **Nightly automation** - scheduled cycle searches, downloads and replaces movies while you sleep
- **Usenet search** - supports Prowlarr (recommended) or direct Newznab/NZBGeek indexers
- **Download client integration** - supports SABnzbd by default, with NZBGet support included
- **Plex sync** - reads your library via PlexAPI, refreshes Plex after each replacement
- **TMDB enrichment** - posters, backdrops, and metadata fetched and cached locally
- **Smart comparison engine** - configurable minimum savings %, resolution downgrade protection, codec preferences, language filtering
- **Search diagnostics** - v1.3 adds live visibility into indexer requests, parser failures, raw/parsed counts, filtering stages, and provider reliability
- **Media Health scoring** - v1.3 rates release quality and explains risky candidates before automation can act
- **Path mappings** - translate Plex-reported file paths to locally accessible paths when Plex and Slimarr run on different machines or use different mount points
- **Language filtering** - reject candidates in unwanted languages; prefer English (or any configured language)
- **AV1/h265 preference** - codec scoring bonus for modern efficient codecs
- **Minimum file size floor** - skip tiny low-quality candidates regardless of savings %
- **Real-time UI** - Socket.IO pushes scan progress, download progress, and replacement events to the browser instantly
- **Toast notifications** - non-intrusive feedback for every action
- **Recycling bin controls** - optionally move originals to a configured directory, monitor live usage in Settings, and empty it on demand
- **Duplicate file cleanup** - detect and remove inferior duplicate copies within your Plex library
- **Duplicate cleanup preview** - estimates reclaimable space and confidence before any file action
- **Maintenance Intelligence** - telemetry-aware utilities score with safe, transparent recommendations
- **TV Show Stale Media Sweeper** - Slimarr surfaces never-watched or long-unwatched TV shows with their disk footprint so *you* can decide what to delete; optionally unmonitors in Sonarr to prevent re-download
- **System tray** - runs as a Windows tray app with one-click open browser
- **Activity log** - full history of every replacement with old/new size and savings %
- **Update checker** - System page shows a badge when a newer version is available on GitHub
- **Radarr-compatible feel** - sidebar nav, poster grid, quality badges, test connection buttons
- **Discovery & recommendations** - deterministic suggestions for missing collection entries, sequels/prequels, and related titles based on what you already own; region-specific streaming availability via TMDB; optional explicit hand-off to Radarr/Sonarr - nothing is ever downloaded automatically

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Docker Engine + Compose | Current | Recommended deployment path for Linux/homelab |
| Python | 3.11 – 3.13 | Required only for source install; **3.14 is not supported** |
| Node.js | 18+ | Required only when building frontend from source |
| Plex Media Server | Any | PlexAPI token required |
| SABnzbd or NZBGet | Any | Configure at least one download client |
| Prowlarr **or** Newznab indexer | Any | At least one required |
| TMDB API key | Free | For posters and metadata |

---

## Installation

### Option A - Docker (recommended)

Slimarr v1.5 keeps the v1.4 Docker-first deployment model and adds optional advanced runtime features.

1. Copy `docker-compose.yml` and `.env.example` from this repository.
2. Rename `.env.example` to `.env` and fill in your service values.
3. Start Slimarr with the direct compose command:

```bash
docker compose up -d
```

No-file quick launch from shell (Linux/macOS):

```bash
curl -fsSL https://raw.githubusercontent.com/theantipopau/slimarr/main/docker-compose.yml | docker compose -f - up -d
```

No-file quick launch from shell (PowerShell):

```powershell
(Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/theantipopau/slimarr/main/docker-compose.yml).Content | docker compose -f - up -d
```

Repository helper wrappers are also available:

```powershell
./scripts/slimarr-compose.ps1 up -d
```

```bash
./scripts/slimarr-compose.sh up -d
```

4. Open `http://<your-host>:9494` and complete first-run setup.

For Traefik, Unraid, Synology, reverse proxy, volumes, and migration details,
see `docs/DOCKER.md`.

Optional PostgreSQL deployments use the companion template:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

### Option B - Windows installer

Download `SlimarrSetup-1.8.0.0.exe` (or the latest `SlimarrSetup-*.exe`) from the [Releases](https://github.com/theantipopau/slimarr/releases) page and run it. The installer bundles Python and all dependencies - no manual setup required. After install, Slimarr appears in the Start Menu and optionally the system tray on login.

At the end of setup, the installer shows `Start Slimarr now` (checked by default). If selected, Slimarr starts minimized with the tray icon available and your browser opens automatically to `http://localhost:9494` when the backend is ready.

`1.8.0.0` is the current release target. Newer `main` branch changes may land before the next installer is cut; if you want those immediately, run Slimarr from source or Docker.

### Option C - From source

**1. Clone the repository:**
```powershell
git clone https://github.com/theantipopau/slimarr.git C:\Slimarr
cd C:\Slimarr
```

**2. Run the source install script:**
```powershell
.\install.ps1
```

The install script will:
- Create a Python virtual environment
- Install all Python dependencies
- Install Node.js frontend dependencies and build the React app

**3. Start Slimarr:**
```powershell
# Simplest (starts backend + opens browser):
start.bat

# Alternative headless command:
python run.py --headless
```

**4. Open your browser to `http://localhost:9494`** and complete the one-time registration.

**5. Configure** your services in Settings - Plex, SABnzbd, TMDB, and at least one indexer are required.

### Keeping up to date

Use one update path consistently:

- **Source install (git clone)**: run `update.bat` (or `git pull`) inside your Slimarr repo folder.
- **Installer install (Start Menu / Program Files)**: install the newest `SlimarrSetup-*.exe` from Releases.

`update.bat` only updates the git working copy it is run from; it does **not** patch an already-installed Program Files build.

Keep `config.yaml` and `data/` when upgrading. Your settings/database remain intact as long as those are preserved.

---

## Troubleshooting

### Docker / Linux quick checks

```bash
# Container logs
docker logs -f slimarr

# Container health status
docker inspect --format='{{json .State.Health}}' slimarr

# API health endpoint
curl -fsS http://localhost:9494/api/v1/system/health

# Prometheus metrics endpoint
curl -fsS http://localhost:9494/api/v1/system/metrics
```

If mounts or permissions are wrong, open **System -> Container** in the UI.
Slimarr v1.5 surfaces startup mount checks, writable-path checks, database backend details, and low-disk warnings there.

### "Building wheel for lxml failed" / "Building wheel for pydantic-core failed"

**Symptoms in `startup-error.log`:**
```
error: Microsoft Visual C++ 14.0 or greater is required
```
or
```
error: linker link.exe not found
```

**Cause:** You have Python 3.14 installed. `lxml` and `pydantic-core` do not yet publish prebuilt Windows packages (wheels) for Python 3.14, so pip tries to compile them from source — which requires Visual C++ Build Tools and Rust. Most users don't have these.

**Fix:**
1. Install Python **3.12** or **3.13** from https://python.org (tick *Add Python to PATH*).
2. Delete the `venv` folder in your Slimarr directory.
3. Rerun `install.ps1`.

The installer will automatically prefer 3.13 → 3.12 → 3.11 and skip 3.14.

### "Failed to establish a new connection" / WinError 10013

**Cause:** A firewall, VPN, or endpoint-security policy is blocking outbound HTTPS to `pypi.org`.

**Fix:**
- Allow outbound port 443 for `python.exe` and `venv\Scripts\python.exe` in your firewall or AV.
- On a corporate proxy, set before running the installer:
  ```powershell
  $env:HTTPS_PROXY = "http://user:pass@proxy:port"
  $env:HTTP_PROXY  = "http://user:pass@proxy:port"
  ```
- Test connectivity: `Test-NetConnection pypi.org -Port 443`

## GitHub Pages Website

Slimarr includes a simple project website in `docs/` for GitHub Pages.

1. Push this repository to GitHub.
2. Open **Settings -> Pages** in your GitHub repo.
3. Under **Build and deployment**, set:
  - **Source**: Deploy from a branch
  - **Branch**: `main`
  - **Folder**: `/docs`
4. Save and wait for deployment.

Your site URL will be:

`https://theantipopau.github.io/slimarr/`

---

## Configuration

`config.yaml` is created automatically on first run. Key sections:

In v1.4, configuration precedence is:

```
SLIMARR_* environment variables -> config.yaml -> built-in defaults
```

Common env vars include: `SLIMARR_PLEX_URL`, `SLIMARR_PLEX_TOKEN`,
`SLIMARR_PROWLARR_URL`, `SLIMARR_PROWLARR_API_KEY`, `SLIMARR_SABNZBD_URL`,
`SLIMARR_SABNZBD_API_KEY`, `SLIMARR_LOG_LEVEL`, `SLIMARR_LOG_FORMAT`, and `TZ`.

See `.env.example` for the full list.

```yaml
plex:
  url: "http://localhost:32400"
  token: "your-plex-token"
  library_sections:
    - "Movies"

sabnzbd:
  url: "http://localhost:8080"
  api_key: "your-sabnzbd-api-key"
  category: "slimarr"

download_client: "sabnzbd"   # "sabnzbd" or "nzbget"

nzbget:
  url: "http://localhost:6789"
  username: ""
  password: ""
  category: "slimarr"

prowlarr:
  enabled: true
  url: "http://localhost:9696"
  api_key: "your-prowlarr-api-key"

tmdb:
  api_key: "your-tmdb-api-key"

comparison:
  min_savings_percent: 10.0          # Reject candidates saving less than this
  allow_resolution_downgrade: false   # e.g. block 1080p -> 720p replacements
  preferred_codecs: ["av1", "h265"]
  preferred_language: "english"       # Reject foreign-language releases
  minimum_file_size_mb: 500           # Ignore candidates below this size
  avoid_dolby_vision: true            # v1.3: block DV-only releases by default
  allow_dolby_vision_with_hdr_fallback: false
  require_english_audio: true
  reject_hardcoded_subs: true
  allow_size_increase_for_low_quality: true
  max_size_increase_percent_for_quality_upgrade: 250.0
  max_quality_upgrade_size_gb: 8.0

radarr:
  enabled: false
  url: "http://localhost:7878"
  api_key: "your-radarr-api-key"

sonarr:
  enabled: false
  url: "http://localhost:8989"
  api_key: "your-sonarr-api-key"

files:
  recycling_bin: ""              # Leave empty to delete originals immediately (recommended).
                                 # Set a path (e.g. D:/recycle) to keep copies temporarily.
  recycling_bin_cleanup_days: 30 # Auto-delete recycled files older than this many days
  enable_media_probe: false
  nas_path_prefixes:
    - "Z:/Movies"
  nas_max_write_gb_per_day: 150
  nas_max_replacements_per_day: 3
  nas_max_concurrent_operations: 1
  nas_failure_cooldown_minutes: 15
  nas_max_transfer_mbps: 50
  nas_copy_chunk_mb: 8

  # Path mappings: use when Plex reports file paths that Slimarr can't
  # access directly (different machine, different drive letter/mount point).
  # plex_path: what Plex says  ->  local_path: what Slimarr can write to
  plex_path_mappings: []
  # Example:
  # plex_path_mappings:
  #   - plex_path: "/data/media"
  #     local_path: "E:/media"

schedule:
  start_time: "01:00"   # UTC
  end_time: "07:00"
  max_downloads_per_night: 10
  throttle_seconds: 30
  max_active_download_hours: 24

recommendations:
  enabled: false            # Off by default - nothing is sourced or scored until enabled
  region: ""                # Two-letter TMDB region (e.g. "US", "AU"); leave empty to disable
                             # streaming-availability lookups entirely - never guessed
  subscribed_providers: []  # TMDB watch-provider IDs to highlight; empty means "show all"
  enabled_categories:
    - "collection_completion"
    - "sequel_prequel"
    - "related_title"
  media_types:
    - "movie"                # TV recommendations are not implemented in this release
  minimum_score: 40.0
  languages: []              # Restrict to specific original languages; empty = no restriction
  genres_include: []
  genres_exclude: []
  excluded_keywords: []
  use_plex_watch_history: false  # Opt-in: required before any watch-history signal is used
  refresh_interval_hours: 24
  max_recommendations_retained: 500
  ai:
    enabled: false           # Off by default; only reranks/explains an already-sourced list -
                              # never invents titles, availability, or triggers downloads
    provider: "none"         # "none" | "openai_compatible" | "anthropic" | "ollama"
    base_url: ""
    model: ""
    api_key: ""
    timeout_seconds: 20
    share_watch_history: false  # Separate opt-in from use_plex_watch_history above
```

> **Note on disk space:** By default `recycling_bin` is empty, meaning old files are deleted immediately when a replacement succeeds. If you configure a recycling bin path, be aware that replaced movie files (typically 10-50 GB each) accumulate there until the nightly cleanup runs. Use a path on a drive with plenty of headroom, or leave the setting empty.

---

### NAS-safe deployment

Keep Slimarr's database, logs, configuration, and image cache on local storage. Mount only the media library from the NAS. SQLite performs many small transactional writes and should not be placed on SMB or NFS storage.

List every real NAS root in NAS Movie Path Prefixes. Do not use a placeholder drive: an incorrect prefix causes mapped network drives to be treated as local. UNC paths are detected automatically, but listing them explicitly keeps policy reporting clear.

Cross-device file replacements that touch a configured NAS are copied in chunks to a temporary target and paced by the NAS transfer limit. The temporary file is renamed only after the copy succeeds. Same-volume moves remain fast metadata-only renames.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11-3.13, FastAPI, SQLAlchemy 2.0 async |
| Database | SQLite via aiosqlite; optional PostgreSQL via asyncpg |
| Real-time | python-socketio (Socket.IO) |
| Scheduling | APScheduler 3.10 |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Plex | python-plexapi |
| HTTP client | httpx (async) |
| Auth | JWT (PyJWT) + bcrypt |
| Tray | pystray + Pillow |
| Sonarr | httpx REST client (v3 API) |

---

## Architecture

```
slimarr/
|-- backend/
|   |-- api/          # FastAPI routers (library, queue, activity, settings, system, dashboard, tv)
|   |-- auth/         # JWT authentication
|   |-- core/         # Business logic (scanner, searcher, comparer, downloader, replacer, cleanup)
|   |-- integrations/ # Plex, SABnzbd, TMDB, Prowlarr, Newznab, Radarr, Sonarr clients
|   |-- realtime/     # Socket.IO instance and event emitter
|   |-- scheduler/    # APScheduler nightly job
|   `-- main.py       # App entry point, static file serving
|-- frontend/
|   `-- src/
|       |-- pages/    # Dashboard, Library, MovieDetail, Queue, Activity, Settings, System, TVShows
|       |-- components/ # PosterCard, StatCard, QualityBadge, Toast, Sidebar, Layout
|       |-- hooks/    # useSocket, useAuth, useNasPreset
|       `-- lib/      # api.ts, socket.ts, types.ts
|-- data/             # SQLite DB, MediaCover image cache, recycling bin
|-- docs/             # GitHub Pages website and Docker deployment guide
|-- images/           # Brand assets
|-- docker-compose.yml # Recommended Docker deployment template
|-- run.py            # Entry point (headless on Linux/Docker, tray on Windows)
|-- tray.py           # pystray system tray
|-- install.ps1       # One-click installer
`-- config.yaml       # User configuration
```

---

## How It Works

### 1. Library Scan
Slimarr reads every movie from your configured Plex sections via PlexAPI, upserts them into the local SQLite database, and enriches each entry with TMDB metadata (poster, backdrop, overview, genres). Progress is emitted in real time via Socket.IO.

### 2. Search
For each `pending` movie, Slimarr queries Prowlarr (or direct Newznab indexers) by IMDb ID or title. Results are parsed for resolution, codec, source, size, HDR/Dolby Vision markers, language/audio markers, subtitles, release group, and quality risk signals.

### 3. Compare
Each result is scored against the local file:
- **Reject by default** if the candidate is not smaller
- **Configurable exception** for clearly low-quality local files when the candidate is a bounded 1080p quality upgrade
- **Hard reject** if savings fall below `min_savings_percent`
- **Hard reject** if candidate falls below `minimum_file_size_mb`
- **Hard reject** if candidate has a foreign-language tag and doesn't match `preferred_language`
- **Hard reject** if Dolby Vision safety mode blocks a DV-only release
- **Hard reject** if hardcoded foreign subtitles are detected and subtitle safety is enabled
- **Configurable** resolution downgrade protection
- Score considers savings %, codec preference (AV1 > h265 > h264), source quality, media health, language/subtitle risk, uploader reliability, and title/year confidence

### Search Diagnostics and Test Harness

Slimarr v1.3 adds `/system/search-diagnostics` in the UI and `/api/v1/system/search-diagnostics` in the API. It records a bounded in-memory history of search requests and responses with secrets redacted, including provider name, request URL, HTTP status, response timing, raw and parsed counts, parser/auth/timeout failures, category warnings, rejection summaries, and last successful search.

The Search Test Harness runs a manual movie search without downloading anything or mutating library state. It shows raw payload previews, parsed releases, accepted candidates, rejected candidates, and filtering stages so support cases can answer why Slimarr accepted or rejected a release.

Known limitations: live in-memory diagnostics counters reset on restart (persisted diagnostics history remains available); raw payload previews are truncated; Media Health currently relies on parser plus best-effort MediaInfo enrichment rather than ffprobe parity.

### 4. Download
The best accepted candidate is submitted to the active download client as an NZB. Slimarr currently supports SABnzbd and NZBGet, then polls for progress and emits `download:progress` events for the live progress bar.

### 5. Replace
Once complete, the new file is moved into the exact location of the original in your Plex library. If configured, the old file is moved to the recycling bin first (using a collision-safe name); otherwise it is deleted immediately. Plex is refreshed, an activity log entry is written, and a `replace:completed` event is emitted.

> **Tip:** If your Plex server and Slimarr run on different machines (or see the same storage under different paths), configure **Path Mappings** in Settings so Slimarr can translate Plex-reported paths to locally accessible ones.

### 6. TV Show Stale Media Sweeper
The **TV Shows** page lets you explore your Plex TV library by disk usage and watch history. Slimarr surfaces shows that have never been watched (or not watched within your chosen time window) alongside their total size on disk. Nothing is automatic - you review the suggestions and choose what to delete. Deleting a show:
1. Optionally unmonitors the series in Sonarr (so it won't be automatically re-downloaded)
2. Instructs Plex to delete all associated files from disk

### 7. Duplicate File Cleanup
The System page includes a one-click **Find Duplicates** tool. Slimarr scans Plex for movies that have multiple file copies, scores them by resolution and codec quality, and deletes the inferior copies - keeping the best version.

### 8. Utilities Maintenance Intelligence
The System page now includes a **Maintenance Intelligence** panel that combines utility telemetry with health signals to provide:
- A transparent maintenance score and state
- Safe recommendations tied to observable telemetry
- Duplicate cleanup previews with reclaimable-byte estimates and confidence buckets

Duplicate cleanup now follows a safer flow:
1. Preview candidates and estimated reclaimable space
2. Review confidence and sample titles
3. Explicitly confirm cleanup before any delete/recycle action

This keeps optimization actions technically honest, non-destructive by default, and aligned with real system state.

### 9. Discovery & Recommendations
The **Discovery** page suggests titles related to what you already own - missing entries in a collection you're partway through, sequels/prequels, and related or similar titles - so you can decide what to add next. Recommendations are entirely deterministic by default: no AI is required or contacted unless you explicitly configure and enable it.

- **Sourcing** - for each owned movie with a TMDB match, Slimarr checks its collection (missing members become `collection_completion` candidates) and its related/recommended titles (`related_title` candidates), skipping anything already in Plex or already managed in Radarr/Sonarr.
- **Scoring** - every candidate gets a transparent numeric score built from named positive signals (collection completion, sequel/prequel, genre/creator affinity, popularity, streaming availability) and negative ones (wrong year/language/region, blocked keywords), each with a human-readable reason attached - never a generic "recommended for you."
- **Streaming availability** - looked up per-region via TMDB's own `/watch/providers` endpoint only. No streaming service is ever scraped or asked for credentials. Availability carries a "last checked" timestamp and is treated as time-sensitive; it is never shown as current once stale. Region must be explicitly configured - it is never assumed from IP or locale.
- **Actions, not automation** - each recommendation can be dismissed, hidden permanently, added to your watchlist, or marked as already owned. Sending a title to Radarr or Sonarr is a separate, explicit action that requires you to confirm the root folder and quality profile - Slimarr never downloads a recommended title on its own, and Radarr/Sonarr remain the system of record afterward.
- **Optional AI** - if you configure and enable an AI provider, it may only rerank the candidate list Slimarr already sourced or generate short explanations - it cannot invent titles or availability, cannot see your Plex token or file paths, and every ID it returns is re-validated against TMDB before it can appear on screen. No AI provider ships enabled or pre-configured; only Radarr/Sonarr hand-off (capability-checked against your own instance) is available at launch, and Seerr hand-off is intentionally not implemented yet - see `docs/RECOMMENDATION_INTEGRATIONS.md` for why.

See `docs/RECOMMENDATION_ARCHITECTURE.md`, `docs/RECOMMENDATION_PRIVACY.md`, and `docs/RECOMMENDATION_INTEGRATIONS.md` for full design, privacy, and integration details.

---

## Development

```powershell
# Backend (auto-reload):
.\venv\Scripts\python.exe -m uvicorn backend.main:socket_app --host 0.0.0.0 --port 9494 --reload

# Frontend (dev server with HMR):
cd frontend
npm run dev
```

The Vite dev server proxies `/api` and `/socket.io` to `localhost:9494` automatically.

---

## License

MIT - see [LICENSE](LICENSE) for details.

---

<p align="center">Built for the *arr ecosystem &nbsp;-&nbsp; Dark UI, real-time updates, one-click installs</p>
