<p align="center">
  <img src="images/header-logo.PNG" alt="Slimarr" width="420" />
</p>

<p align="center">
  <strong>Automatically shrink your Plex library - find smaller, better-compressed releases on Usenet and replace bloated files overnight.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/fastapi-0.115-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/release-1.3.0.0-success" />
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

**Core rule: save space safely.** A release is normally accepted only when it is smaller than your existing copy. In v1.3, Slimarr can make a bounded exception for clearly poor local media such as CAM/TS, weak 720p, or suspiciously low-bitrate files when the candidate is a strong 1080p quality upgrade.

Slimarr is designed to look and feel like a native member of the **\*arr ecosystem** (Radarr, Sonarr, Prowlarr). If you're familiar with those tools, you'll feel right at home.

Current release: **1.3.0.0** (2026-05-13).

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

- **Nightly automation** - scheduled cycle searches, downloads and replaces movies while you sleep
- **Usenet search** - supports Prowlarr (recommended) or direct Newznab/NZBGeek indexers
- **Download client integration** - supports SABnzbd by default, with NZBGet support on the current `main` branch
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
- **TV Show Stale Media Sweeper** - Slimarr surfaces never-watched or long-unwatched TV shows with their disk footprint so *you* can decide what to delete; optionally unmonitors in Sonarr to prevent re-download
- **System tray** - runs as a Windows tray app with one-click open browser
- **Activity log** - full history of every replacement with old/new size and savings %
- **Update checker** - System page shows a badge when a newer version is available on GitHub
- **Radarr-compatible feel** - sidebar nav, poster grid, quality badges, test connection buttons

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | 3.11 – 3.13 | **3.14 is not yet supported** — use 3.12 or 3.13 |
| Node.js | 18+ | For building the frontend |
| Plex Media Server | Any | PlexAPI token required |
| SABnzbd or NZBGet | Any | Configure at least one download client |
| Prowlarr **or** Newznab indexer | Any | At least one required |
| TMDB API key | Free | For posters and metadata |

---

## Installation (Windows)

### Option A - Installer (recommended for sharing)

Download `SlimarrSetup-1.3.0.0.exe` (or the latest `SlimarrSetup-*.exe`) from the [Releases](https://github.com/theantipopau/slimarr/releases) page and run it. The installer bundles Python and all dependencies - no manual setup required. After install, Slimarr appears in the Start Menu and optionally the system tray on login.

At the end of setup, the installer shows `Do you want to open Slimarr?` (checked by default). If selected, Slimarr starts minimized and your browser opens automatically to `http://localhost:9494` when the backend is ready.

`1.3.0.0` is the current installer target. Newer `main` branch changes may land before the next installer is cut; if you want those immediately, run Slimarr from source or build a fresh installer from `main`.

### Option B - From source

**1. Clone the repository:**
```powershell
git clone https://github.com/theantipopau/slimarr.git C:\Slimarr
cd C:\Slimarr
```

**2. Run the installer:**
```powershell
.\install.ps1
```

The installer will:
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
```

> **Note on disk space:** By default `recycling_bin` is empty, meaning old files are deleted immediately when a replacement succeeds. If you configure a recycling bin path, be aware that replaced movie files (typically 10-50 GB each) accumulate there until the nightly cleanup runs. Use a path on a drive with plenty of headroom, or leave the setting empty.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async |
| Database | SQLite via aiosqlite |
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
C:\Slimarr\
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
|       |-- hooks/    # useSocket, useAuth
|       `-- lib/      # api.ts, socket.ts, types.ts
|-- data/             # SQLite DB, MediaCover image cache, recycling bin
|-- images/           # Brand assets
|-- run.py            # Entry point (tray or headless)
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
