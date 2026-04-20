# Slimarr - Design Document

## Library Compression Optimizer for Plex Media Servers

---

## 1. Executive Summary

**Slimarr** is a self-hosted application that automatically reduces the disk footprint of a Plex media library by finding smaller, equally-or-better quality releases on Usenet and replacing oversized local files. It follows the naming conventions of the *arr ecosystem (Radarr, Sonarr, Prowlarr) and integrates with the same backend infrastructure.

**Core Principle:** Never increase file size. Only replace a file if a candidate is strictly smaller than the existing copy, regardless of whether its resolution or codec is superior.

---

## 2. Problem Statement

Over time, Plex libraries accumulate large files — old h264 Blu-ray encodes, bloated remuxes, or poorly compressed rips. Modern codecs (h265/HEVC, AV1) can deliver equivalent or better visual quality at a fraction of the size. Manually auditing hundreds of movies and searching for better-compressed alternatives is impractical.

Slimarr automates this entire workflow: scan → identify → search → compare → download → replace → log.

---

## 3. Design Philosophy — Matching the *arr Ecosystem

Slimarr is designed to **look and feel like a native member of the *arr family** (Radarr, Sonarr, Prowlarr). Users familiar with those tools should feel immediately at home.

### 3.1 Key *arr Design Principles Adopted

| Principle | How Radarr Does It | How Slimarr Does It |
|-----------|-------------------|---------------------|
| **Single-process monolith** | C#/.NET backend serves React frontend as static files — one binary, one port, one service | FastAPI backend serves the React frontend as static build output — one `python` process, one port, one service |
| **Dark cinematic UI** | Dark theme with movie posters, fanart backdrops, color-coded quality badges | Same dark theme using the *arr color palette (`#1a1d23` background, `#2a2e37` cards, `#5d9cec` accent blue) |
| **Poster-first library** | Movies displayed as a poster grid (like a streaming app), with table/list as an alternative view | Identical poster grid view for the library, plus a table view |
| **Rich movie detail pages** | Full-width fanart backdrop, poster on left, metadata + file info + history on right | Same layout, adapted to show size comparison data and replacement history |
| **Real-time updates** | SignalR (WebSocket) pushes events (download progress, scan status) to the UI instantly | `socketio` (Python SignalR equivalent) for real-time event streaming to the frontend |
| **Sidebar navigation** | Persistent left sidebar: Movies, Calendar, Activity, Settings, System | Persistent left sidebar: Dashboard, Library, Activity, Queue, Logs, Settings, System |
| **TMDB images** | Movie posters and fanart fetched from TMDB API, cached locally, proxied through backend | Same — TMDB API for posters/backdrops, backend proxy endpoint (`/api/v1/images/`) so API keys never reach the browser |
| **API-key auth + forms login** | API key for programmatic access, mandatory forms-based login for UI (Radarr v5+) | Same — JWT + session for UI login, API key header for external integrations |
| **Health checks** | System → Status page showing connection health for every integration | System page with live health checks for Plex, SABnzbd, each indexer, Radarr, Prowlarr |
| **Test connection** | Settings pages have "Test" buttons that verify API connectivity on the spot | Same — every integration settings page has a Test button with success/failure feedback |
| **Toast notifications** | Pop-up toasts for events (grab, import, error) | Same toast system for real-time event feedback |

### 3.2 TMDB Integration for Images

Radarr's visual richness comes from **The Movie Database (TMDB)**. Slimarr uses TMDB identically:

| Image Type | TMDB Endpoint | Usage in Slimarr |
|------------|--------------|------------------|
| **Poster** (300×450) | `https://image.tmdb.org/t/p/w300/{poster_path}` | Library grid, movie cards, search results |
| **Backdrop/Fanart** (1280×720) | `https://image.tmdb.org/t/p/w1280/{backdrop_path}` | Movie detail page header, dashboard featured movie |
| **Poster HD** (500×750) | `https://image.tmdb.org/t/p/w500/{poster_path}` | Movie detail page sidebar |

