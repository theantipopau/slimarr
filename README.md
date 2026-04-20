<p align="center">
  <img src="images/header-logo.PNG" alt="Slimarr" width="420" />
</p>

<p align="center">
  <strong>Automatically shrink your Plex library — find smaller, better-compressed releases on Usenet and replace bloated files overnight.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/fastapi-0.115-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" />
</p>

---

## What is Slimarr?

Plex libraries accumulate large files over time — bloated remuxes, old h264 Blu-ray rips, and poorly compressed encodes. Modern codecs like **h265/HEVC** and **AV1** deliver equivalent or better visual quality at a fraction of the file size.

**Slimarr automates the entire replacement workflow:**

```
Scan Plex library → Search Usenet indexers → Compare releases
→ Queue download via SABnzbd → Replace file → Refresh Plex → Log savings
```

**Core rule: never increase file size.** A release is only accepted if it is strictly smaller than your existing copy.

Slimarr is designed to look and feel like a native member of the **\*arr ecosystem** (Radarr, Sonarr, Prowlarr). If you're familiar with those tools, you'll feel right at home.

---

## Screenshots

| Dashboard | Library | Movie Detail |
|-----------|---------|--------------|
| Live savings stats, recent activity, and area chart | Poster grid with status overlays and real-time scan progress | Per-result download with quality badges and comparison scores |

| Queue | Activity | Settings |
|-------|----------|----------|
| Live download progress bars with speed and ETA | Full replacement history with savings per movie | Per-service connection testing |

---

## Features

- **Nightly automation** — scheduled cycle searches, downloads and replaces movies while you sleep
- **Usenet search** — supports Prowlarr (recommended) or direct Newznab/NZBGeek indexers
- **SABnzbd integration** — submit NZBs and monitor downloads in real time
- **Plex sync** — reads your library via PlexAPI, refreshes Plex after each replacement
- **TMDB enrichment** — posters, backdrops, and metadata fetched and cached locally
- **Smart comparison engine** — configurable minimum savings %, resolution downgrade protection, codec preferences
- **Real-time UI** — Socket.IO pushes scan progress, download progress, and replacement events to the browser instantly
- **Toast notifications** — non-intrusive feedback for every action
- **Recycling bin** — original files moved to a configurable recycle directory before replacement
- **System tray** — runs as a Windows tray app with one-click open browser
- **Activity log** — full history of every replacement with old/new size and savings %
- **Radarr-compatible feel** — sidebar nav, poster grid, quality badges, test connection buttons

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | 3.12+ | |
| Node.js | 18+ | For building the frontend |
| Plex Media Server | Any | PlexAPI token required |
| SABnzbd | Any | API key required |
| Prowlarr **or** Newznab indexer | Any | At least one required |
| TMDB API key | Free | For posters and metadata |

---

## Installation (Windows)

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

**3. Edit `config.yaml`** with your service credentials (created on first run).

**4. Start Slimarr:**
```powershell
# With system tray (Windows default):
python run.py

# Headless (no tray):
python run.py --headless

# Direct uvicorn:
.\venv\Scripts\python.exe -m uvicorn backend.main:socket_app --host 0.0.0.0 --port 9494
```

**5. Open your browser to `http://localhost:9494`** and complete the one-time registration.

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

prowlarr:
  enabled: true
  url: "http://localhost:9696"
  api_key: "your-prowlarr-api-key"

tmdb:
  api_key: "your-tmdb-api-key"

comparison:
  min_savings_percent: 10.0         # Reject candidates saving less than this
  allow_resolution_downgrade: false  # e.g. block 1080p → 720p replacements
  preferred_codecs: ["av1", "h265"]

schedule:
  start_time: "01:00"   # UTC
  end_time: "07:00"
  max_downloads_per_night: 10
  throttle_seconds: 30
```

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

---

## Architecture

```
C:\Slimarr\
├── backend/
│   ├── api/          # FastAPI routers (library, queue, activity, settings, system, dashboard)
│   ├── auth/         # JWT authentication
│   ├── core/         # Business logic (scanner, searcher, comparer, downloader, replacer)
│   ├── integrations/ # Plex, SABnzbd, TMDB, Prowlarr, Newznab clients
│   ├── realtime/     # Socket.IO instance and event emitter
│   ├── scheduler/    # APScheduler nightly job
│   └── main.py       # App entry point, static file serving
├── frontend/
│   └── src/
│       ├── pages/    # Dashboard, Library, MovieDetail, Queue, Activity, Settings, System
│       ├── components/ # PosterCard, StatCard, QualityBadge, Toast, Sidebar, Layout
│       ├── hooks/    # useSocket, useAuth
│       └── lib/      # api.ts, socket.ts, types.ts
├── data/             # SQLite DB, MediaCover image cache, recycling bin
├── images/           # Brand assets
├── run.py            # Entry point (tray or headless)
├── tray.py           # pystray system tray
├── install.ps1       # One-click installer
└── config.yaml       # User configuration
```

---

## How It Works

### 1. Library Scan
Slimarr reads every movie from your configured Plex sections via PlexAPI, upserts them into the local SQLite database, and enriches each entry with TMDB metadata (poster, backdrop, overview, genres). Progress is emitted in real time via Socket.IO.

### 2. Search
For each `pending` movie, Slimarr queries Prowlarr (or direct Newznab indexers) by IMDb ID or title. Results are parsed for resolution, codec, source, and size.

### 3. Compare
Each result is scored against the local file:
- **Hard reject** if the candidate is not smaller
- **Hard reject** if savings fall below `min_savings_percent`
- **Configurable** resolution downgrade protection
- Score considers savings %, codec preference, and release quality

### 4. Download
The best accepted candidate is submitted to SABnzbd as an NZB. Slimarr polls for progress and emits `download:progress` events for the live progress bar.

### 5. Replace
Once complete, the original file is moved to the recycling bin and the new file is moved into place. Plex is refreshed, an activity log entry is written, and a `replace:completed` event is emitted.

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

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">Built for the *arr ecosystem &nbsp;·&nbsp; Dark UI, real-time updates, one-click installs</p>