**Image Proxy Pattern (matching Radarr's `/api/v3/mediacover/`):**
```
Browser → GET /api/v1/images/{movie_id}/poster.jpg
         → Slimarr backend checks local cache
         → If not cached: fetches from TMDB, caches to disk, returns image
         → If cached: returns from disk immediately

Cache location: data/MediaCover/{movie_id}/
  ├── poster.jpg
  ├── poster-500.jpg
  └── fanart.jpg
```

This means:
- TMDB API key is **never exposed** to the browser
- Images are **cached locally** — no repeated TMDB calls
- Works identically to Radarr's `MediaCover` endpoint
- TMDB metadata (title, year, overview, genres, cast) is fetched on first scan and stored in the database

### 3.3 Real-Time Communication (SignalR Pattern)

Radarr uses **SignalR** (Microsoft's WebSocket abstraction) to push live events to the UI. Slimarr replicates this with **Socket.IO** (the Python ecosystem equivalent):

```
Backend Events                          Frontend Handlers
─────────────────                       ──────────────────
scan:started     ───WebSocket───►      Update library progress bar
scan:movie       ───WebSocket───►      Flash movie card in library
search:results   ───WebSocket───►      Update candidate count badge
download:progress───WebSocket───►      Animate progress bar (%, speed, ETA)
download:complete───WebSocket───►      Show toast notification
replace:complete ───WebSocket───►      Update movie card (new size, badge)
system:health    ───WebSocket───►      Update health indicators
queue:update     ───WebSocket───►      Refresh queue panel
```

The frontend subscribes on page load and receives all events. No polling. Just like Radarr.

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SLIMARR (Single Process)                     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 FastAPI HTTP Server                        │  │
│  │                                                           │  │
│  │  /api/v1/*    → REST API (JSON)                           │  │
│  │  /api/v1/images/* → Image proxy (TMDB cache)              │  │
│  │  /ws          → Socket.IO (real-time events)              │  │
│  │  /*           → React SPA (static files)                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐         │
│  │Scheduler│ │ Scanner  │ │ Searcher  │ │ Comparer  │         │
│  │ (APSch) │ │  Module  │ │  Module   │ │  Module   │         │
│  └────┬────┘ └────┬─────┘ └─────┬─────┘ └─────┬─────┘         │
│       │           │             │              │               │
│  ┌────▼───────────▼─────────────▼──────────────▼────────────┐  │
│  │              Orchestrator / Job Queue                     │  │
│  │          (one-at-a-time sequential processing)            │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│  ┌────────────┐ ┌───────────▼──────────┐ ┌────────────────┐   │
│  │  Logger    │ │  Download Manager    │ │  File Replacer │   │
│  │ (SQLite)   │ │                      │ │                │   │
│  └────────────┘ └──────────────────────┘ └────────────────┘   │
│  ┌────────────┐ ┌──────────────────────┐                      │
│  │  TMDB      │ │  Image Cache         │                      │
│  │  Client    │ │  (MediaCover/)       │                      │
│  └────────────┘ └──────────────────────┘                      │
└──────────┬──────────┬───────────┬──────────┬──────────────────┘
           │          │           │          │
      ┌────▼───┐ ┌────▼────┐ ┌───▼───┐ ┌───▼────────┐ ┌────────┐
      │  Plex  │ │Prowlarr │ │SABnzbd│ │  Radarr    │ │  TMDB  │
      │  API   │ │/Newznab │ │/NZBGet│ │  (optional)│ │  API   │
      └────────┘ └─────────┘ └───────┘ └────────────┘ └────────┘
```

**Key architectural point:** Like Radarr, Slimarr is a **single process** that serves everything — the API, the WebSocket events, the image proxy, and the frontend UI — all on one port (default `9494`). No separate frontend server. The React app is built to static files and served by FastAPI.

---

## 4. Core Workflow (Per Movie)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SCAN: Read movie from Plex library                       │
│    → Get title, year, TMDB/IMDB ID, file path              │
│    → Probe local file: size, resolution, codec, bitrate     │
├─────────────────────────────────────────────────────────────┤
│ 2. SEARCH: Query Usenet indexers via Newznab/Prowlarr API   │
│    → Search by IMDB ID (preferred) or title+year            │
│    → Collect all available NZBs with metadata               │
├─────────────────────────────────────────────────────────────┤
│ 3. COMPARE: Filter and rank candidates                      │
│    → REJECT if candidate size >= local file size            │
│    → REJECT if candidate resolution < local resolution      │
│      (unless size saving is massive and user allows it)     │
│    → RANK by: size savings, codec efficiency, resolution    │
│    → SELECT best candidate (smallest that meets criteria)   │
├─────────────────────────────────────────────────────────────┤
│ 4. DECISION: Download or Skip                               │
│    → If no better candidate found → LOG as "Optimal" → NEXT│
│    → If better candidate found → proceed to download        │
├─────────────────────────────────────────────────────────────┤
│ 5. DOWNLOAD: Send NZB to SABnzbd via API                    │
│    → Monitor download progress                              │
│    → Wait for completion + post-processing                  │
├─────────────────────────────────────────────────────────────┤
│ 6. REPLACE: Swap files                                      │
│    → Verify downloaded file is valid (not corrupt)          │
│    → Move old file to recycling bin (configurable)          │
│    → Move new file into Plex library path                   │
│    → Trigger Plex library scan for that section             │
│    → Update Radarr if integrated (optional)                 │
├─────────────────────────────────────────────────────────────┤
│ 7. LOG: Record everything                                   │
│    → Movie title, old size, new size, savings               │
│    → Codec/resolution changes                               │
│    → Timestamp, status, any errors                          │
├─────────────────────────────────────────────────────────────┤
│ 8. NEXT: Move to next movie in the queue                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. External API Integrations

### 5.1 Plex Media Server API

**Purpose:** Read the movie library, get file paths, media metadata.

| Aspect | Detail |
|--------|--------|
| **Library** | `python-plexapi` (PyPI package) |
| **Auth** | Plex Token (from Plex account or server settings) |
| **Key Endpoints** | `GET /library/sections` — list libraries |
| | `GET /library/sections/{id}/all` — list all movies in a section |
| | Each movie object contains `media` → `part` → `file` (full file path) |
| | Media info includes: `videoResolution`, `videoCodec`, `bitrate`, `width`, `height`, `container` |
| **Connection** | Direct HTTP to Plex server (e.g., `http://localhost:32400`) |

**Example Flow:**
```python
from plexapi.server import PlexServer
plex = PlexServer('http://localhost:32400', 'YOUR_PLEX_TOKEN')
movies = plex.library.section('Movies')
for movie in movies.all():
    for media in movie.media:
        for part in media.parts:
            print(f"{movie.title} ({movie.year})")
            print(f"  File: {part.file}")
            print(f"  Size: {part.size} bytes")
            print(f"  Resolution: {media.videoResolution}")
            print(f"  Codec: {media.videoCodec}")
            print(f"  Bitrate: {media.bitrate} kbps")
```

### 5.2 Usenet Indexers (Newznab API)

**Purpose:** Search for NZB releases matching each movie.

**How Radarr/Sonarr Do It:**
The *arr apps use the **Newznab** protocol — an XML/JSON API standard supported by most Usenet indexers (NZBgeek, DrunkenSlug, NZBFinder, etc.). Prowlarr acts as a unified proxy for all indexers.

| Aspect | Detail |
|--------|--------|
| **Protocol** | Newznab API (standardized REST API) |
| **Auth** | API Key per indexer |
| **Search Endpoint** | `GET {indexer_url}/api?t=movie&imdbid={imdb_id}&apikey={key}` |
| **Alternative** | `GET {indexer_url}/api?t=search&q={movie+title+year}&cat=2000&apikey={key}` |
| **Category 2000** | Movies (Newznab standard category) |
| **Response** | XML/RSS feed with `<item>` elements containing: title, size, link (NZB URL), category, IMDB ID, grabs count |
| **Size Info** | `<enclosure length="3758096384"/>` (size in bytes) |
| **Attributes** | `<newznab:attr name="size" value="..."/>` |
| | `<newznab:attr name="imdb" value="..."/>` |
| | `<newznab:attr name="resolution" value="1080"/>` |

**Option A — Direct Indexer Queries (Recommended for simplicity):**
```
GET https://api.nzbgeek.info/api?t=movie&imdbid=tt0114709&apikey=YOUR_KEY
```
Returns XML with all available releases for Toy Story.

**Option B — Via Prowlarr (Recommended for multi-indexer):**
Prowlarr aggregates multiple indexers behind a single Newznab-compatible endpoint. Radarr and Sonarr connect to Prowlarr this way. Slimarr can do the same:
```
GET http://localhost:9696/1/api?t=movie&imdbid=tt0114709&apikey=PROWLARR_KEY
```

**Option C — Via Radarr API (Leverage existing setup):**
If the user already has Radarr configured with indexers, Slimarr can query Radarr's release endpoint:
```
GET http://localhost:7878/api/v3/release?movieId={id}
Headers: X-Api-Key: RADARR_API_KEY
```
This returns all releases Radarr finds across all configured indexers, complete with size, quality, codec parsing.

### 5.3 SABnzbd Download Client

**Purpose:** Download NZB files from Usenet.

| Aspect | Detail |
|--------|--------|
| **API** | REST API with JSON responses |
| **Auth** | API Key |
| **Base URL** | `http://localhost:8080/api` |
| **Add Download** | `GET /api?mode=addurl&name={nzb_url}&cat=slimarr&apikey={key}` |
| **Check Status** | `GET /api?mode=queue&apikey={key}` — active downloads |
| **History** | `GET /api?mode=history&apikey={key}` — completed downloads |
| **Key Fields** | `nzo_id` — unique job identifier |
| | `status` — Downloading, Completed, Failed |
| | `storage` — final file path after completion |

**Download Flow:**
1. Send NZB URL to SABnzbd with category `slimarr`
2. Poll queue status until job completes
3. Read `storage` path from history to find the downloaded file
4. Verify the file, then proceed to replacement

**NZBGet Alternative:**
NZBGet uses a JSON-RPC API at `http://host:6789/jsonrpc`:
```json
{
    "method": "append",
    "params": ["filename.nzb", "nzb_content_base64", "slimarr", 0, false, false, "", 0, "SCORE"]
}
```

### 5.4 Radarr Integration (Optional)

**Purpose:** Leverage existing movie metadata, indexer configs, and library management.

| Aspect | Detail |
|--------|--------|
| **API** | REST v3, JSON |
| **Auth** | `X-Api-Key` header |
| **List Movies** | `GET /api/v3/movie` — all movies with file info |
| **Movie Detail** | `GET /api/v3/movie/{id}` — includes `movieFile` with size, quality, mediaInfo |
| **Search Releases** | `GET /api/v3/release?movieId={id}` — search all indexers |
| **Manual Import** | `POST /api/v3/command` with `ManualImport` body |
| **Rescan** | `POST /api/v3/command` with `RescanMovie` body |

**Key Radarr Data Per Movie:**
```json
{
    "title": "Toy Story",
    "year": 1995,
    "imdbId": "tt0114709",
    "tmdbId": 862,
    "movieFile": {
        "size": 5905580032,
        "quality": { "quality": { "name": "Bluray-1080p" } },
        "mediaInfo": {
            "videoCodec": "h264",
            "videoBitrate": 8500000,
            "audioCodec": "DTS",
            "resolution": "1920x1080"
        },
        "path": "T:\\Movies\\Toy Story (1995)\\Toy Story (1995) Bluray-1080p.mkv"
    }
}
```

### 5.5 Prowlarr Integration (Optional, Recommended)

**Purpose:** Unified indexer management — search all Usenet indexers through one API.

| Aspect | Detail |
|--------|--------|
| **API** | Newznab-compatible per indexer, plus native REST API |
| **Sync** | Auto-syncs indexer configs to Radarr/Sonarr |
| **Search** | `GET /api/v1/search?query={term}&type=movie&categories=2000` |
| **Benefits** | Single config point for all indexers; handles rate limiting; tracks stats |

---

## 6. Release Parsing & Comparison Engine

### 6.1 Parsing Release Names

Following Radarr's approach, release names encode quality information:

```
Toy.Story.1995.2160p.UHD.BluRay.x265.HDR.DTS-HD.MA.7.1-GROUP
│         │    │     │        │    │         │          │
│         │    │     │        │    │         │          └─ Release Group
│         │    │     │        │    │         └─ Audio Codec + Channels
│         │    │     │        │    └─ HDR type
│         │    │     │        └─ Video Codec
│         │    │     └─ Source (BluRay, WEB-DL, WEBRip, HDTV)
│         │    └─ Resolution (2160p, 1080p, 720p, 480p)
│         └─ Year
└─ Title
```

**Parser extracts:**
- **Resolution:** 2160p, 1080p, 720p, 480p
- **Video Codec:** x264/h264, x265/h265/HEVC, AV1, VP9, MPEG2, XviD
- **Audio Codec:** DTS-HD MA, TrueHD, Atmos, DTS, DD5.1, AAC, FLAC
- **Source:** BluRay, Remux, WEB-DL, WEBRip, HDTV, DVDRip
- **HDR:** HDR10, HDR10+, Dolby Vision, HLG, SDR
- **Size:** From the Newznab `<enclosure length>` attribute (in bytes)

### 6.2 Comparison Algorithm

```
FUNCTION compare(local_file, candidate_release):

    # HARD RULE: Never increase size
    IF candidate.size >= local_file.size:
        RETURN REJECT("Candidate is not smaller")

    # Calculate savings
    savings_bytes = local_file.size - candidate.size
    savings_pct = (savings_bytes / local_file.size) * 100

    # Minimum savings threshold (configurable, default 10%)
    IF savings_pct < config.min_savings_percent:
        RETURN REJECT("Savings below threshold")

    # Resolution check
    IF candidate.resolution < local_file.resolution:
        IF NOT config.allow_resolution_downgrade:
            RETURN REJECT("Lower resolution")
        # If allowed, require significant savings (e.g., 40%+)
        IF savings_pct < config.downgrade_min_savings:
            RETURN REJECT("Insufficient savings for downgrade")

    # Codec efficiency scoring
    codec_score = {
        'av1': 100, 'h265': 80, 'hevc': 80, 'x265': 80,
        'h264': 50, 'x264': 50,
        'mpeg2': 20, 'xvid': 10
    }

    # Higher resolution at smaller size = bonus (e.g., 4K AV1 < 1080p h264)
    IF candidate.resolution > local_file.resolution:
        score_bonus = 20  # Resolution upgrade bonus

    # Compile score
    score = savings_pct
          + codec_score.get(candidate.codec, 0)
          - codec_score.get(local_file.codec, 0)
          + score_bonus

    RETURN ACCEPT(score, savings_bytes, savings_pct)
```

### 6.3 Decision Examples

| Local File | Candidate | Size | Decision |
|-----------|-----------|------|----------|
| Toy Story 1080p h264 — 5.5 GB | 2160p AV1 — 3.5 GB | -36% | **REPLACE** (4K upgrade + smaller) |
| Toy Story 1080p h264 — 5.5 GB | 1080p h265 — 2.5 GB | -55% | **REPLACE** (same res, better codec, much smaller) |
| Toy Story 1080p h264 — 5.5 GB | 1080p h264 — 5.2 GB | -5% | **SKIP** (below 10% threshold) |
| Toy Story 1080p h264 — 5.5 GB | 720p h265 — 1.8 GB | -67% | **SKIP** (resolution downgrade, unless allowed) |
| Toy Story 1080p h264 — 5.5 GB | 1080p h264 — 6.1 GB | +11% | **REJECT** (larger file) |
| Toy Story 1080p h264 — 5.5 GB | 2160p Remux — 45 GB | +718% | **REJECT** (much larger) |

---

## 7. Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend** | Python 3.12+ / FastAPI | Async-first, excellent for API integrations, rich ecosystem |
| **Task Queue** | APScheduler + asyncio | Lightweight scheduling, no Redis dependency needed |
| **Database** | SQLite (via SQLAlchemy) | Zero-config, file-based, perfect for single-server app |
| **Frontend** | React 18 + TypeScript + Vite | Built to static files, served by FastAPI (single process, like Radarr) |
| **UI Styling** | Tailwind CSS + shadcn/ui | Polished component library, dark mode, *arr color palette |
| **Charts** | Recharts | Area charts for savings over time, bar charts for size comparisons |
| **Real-time** | python-socketio + Socket.IO client | SignalR equivalent for Python — real-time event push |
| **Auth** | JWT tokens + bcrypt | Secure session management, plus API key header support |
| **Plex Client** | `python-plexapi` | Official Python bindings for Plex |
| **TMDB Client** | `httpx` + TMDB API v3 | Movie posters, backdrops, metadata (requires free API key) |
| **Media Probe** | `pymediainfo` or `ffprobe` | Detailed codec/bitrate analysis of local files |
| **NZB Parsing** | Custom XML parser | Parse Newznab API responses |
| **Image Cache** | Disk cache (`data/MediaCover/`) | Local cache of TMDB images, proxied through backend |
| **Installer** | NSSM / Windows Service | Run as Windows service, auto-start on boot |
| **Packaging** | PyInstaller or Docker | Easy deployment |

> **Why not Next.js?** Radarr/Sonarr serve the frontend as static files from the backend — no separate Node.js server. Slimarr follows this pattern: Vite builds the React app to `frontend/dist/`, and FastAPI serves those files on `/`. One process, one port, zero Node.js in production.

---

## 8. Database Schema

```sql
-- Core tables

CREATE TABLE movies (
    id              INTEGER PRIMARY KEY,
    plex_rating_key TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    year            INTEGER,
    imdb_id         TEXT,
    tmdb_id         INTEGER,
    -- TMDB metadata (for rich UI display)
    overview        TEXT,              -- movie synopsis
    poster_path     TEXT,              -- TMDB poster path (e.g., "/abc123.jpg")
    backdrop_path   TEXT,              -- TMDB backdrop/fanart path
    genres          TEXT,              -- JSON array of genre names
    -- File info
    file_path       TEXT,
    file_size       INTEGER,           -- bytes
    resolution      TEXT,              -- e.g., "1080p"
    video_codec     TEXT,              -- e.g., "h264"
    audio_codec     TEXT,
    bitrate         INTEGER,           -- kbps
    last_scanned    DATETIME,
    last_searched   DATETIME,
    status          TEXT DEFAULT 'pending',  -- pending, optimal, replaced, error
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE search_results (
    id              INTEGER PRIMARY KEY,
    movie_id        INTEGER REFERENCES movies(id),
    indexer_name    TEXT,
    release_title   TEXT,
    nzb_url         TEXT,
    size            INTEGER,           -- bytes
    resolution      TEXT,
    video_codec     TEXT,
    audio_codec     TEXT,
    source          TEXT,              -- BluRay, WEB-DL, etc.
    savings_bytes   INTEGER,
    savings_pct     REAL,
    score           REAL,
    decision        TEXT,              -- accept, reject
    reject_reason   TEXT,
    searched_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE downloads (
    id              INTEGER PRIMARY KEY,
    movie_id        INTEGER REFERENCES movies(id),
    search_result_id INTEGER REFERENCES search_results(id),
    sabnzbd_nzo_id  TEXT,
    status          TEXT,              -- queued, downloading, completed, failed, replaced
    old_file_path   TEXT,
    old_file_size   INTEGER,
    new_file_path   TEXT,
    new_file_size   INTEGER,
    savings_bytes   INTEGER,
    started_at      DATETIME,
    completed_at    DATETIME
);

CREATE TABLE activity_log (
    id              INTEGER PRIMARY KEY,
    movie_id        INTEGER REFERENCES movies(id),
    action          TEXT NOT NULL,     -- scanned, searched, skipped, downloaded, replaced, error
    detail          TEXT,              -- Human-readable description
    old_size        INTEGER,
    new_size        INTEGER,
    savings_bytes   INTEGER,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id              INTEGER PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. Web UI Design (Matching the *arr Visual Language)

The UI is a **pixel-perfect homage** to the Radarr/Sonarr interface. Users familiar with those tools should recognize every pattern: the dark theme, the sidebar, the poster grid, the movie detail pages, the quality badges, and the settings layout.

### 9.1 Brand Assets & Color Palette

**Logo files** (located in `/images/`):
- `header-logo.PNG` — Full logo with icon + "Slimarr" text (for sidebar header, login page)
- `icon.PNG` — Icon only: film reel with green download arrow (for favicon, system tray, mobile)

**Brand colors** (derived from the logo):
```
Slimarr Green:     #4CAF50  ("Slim" text color, download arrow, success states)
Slimarr Dark Blue: #1B3A5C  (film reel dark, sidebar background)
Slimarr Blue:      #2196F3  (film reel accent, links, active nav items)
```

**Full UI palette** (dark theme, *arr-style, but tinted with Slimarr brand):
```
Background:        #1a1d23  (deep charcoal — page background)
Surface/Card:      #272b33  (slightly lighter — card/panel backgrounds)
Sidebar:           #1B2838  (dark blue-tinted — matches logo's dark blue)
Sidebar Active:    #253447  (lighter blue tint for active nav item)
Accent Green:      #4CAF50  (primary action buttons, success, the Slimarr brand green)
Accent Blue:       #2196F3  (links, secondary actions, matches logo's blue curve)
Success Green:     #4CAF50  (optimal, completed, replaced — same as brand green)
Warning Amber:     #f0ad4e  (pending, downloading)
Danger Red:        #f05050  (error, failed, health issues)
Text Primary:      #E0E0E0  (light gray, main text)
Text Secondary:    #8e8e8e  (muted labels)
Badge Background:  #35394a  (quality/codec pills)
Border:            #2a2e37  (subtle borders between sections)
```

### 9.2 Sidebar Navigation (Radarr Layout)

```
┌────────────┬──────────────────────────────────────────────────┐
│            │                                                  │
│  SLIMARR   │  (page content)                                  │
│  ────────  │                                                  │
│            │                                                  │
│  ◉ Dashboard                                                  │
│  ☐ Library │                                                  │
│  ☐ Activity│                                                  │
│  ☐ Queue   │                                                  │
│            │                                                  │
│  ────────  │                                                  │
│  ☐ Settings│                                                  │
│  ☐ System  │                                                  │
│            │                                                  │
│  ────────  │                                                  │
│  v0.1.0    │                                                  │
└────────────┴──────────────────────────────────────────────────┘
```

Sidebar items match the Radarr grouping:
- **Top group:** Dashboard, Library, Activity, Queue (daily-use pages)
- **Bottom group:** Settings, System (configuration, separated by a divider)
- **Version badge** at the very bottom (like Radarr shows its version)

### 9.3 Dashboard Page

The dashboard is the landing page. It shows at-a-glance stats and current activity:

```
┌────────────┬──────────────────────────────────────────────────────┐
│            │  Dashboard                                           │
│  SLIMARR   │                                                      │
│  ────────  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐  │
│            │  │ 847     │ │ 312     │ │ 23      │ │ 1.24 TB   │  │
│  ◉ Dash    │  │ Movies  │ │ Optimal │ │Replaced │ │ Saved     │  │
│  ☐ Library │  └─────────┘ └─────────┘ └─────────┘ └───────────┘  │
│  ☐ Active  │                                                      │
│  ☐ Queue   │  ┌─────────────────────────────────────────────────┐  │
│            │  │  Space Savings Over Time (area chart)            │  │
│  ────────  │  │                                                 │  │
│  ☐ Settings│  │  [Jan] [Feb] [Mar] [Apr] [May] [Jun]            │  │
│  ☐ System  │  │   40GB  220GB 480GB 720GB  1.0TB  1.24TB       │  │
│            │  └─────────────────────────────────────────────────┘  │
│  v0.1.0    │                                                      │
│            │  ┌──────────────────────┐ ┌──────────────────────┐   │
│            │  │ Currently Processing │ │ Recent Activity      │   │
│            │  │                      │ │                      │   │
│            │  │  Toy Story (1995)    │ │ The Matrix           │   │
│            │  │ Searching indexers.. │ │    8.2GB > 3.1GB     │   │
│            │  │ ████████░░ 80%       │ │ Inception            │   │
│            │  │                      │ │    Optimal            │   │
│            │  │ Up next:             │ │ Interstellar         │   │
│            │  │ Fight Club (1999)    │ │    Downloading 45%    │   │
│            │  └──────────────────────┘ └──────────────────────┘   │
└────────────┴──────────────────────────────────────────────────────┘
```

### 9.4 Library Page — Poster Grid View (Key *arr Pattern)

This is the most important visual element. Like Radarr, the default library view is a **poster grid**, not a table. Each movie is a card with:

```
┌────────────┬──────────────────────────────────────────────────────┐
│            │  Library                    [Filter] [Grid|Table]    │
│  SLIMARR   │                                                      │
│            │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  │
│  ◉ Library │  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │
│            │  │▓POST▓│  │▓POST▓│  │▓POST▓│  │▓POST▓│  │▓POST▓│  │
│            │  │▓ ER ▓│  │▓ ER ▓│  │▓ ER ▓│  │▓ ER ▓│  │▓ ER ▓│  │
│            │  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │
│            │  │Matrix │  │Incep- │  │Inter- │  │Fight  │  │Glad-  │  │
│            │  │(1999) │  │tion   │  │stellar│  │Club   │  │iator  │  │
│            │  │[H265] │  │[H264] │  │[H265] │  │[H264] │  │[H265] │  │
│            │  │ 3.1GB │  │ 12GB  │  │ 5.2GB │  │ 8.4GB │  │ 4.1GB │  │
│            │  │ -62%  │  │ Pend  │  │ -48%  │  │ Err   │  │ -35%  │  │
│            │  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  │
│            │                                                      │
│            │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  │
│            │  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │▓▓▓▓▓▓│  │
│            │  │...   │  │...   │  │...   │  │...   │  │...   │  │
│            │  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  │
└────────────┴──────────────────────────────────────────────────────┘
```

**Each poster card contains:**
- Movie poster image (from TMDB, proxied through backend)
- Movie title + year
- **Quality badge** — color-coded pill: `H265` (green), `H264` (amber), `AV1` (blue), `REMUX` (purple)
- Current file size
- **Status bar** at bottom:
  - Green = Optimal (no smaller found or already replaced)
  - Amber = Pending (smaller candidate exists, awaiting download)
  - Blue = Downloading (in progress)
  - Red = Error (search failed, download failed)
  - Gray = Not yet scanned

**Filter bar** (matching Radarr's filter bar):
- Filter by status: All | Optimal | Has Savings | Pending | Error
- Sort by: Title | Size | Potential Savings | Date Added | Date Replaced
- Search by movie name
- Toggle: Grid View | Table View

### 9.5 Movie Detail Page (Radarr's Most Distinctive Feature)

Clicking a movie in the poster grid opens the detail page. This matches Radarr's cinematic layout:

```
┌────────────┬──────────────────────────────────────────────────────────┐
│            │ ╔══════════════════════════════════════════════════════╗  │
│  SLIMARR   │ ║  ░░░░░░░░░░ BACKDROP / FANART IMAGE ░░░░░░░░░░░   ║  │
│            │ ║  ░░░░░░░░░░░░░░░ (from TMDB) ░░░░░░░░░░░░░░░░░░   ║  │
│            │ ╚══════════════════════════════════════════════════════╝  │
│            │                                                          │
│            │  ┌──────┐   The Matrix (1999)                            │
│            │  │▓▓▓▓▓▓│   ──────────────────                          │
│            │  │▓POST▓│   [H265 1080p] [WEB-DL] [Bluray]              │
│            │  │▓ ER ▓│                                                │
│            │  │▓▓▓▓▓▓│   Overview:                                    │
│            │  │▓▓▓▓▓▓│   A computer hacker learns from mysterious     │
│            │  │▓▓▓▓▓▓│   rebels about the true nature of his          │
│            │  └──────┘   reality and his role in the war against      │
│            │             its controllers.                             │
│            │                                                          │
│            │  ┌─────────────────────────────────────────────────────┐  │
│            │  │  FILE INFO                                          │  │
│            │  │                                                     │  │
│            │  │  Path:       /media/movies/The Matrix (1999)/       │  │
│            │  │              The.Matrix.1999.1080p.WEB-DL.H265.mkv  │  │
│            │  │  Size:       3.14 GB                                │  │
│            │  │  Video:      H265 (HEVC) - 1080p - 4,231 kbps      │  │
│            │  │  Audio:      AAC 5.1 - 384 kbps                    │  │
│            │  │  Original:   8.2 GB (H264 Blu-ray)                 │  │
│            │  │  Savings:    5.06 GB (62% reduction)                │  │
│            │  └─────────────────────────────────────────────────────┘  │
│            │                                                          │
│            │  ┌─────────────────────────────────────────────────────┐  │
│            │  │  HISTORY                                 [Search]   │  │
│            │  │                                                     │  │
│            │  │  2024-01-15 03:22  Replaced file (8.2GB > 3.1GB)   │  │
│            │  │  2024-01-15 03:10  Download complete                │  │
│            │  │  2024-01-15 02:45  Grabbed NZB from NZBgeek        │  │
│            │  │  2024-01-15 02:44  Found 4 candidates, best: 3.1GB │  │
│            │  │  2024-01-15 02:42  Searched 3 indexers              │  │
│            │  │  2024-01-14 01:00  Initial scan: 8.2GB, H264       │  │
│            │  └─────────────────────────────────────────────────────┘  │
│            │                                                          │
│            │  ┌─────────────────────────────────────────────────────┐  │
│            │  │  SEARCH RESULTS (last search: 4 candidates)         │  │
│            │  │                                                     │  │
│            │  │  The.Matrix.1999.1080p.WEB-DL.H265       3.1GB     │  │
│            │  │    The.Matrix.1999.1080p.BluRay.H264     6.8GB     │  │
│            │  │    The.Matrix.1999.2160p.WEB-DL.H265     9.2GB     │  │
│            │  │    The.Matrix.1999.720p.WEB-DL.H265      1.8GB     │  │
│            │  └─────────────────────────────────────────────────────┘  │
└────────────┴──────────────────────────────────────────────────────────┘
```

**Key movie detail elements:**
- **Fanart backdrop** — full-width TMDB backdrop at top with gradient overlay (like Radarr)
- **Poster** — left sidebar (from TMDB)
- **Quality badges** — colored pills showing codec, resolution, source (matching Radarr's badge style)
- **File info panel** — path, size, codec details, bitrate
- **Size comparison** — old vs. new size, percentage savings (unique to Slimarr)
- **History timeline** — every action taken on this movie, chronological (same as Radarr's history tab)
- **Search results** — last indexer search results with size + acceptability status
- **Manual search button** — trigger an on-demand indexer search (like Radarr's interactive search)

### 9.6 Quality Badges (Matching Radarr's Visual Language)

Radarr displays quality info as color-coded rounded "pills". Slimarr does the same:

| Badge | Color | Background | Examples |
|-------|-------|------------|----------|
| **Codec** | White text | `#35394a` | `H265` `H264` `AV1` `MPEG4` |
| **Resolution** | White text | `#35394a` | `2160p` `1080p` `720p` `480p` |
| **Source** | White text | `#35394a` | `Bluray` `WEB-DL` `WEBRip` `HDTV` `REMUX` |
| **Status: Optimal** | White text | `#27c24c` (green) | `Optimal` `Replaced -62%` |
| **Status: Pending** | White text | `#f0ad4e` (amber) | `Pending` `Savings Available` |
| **Status: Error** | White text | `#f05050` (red) | `Error` `Search Failed` |

### 9.7 Settings Pages (Matching Radarr's Settings Layout)

Settings are organized into sub-pages with a **horizontal tab bar** (like Radarr):

```
Settings
──────────────────────────────────────────────────
[Connections] [Indexers] [Download Client] [General] [UI]
──────────────────────────────────────────────────

┌─────────────────────────────────────────────────┐
│  Plex Connection                                │
│                                                 │
│  URL:    [http://localhost:32400    ]            │
│  Token:  [****                     ]            │
│  Library:[Movies                   ]            │
│                                                 │
│         [Test Connection]  [Save]               │
│                                                 │
│  Status: Connected — 847 movies found           │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Radarr Connection (Optional)                   │
│                                                 │
│  URL:    [http://localhost:7878     ]            │
│  API Key:[****                     ]            │
│                                                 │
│         [Test Connection]  [Save]               │
│                                                 │
│  Status: Connected — Radarr v5.3.6              │
└─────────────────────────────────────────────────┘
```

Each integration has:
- Input fields for URL, API key, token
- **"Test Connection" button** that verifies connectivity and returns status (like Radarr)
- Save button
- Live status indicator (green check / red X)

### 9.8 System Page (Matching Radarr's System > Status)

```
System
──────────────────────────────────────────────────
[Status] [Health] [Tasks] [Backup] [About]
──────────────────────────────────────────────────

Health Checks:
  Plex — Connected (847 movies)
  SABnzbd — Connected (v4.2.1, 2 slots free)
  NZBgeek — Connected (47 API calls remaining)
  DrunkenSlug — Slow response (3.2s)
  TMDB — Connected (cached 847 posters)
  NZBFinder — Connection refused (check URL)

Scheduled Tasks:
  Nightly Scan      01:00 daily     Last run: 6h ago   [Run Now]
  TMDB Refresh      Weekly Sunday   Last run: 3d ago   [Run Now]
  Backup            Weekly Monday   Last run: 4d ago   [Run Now]
```

### 9.9 Visual Design Summary

| Element | Implementation |
|---------|---------------|
| **Framework** | React 18 + TypeScript (built to static files, served by FastAPI) |
| **Styling** | TailwindCSS with custom *arr color palette |
| **Charts** | Recharts (area chart for savings over time, bar charts for size comparison) |
| **Poster images** | TMDB via backend proxy, lazy-loaded, with skeleton placeholders |
| **Quality badges** | React components matching Radarr's rounded pill style |
| **Toasts** | React-Hot-Toast for real-time event notifications |
| **Real-time** | Socket.IO client for live updates (no polling) |
| **Responsive** | Mobile-friendly sidebar collapses to hamburger menu |
| **Loading states** | Skeleton loaders on poster grid (like Radarr) |
| **Transitions** | CSS transitions on hover (poster card lift effect, badge glow) |

---

## 10. Scheduling & Operation Modes

### 10.1 Night Mode (Default)

```yaml
schedule:
  mode: "nightly"
  start_time: "01:00"        # 1 AM
  end_time: "07:00"          # 7 AM
  days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
  max_downloads_per_night: 10
  bandwidth_limit: null       # use full speed at night
```

**Behavior:**
1. At 1:00 AM, Slimarr wakes up
2. Picks the next unprocessed movie from the queue
3. Scans → Searches → Compares → Downloads (if needed)
4. Waits for download completion
5. Replaces file, logs result
6. Moves to next movie
7. Stops at 7:00 AM or when all movies processed

### 10.2 Continuous Mode (Force)

```yaml
schedule:
  mode: "continuous"
  throttle_seconds: 30       # pause between movies to avoid hammering indexers
  bandwidth_limit: "50%"     # don't saturate the connection during the day
```

**Behavior:** Processes movies non-stop until the entire library is reviewed. Toggleable from the Web UI.

### 10.3 Manual Mode

Trigger processing for a specific movie or batch from the Web UI. Useful for testing or priority items.

---

## 11. Configuration

### 11.1 Settings (stored in database + config file)

```yaml
# config.yaml

# Plex
plex:
  url: "http://localhost:32400"
  token: "YOUR_PLEX_TOKEN"
  library_sections: ["Movies"]          # which Plex libraries to scan

# Download Client
sabnzbd:
  url: "http://localhost:8080"
  api_key: "YOUR_SAB_API_KEY"
  category: "slimarr"                   # dedicated category for Slimarr downloads

# Indexers (direct Newznab — or use Prowlarr)
indexers:
  - name: "NZBgeek"
    url: "https://api.nzbgeek.info"
    api_key: "YOUR_KEY"
    categories: [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060]
  - name: "DrunkenSlug"
    url: "https://api.drunkenslug.com"
    api_key: "YOUR_KEY"

# Prowlarr (alternative to direct indexers)
prowlarr:
  enabled: false
  url: "http://localhost:9696"
  api_key: "YOUR_PROWLARR_KEY"

# Radarr (optional, for metadata enrichment)
radarr:
  enabled: false
  url: "http://localhost:7878"
  api_key: "YOUR_RADARR_KEY"

# TMDB (for movie posters, backdrops, and metadata)
tmdb:
  api_key: "YOUR_TMDB_API_KEY"         # free at https://www.themoviedb.org/settings/api
  language: "en-US"                     # metadata language
  image_cache_dir: "data/MediaCover"   # local cache for poster/fanart images

# Comparison Rules
comparison:
  min_savings_percent: 10               # minimum % savings to trigger replacement
  allow_resolution_downgrade: false     # if true, allow 1080p→720p if much smaller
  downgrade_min_savings_percent: 40     # required savings % if downgrading resolution
  preferred_codecs: ["av1", "h265"]     # prefer these codecs in ranking
  max_candidate_age_days: 3650          # ignore NZBs older than this (Usenet retention)
  minimum_file_size_mb: 500             # don't bother with files under 500MB

# File Management
files:
  recycling_bin: "C:\\Slimarr\\recycling"  # move old files here instead of deleting
  recycling_bin_cleanup_days: 30           # auto-delete after 30 days
  verify_after_download: true              # run integrity check on downloaded file

# Scheduling
schedule:
  mode: "nightly"                       # nightly | continuous | manual
  start_time: "01:00"
  end_time: "07:00"

# Web UI
web:
  port: 9494
  bind_address: "0.0.0.0"

# Security
auth:
  required: true
  session_timeout_hours: 24
```

---

## 12. Security

| Concern | Mitigation |
|---------|-----------|
| **Authentication** | Mandatory login with bcrypt-hashed passwords. JWT tokens with expiry. |
| **API Keys** | Stored encrypted in database, never exposed in logs or UI responses |
| **HTTPS** | Support TLS termination via reverse proxy (nginx/Caddy) |
| **CSRF** | SameSite cookies + CSRF tokens on state-changing requests |
| **Rate Limiting** | Respect indexer API rate limits; configurable delays between searches |
| **Input Validation** | All API inputs validated via Pydantic models |
| **File Operations** | Path traversal protection — validate all file paths stay within configured library roots |
| **Logging** | API keys and tokens are redacted in all log output |

---

## 13. Logging System

### 13.1 Log Levels

| Level | Content |
|-------|---------|
| **Summary** | One line per movie: title, action taken, size change |
| **Detail** | All candidates found, comparison scores, decision reasoning |
| **Debug** | API request/response payloads, timing data |

### 13.2 Log Storage

- **Database:** All actions stored in `activity_log` table (queryable via UI)
- **File:** Rotating log files in `logs/` directory (7-day retention)
- **Export:** CSV export from Web UI for offline analysis

### 13.3 Example Log Entries

```
2026-04-21 01:15:32 [INFO]  SCAN   | Toy Story (1995) | 1080p h264 | 5.5 GB
2026-04-21 01:15:34 [INFO]  SEARCH | Toy Story (1995) | Found 14 results across 3 indexers
2026-04-21 01:15:34 [INFO]  COMPARE| Toy Story (1995) | Best: 2160p AV1 3.5GB (-36%) from NZBgeek
2026-04-21 01:15:34 [INFO]  DECIDE | Toy Story (1995) | REPLACE — saving 2.0 GB (36%)
2026-04-21 01:15:35 [INFO]  DOWNLOAD| Toy Story (1995) | Sent to SABnzbd [nzo_abc123]
2026-04-21 01:28:17 [INFO]  COMPLETE| Toy Story (1995) | Download finished, verifying...
2026-04-21 01:28:22 [INFO]  REPLACE| Toy Story (1995) | Old file → recycling bin
2026-04-21 01:28:23 [INFO]  REPLACE| Toy Story (1995) | New file placed at T:\Movies\Toy Story (1995)\
2026-04-21 01:28:25 [INFO]  PLEX   | Toy Story (1995) | Library scan triggered
2026-04-21 01:28:25 [INFO]  DONE   | Toy Story (1995) | 5.5 GB → 3.5 GB | Saved 2.0 GB
---
2026-04-21 01:28:30 [INFO]  SCAN   | The Matrix (1999) | 1080p h265 | 2.1 GB
2026-04-21 01:28:32 [INFO]  SEARCH | The Matrix (1999) | Found 8 results across 3 indexers
2026-04-21 01:28:32 [INFO]  COMPARE| The Matrix (1999) | Smallest candidate: 1080p h265 2.3GB (+10%)
2026-04-21 01:28:32 [INFO]  DECIDE | The Matrix (1999) | SKIP — already optimal, no smaller found
```

---

## 14. Windows Service Integration

### 14.1 Installation as Windows Service

Using **NSSM** (Non-Sucking Service Manager) or Python's `pywin32`:

```powershell
# Option 1: NSSM
nssm install Slimarr "C:\Slimarr\venv\Scripts\python.exe" "C:\Slimarr\main.py"
nssm set Slimarr AppDirectory "C:\Slimarr"
nssm set Slimarr Start SERVICE_AUTO_START
nssm set Slimarr DisplayName "Slimarr - Plex Library Optimizer"
nssm set Slimarr Description "Automatically finds smaller, better-compressed copies of movies"
nssm start Slimarr

# Option 2: Native Windows Service via pywin32
# Built into the application code, installable via:
python main.py --install-service
```

### 14.2 System Tray (Optional)

A lightweight system tray icon showing:
- Service status (running/stopped)
- Current activity (idle/scanning/downloading)
- Quick link to open Web UI in browser
- Start/Stop controls

---

## 15. How Radarr/Sonarr Connect to Usenet (Reference)

Understanding how the *arr ecosystem handles Usenet is fundamental to Slimarr's design:

### 15.1 Indexer Communication (Radarr → Newznab Indexers)

1. **Configuration:** User adds indexer URL + API key in Settings → Indexers
2. **Protocol:** Newznab API — a standardized REST/XML interface
3. **Search:** Radarr sends `GET /api?t=movie&imdbid=tt0114709&apikey=KEY`
4. **Response:** XML RSS feed with release entries, each containing:
   - Release title (parsed for quality info)
   - Download link (NZB URL)
   - File size
   - IMDB/TMDB ID match confirmation
   - Age (days since posted)
5. **Parsing:** Radarr's parser extracts resolution, codec, source, group from the title
6. **Scoring:** Custom Formats + Quality Profiles determine ranking
7. **Grabbing:** Best match's NZB URL is sent to the download client

### 15.2 Download Client Communication (Radarr → SABnzbd)

1. **Configuration:** User adds SABnzbd URL + API key + category in Settings → Download Clients
2. **Sending:** Radarr calls SABnzbd API: `addurl` with the NZB URL and category
3. **Monitoring:** Radarr polls SABnzbd's queue/history API to track progress
4. **Completion:** When SABnzbd reports completion, Radarr reads the output path
5. **Import:** Radarr moves/renames the file to the library, updates its database
6. **Notification:** Plex/Kodi gets notified to refresh

### 15.3 What Slimarr Borrows

Slimarr replicates this exact flow, but with a different trigger:
- **Radarr's trigger:** "I want this movie, find it"
- **Slimarr's trigger:** "I already have this movie, find a smaller copy"

The API calls, protocols, and integrations are identical. Slimarr uses:
- Same Newznab API for indexer searches
- Same SABnzbd/NZBGet API for downloads
- Same Plex API for library awareness
- Optionally, Radarr's own API to piggyback on existing indexer configurations

---

## 16. Project Structure

```
Slimarr/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Configuration loader
│   ├── database.py                # SQLAlchemy models & engine
│   ├── auth/
│   │   ├── router.py              # Login/logout endpoints
│   │   ├── jwt.py                 # Token generation/validation
│   │   └── models.py              # User model
│   ├── api/
│   │   ├── dashboard.py           # Dashboard stats endpoints
│   │   ├── library.py             # Movie list/detail endpoints
│   │   ├── activity.py            # Activity log endpoints
│   │   ├── settings.py            # Settings CRUD endpoints
│   │   └── queue.py               # Queue management endpoints
│   ├── integrations/
│   │   ├── plex.py                # Plex API client
│   │   ├── sabnzbd.py             # SABnzbd API client
│   │   ├── nzbget.py              # NZBGet API client (alternative)
│   │   ├── newznab.py             # Newznab indexer API client
│   │   ├── prowlarr.py            # Prowlarr API client
│   │   ├── radarr.py              # Radarr API client
│   │   └── tmdb.py                # TMDB API client (posters, backdrops, metadata)
│   ├── core/
│   │   ├── scanner.py             # Plex library scanner
│   │   ├── searcher.py            # Usenet release searcher
│   │   ├── parser.py              # Release name parser (codec, res, etc.)
│   │   ├── comparer.py            # Size/quality comparison engine
│   │   ├── downloader.py          # Download orchestration
│   │   ├── replacer.py            # File replacement logic
│   │   ├── mediaprobe.py          # Local file analysis (ffprobe/mediainfo)
│   │   └── image_cache.py         # TMDB image proxy/cache (MediaCover pattern)
│   ├── scheduler/
│   │   ├── scheduler.py           # APScheduler config
│   │   └── jobs.py                # Scheduled job definitions
│   ├── service/
│   │   └── windows_service.py     # Windows service wrapper
│   ├── realtime/
│   │   └── events.py              # Socket.IO event emitter (SignalR pattern)
│   └── utils/
│       ├── logger.py              # Logging configuration
│       └── security.py            # Encryption helpers for API keys
├── frontend/                      # React SPA (built to static files)
│   ├── src/
│   │   ├── pages/                 # React Router pages
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Library.tsx
│   │   │   ├── MovieDetail.tsx    # Fanart backdrop + poster + history
│   │   │   ├── Activity.tsx
│   │   │   ├── Queue.tsx
│   │   │   ├── Settings.tsx
│   │   │   └── System.tsx         # Health checks, tasks, backup
│   │   ├── components/
│   │   │   ├── Sidebar.tsx        # *arr-style sidebar nav
│   │   │   ├── PosterCard.tsx     # Movie poster grid card
│   │   │   ├── QualityBadge.tsx   # Color-coded codec/res/source pills
│   │   │   ├── HealthCheck.tsx    # Integration health indicator
│   │   │   ├── Toast.tsx          # Event notification toasts
│   │   │   └── SizeBar.tsx        # Before/after size comparison bar
│   │   ├── hooks/
│   │   │   ├── useSocket.ts       # Socket.IO client hook (real-time events)
│   │   │   └── useApi.ts          # API client hook
│   │   └── lib/
│   │       ├── api.ts             # REST API client
│   │       └── auth.ts            # JWT auth helpers
│   ├── dist/                      # Built output (served by FastAPI)
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/
│   ├── slimarr.db                 # SQLite database
│   └── MediaCover/                # Cached TMDB images (Radarr pattern)
│       └── {movie_id}/
│           ├── poster.jpg
│           ├── poster-500.jpg
│           └── fanart.jpg
├── config.yaml                    # Default configuration
├── requirements.txt               # Python dependencies
├── DESIGN_DOCUMENT.md             # This file
└── README.md                      # Quick start guide
```

---

## 17. Implementation Phases

### Phase 1 — Foundation (Core MVP)
- [ ] Project scaffolding (FastAPI + SQLite + React/Vite)
- [ ] Configuration system (YAML + database)
- [ ] Authentication (login page + JWT + API key)
- [ ] Plex integration (scan library, read file metadata)
- [ ] TMDB integration (fetch posters, backdrops, metadata on scan)
- [ ] Image proxy/cache endpoint (`/api/v1/images/`, MediaCover pattern)
- [ ] Local file probing (size, codec, resolution via mediainfo)
- [ ] Database models and migrations
- [ ] Socket.IO server setup (real-time event infrastructure)

### Phase 2 — Search & Compare
- [ ] Newznab API client (direct indexer queries)
- [ ] Release name parser (extract quality info from titles)
- [ ] Comparison engine (size-first ranking algorithm)
- [ ] Search results storage and UI display

### Phase 3 — Download & Replace
- [ ] SABnzbd integration (send NZB, monitor progress, get output path)
- [ ] File replacement logic (verify → recycle old → place new)
- [ ] Plex library refresh trigger
- [ ] Activity logging (every action recorded)

### Phase 4 — Scheduling & Automation
- [ ] Night mode scheduler (configurable start/end times)
- [ ] Continuous mode (process all movies sequentially)
- [ ] One-at-a-time job queue (scan→search→compare→download→replace→next)
- [ ] Windows service installation

### Phase 5 — Web UI Polish (*arr Visual Language)
- [ ] Sidebar navigation (Radarr layout)
- [ ] Dashboard with stat cards, savings chart, current activity
- [ ] Library poster grid view (TMDB posters, quality badges, status bars)
- [ ] Library table view (alternative)
- [ ] Movie detail page (fanart backdrop, poster, file info, history, search results)
- [ ] Quality badge components (color-coded pills for codec/resolution/source)
- [ ] Real-time Socket.IO updates (live progress, toasts)
- [ ] Settings pages with Test Connection buttons per integration
- [ ] System → Health page (connection status for all services)
- [ ] System → Tasks page (scheduled jobs, Run Now buttons)
- [ ] Dark theme with *arr color palette, hover transitions, skeleton loaders
- [ ] Responsive design (sidebar collapse on mobile)

### Phase 6 — Advanced Features
- [ ] Prowlarr integration (multi-indexer proxy)
- [ ] Radarr integration (leverage existing metadata + indexers)
- [ ] NZBGet support (alternative download client)
- [ ] CSV/JSON log export
- [ ] Notification support (Discord, email, Pushover)
- [ ] TV Show support via Sonarr (future expansion)

---

## 18. Prerequisites & Dependencies

### User Must Have:
| Service | Required? | Purpose |
|---------|-----------|---------|
| **Plex Media Server** | Yes | Source of movie library and file paths |
| **Usenet Provider** | Yes | Newshosting, Eweka, Frugal, etc. — actual download source |
| **Usenet Indexer(s)** | Yes | NZBgeek, DrunkenSlug, NZBFinder, etc. — search for NZBs |
| **SABnzbd or NZBGet** | Yes | Download client to fetch NZBs from Usenet |
| **Prowlarr** | Optional | Unified indexer management (recommended if using many indexers) |
| **Radarr** | Optional | Can leverage existing movie metadata and indexer configs |

### Python Dependencies:
```
fastapi>=0.110
uvicorn>=0.29
sqlalchemy>=2.0
python-plexapi>=4.15
httpx>=0.27                    # async HTTP client (for TMDB, Newznab, SABnzbd)
python-socketio>=5.11          # Socket.IO server (SignalR equivalent)
apscheduler>=3.10
pyjwt>=2.8
bcrypt>=4.1
pydantic>=2.6
pymediainfo>=6.1
python-multipart>=0.0.9
pyyaml>=6.0
aiofiles>=24.1                 # async static file serving
```

---

## 19. Risk Considerations

| Risk | Mitigation |
|------|-----------|
| **Downloading wrong movie** | Match by IMDB ID (not just title). Verify after download. Keep old file in recycling bin for rollback. |
| **Corrupt download** | Verify file integrity after extraction. Check that video file is playable (probe with ffprobe). |
| **Indexer rate limiting** | Configurable delay between searches. Respect 429 responses. Use Prowlarr for centralized management. |
| **Usenet retention** | Older NZBs may be incomplete. Prefer newer posts. SABnzbd handles par2 repair. |
| **Plex metadata loss** | Plex re-reads metadata from the new file on library scan. Watch status may need to be preserved (tracked via Plex API `viewCount`). |
| **Disk space during download** | Ensure enough temp space for download before starting. Check available space via SABnzbd status API. |
| **Accidentally replacing good quality** | Configurable minimum savings threshold. Never replace with larger file. Recycling bin for rollback. |

---

## 20. Summary

Slimarr fills a gap in the *arr ecosystem: while Radarr finds and downloads movies you want, Slimarr optimizes movies you already have. By reusing the same Newznab, SABnzbd, and Plex APIs that power Radarr and Sonarr, Slimarr integrates seamlessly with existing media server setups.

The one-at-a-time, sequential processing approach ensures predictable behavior — scan one movie, search for it, compare results, download if better, replace, then move on. Running at night keeps it out of the way. Forced continuous mode handles bulk optimization.

Every action is logged, every decision is explainable, and the Web UI provides full visibility into what Slimarr has done and what it plans to do.

---

## 21. Implementation Reference

For **file-by-file implementation details** including exact code, function signatures, API schemas, React component contracts, and build instructions, see:

→ **[IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)**

That document is the companion to this design document and contains everything an AI coding agent needs to build Slimarr from scratch.
