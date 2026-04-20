# Slimarr — Implementation Guide

## For AI Agents: Step-by-Step Build Instructions

This document provides **exact, copy-paste-ready implementation details** for building Slimarr. Every file path, every function signature, every API route, every React component, and every database query is specified. Follow the phases in order.

> **Reference:** See `DESIGN_DOCUMENT.md` for the high-level design, wireframes, and rationale.
> **Brand Assets:** Logo files are in `/images/header-logo.PNG` (full logo) and `/images/icon.PNG` (icon only).

---

# TABLE OF CONTENTS

1. [Project Bootstrap](#1-project-bootstrap)
2. [Backend: Entry Point & Server Setup](#2-backend-entry-point--server-setup)
3. [Backend: Configuration System](#3-backend-configuration-system)
4. [Backend: Database Models & Engine](#4-backend-database-models--engine)
5. [Backend: Authentication System](#5-backend-authentication-system)
6. [Backend: Socket.IO Real-Time Events](#6-backend-socketio-real-time-events)
7. [Backend: TMDB Integration & Image Cache](#7-backend-tmdb-integration--image-cache)
8. [Backend: Plex Integration](#8-backend-plex-integration)
9. [Backend: Newznab Indexer Client](#9-backend-newznab-indexer-client)
10. [Backend: Prowlarr Integration](#10-backend-prowlarr-integration)
11. [Backend: SABnzbd Download Client](#11-backend-sabnzbd-download-client)
12. [Backend: Release Name Parser](#12-backend-release-name-parser)
13. [Backend: Comparison Engine](#13-backend-comparison-engine)
14. [Backend: Scanner Module](#14-backend-scanner-module)
15. [Backend: Searcher Module](#15-backend-searcher-module)
16. [Backend: Downloader & Replacer](#16-backend-downloader--replacer)
17. [Backend: Orchestrator / Job Queue](#17-backend-orchestrator--job-queue)
18. [Backend: Scheduler](#18-backend-scheduler)
19. [Backend: API Routes — Complete Specification](#19-backend-api-routes--complete-specification)
20. [Backend: Radarr Integration (Optional)](#20-backend-radarr-integration-optional)
21. [Backend: Windows Service](#21-backend-windows-service)
22. [Frontend: Project Setup](#22-frontend-project-setup)
23. [Frontend: App Shell & Routing](#23-frontend-app-shell--routing)
24. [Frontend: Sidebar Component](#24-frontend-sidebar-component)
25. [Frontend: Dashboard Page](#25-frontend-dashboard-page)
26. [Frontend: Library Page (Poster Grid)](#26-frontend-library-page-poster-grid)
27. [Frontend: Movie Detail Page](#27-frontend-movie-detail-page)
28. [Frontend: Activity Page](#28-frontend-activity-page)
29. [Frontend: Queue Page](#29-frontend-queue-page)
30. [Frontend: Settings Page](#30-frontend-settings-page)
31. [Frontend: System Page](#31-frontend-system-page)
32. [Frontend: Login Page](#32-frontend-login-page)
33. [Frontend: Shared Components](#33-frontend-shared-components)
34. [Frontend: Socket.IO Hook & Real-Time](#34-frontend-socketio-hook--real-time)
35. [Frontend: API Client](#35-frontend-api-client)
36. [Testing Strategy](#36-testing-strategy)
37. [Build & Deployment](#37-build--deployment)
38. [First Run / Setup Wizard](#38-first-run--setup-wizard)

---

# 1. Project Bootstrap

## 1.1 Directory Creation

Create the full project skeleton:

```
Slimarr/
├── images/
│   ├── header-logo.PNG            # Already exists — full logo with text
│   └── icon.PNG                   # Already exists — icon only
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Configuration loader
│   ├── database.py                # SQLAlchemy models & engine
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── router.py              # Login/logout/register endpoints
│   │   ├── jwt.py                 # Token generation/validation
│   │   └── dependencies.py        # Auth dependency injection
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dashboard.py           # Dashboard stats endpoints
│   │   ├── library.py             # Movie list/detail/search endpoints
│   │   ├── activity.py            # Activity log endpoints
│   │   ├── settings.py            # Settings CRUD + test connection endpoints
│   │   ├── queue.py               # Queue management endpoints
│   │   ├── system.py              # Health checks, tasks, backup
│   │   └── images.py              # TMDB image proxy endpoint
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── plex.py                # Plex API client
│   │   ├── sabnzbd.py             # SABnzbd API client
│   │   ├── newznab.py             # Newznab indexer API client
│   │   ├── prowlarr.py            # Prowlarr API client
│   │   ├── radarr.py              # Radarr API client
│   │   └── tmdb.py                # TMDB API client
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scanner.py             # Plex library scanner + TMDB enrichment
│   │   ├── searcher.py            # Usenet release searcher
│   │   ├── parser.py              # Release name parser
│   │   ├── comparer.py            # Size/quality comparison engine
│   │   ├── downloader.py          # Download orchestration
│   │   ├── replacer.py            # File replacement logic
│   │   ├── orchestrator.py        # Master job queue (one-at-a-time)
│   │   └── image_cache.py         # TMDB image proxy/cache
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── scheduler.py           # APScheduler setup + job definitions
│   ├── realtime/
│   │   ├── __init__.py
│   │   └── events.py              # Socket.IO server + event emitter
│   ├── service/
│   │   ├── __init__.py
│   │   └── windows_service.py     # NSSM / pywin32 service wrapper
│   └── utils/
│       ├── __init__.py
│       ├── logger.py              # Logging configuration
│       └── security.py            # Encrypt/decrypt API keys at rest
├── frontend/
│   ├── public/
│   │   ├── favicon.ico            # Generated from icon.PNG
│   │   └── logo.png               # Copy of header-logo.PNG for login page
│   ├── src/
│   │   ├── main.tsx               # React entry point
│   │   ├── App.tsx                # Root component with router
│   │   ├── index.css              # Tailwind imports + global styles
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Library.tsx
│   │   │   ├── MovieDetail.tsx
│   │   │   ├── Activity.tsx
│   │   │   ├── Queue.tsx
│   │   │   ├── Settings.tsx
│   │   │   └── System.tsx
│   │   ├── components/
│   │   │   ├── Layout.tsx         # Sidebar + content area wrapper
│   │   │   ├── Sidebar.tsx
│   │   │   ├── PosterCard.tsx
│   │   │   ├── QualityBadge.tsx
│   │   │   ├── SizeBar.tsx
│   │   │   ├── HealthCheck.tsx
│   │   │   ├── StatCard.tsx
│   │   │   ├── ActivityItem.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   ├── TestConnectionButton.tsx
│   │   │   └── ProtectedRoute.tsx
│   │   ├── hooks/
│   │   │   ├── useSocket.ts
│   │   │   ├── useApi.ts
│   │   │   └── useAuth.ts
│   │   └── lib/
│   │       ├── api.ts             # Axios/fetch wrapper
│   │       ├── auth.ts            # Token storage/refresh
│   │       ├── socket.ts          # Socket.IO client singleton
│   │       └── types.ts           # TypeScript interfaces
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/                          # Created at runtime
│   ├── slimarr.db                 # SQLite database (auto-created)
│   ├── MediaCover/                # TMDB image cache (auto-created)
│   └── logs/                      # Log files (auto-created)
├── config.yaml                    # User configuration
├── requirements.txt
├── DESIGN_DOCUMENT.md
├── IMPLEMENTATION_GUIDE.md
└── README.md
```

## 1.2 Python Environment Setup

```
requirements.txt contents:
```
```
# Web framework
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.18
aiofiles==24.1.0

# Database
sqlalchemy==2.0.36
alembic==1.14.1

# Authentication
pyjwt==2.10.1
bcrypt==4.2.1
passlib[bcrypt]==1.7.4

# HTTP client
httpx==0.28.1

# Real-time
python-socketio==5.12.1

# Plex
python-plexapi==4.15.16

# Scheduling
apscheduler==3.10.4

# Media analysis
pymediainfo==6.1.0

# Configuration
pyyaml==6.0.2
pydantic==2.10.4
pydantic-settings==2.7.1

# Logging
loguru==0.7.3

# XML parsing (for Newznab responses)
lxml==5.3.0

# Utilities
python-dotenv==1.0.1
```

## 1.3 Frontend Package Setup

```json
{
  "name": "slimarr-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "socket.io-client": "^4.8.1",
    "recharts": "^2.15.0",
    "react-hot-toast": "^2.4.1",
    "lucide-react": "^0.468.0",
    "clsx": "^2.1.1",
    "date-fns": "^4.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.6.3",
    "vite": "^6.0.3",
    "eslint": "^9.16.0"
  }
}
```

## 1.4 Initial Config File

Create `config.yaml` with safe defaults. On first run, the app detects this file exists but has placeholder values and redirects to the setup wizard in the UI.

```yaml
# Slimarr Configuration
# Edit this file or use the Web UI Settings page.

server:
  host: "0.0.0.0"
  port: 9494
  log_level: "info"                     # debug | info | warning | error

auth:
  secret_key: ""                        # Auto-generated on first run if empty
  session_timeout_hours: 72
  api_key: ""                           # Auto-generated on first run if empty

plex:
  url: ""
  token: ""
  library_sections: []                  # e.g., ["Movies", "4K Movies"]

sabnzbd:
  url: ""
  api_key: ""
  category: "slimarr"

indexers: []
# Example:
# - name: "NZBgeek"
#   url: "https://api.nzbgeek.info"
#   api_key: ""
#   categories: [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060]

prowlarr:
  enabled: false
  url: ""
  api_key: ""

radarr:
  enabled: false
  url: ""
  api_key: ""

tmdb:
  api_key: ""                           # Free at https://www.themoviedb.org/settings/api
  language: "en-US"

comparison:
  min_savings_percent: 10
  allow_resolution_downgrade: false
  downgrade_min_savings_percent: 40
  preferred_codecs: ["av1", "h265"]
  max_candidate_age_days: 3650
  minimum_file_size_mb: 500

files:
  recycling_bin: "./data/recycling"
  recycling_bin_cleanup_days: 30
  verify_after_download: true

schedule:
  mode: "nightly"                       # nightly | continuous | manual
  start_time: "01:00"
  end_time: "07:00"
  days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
  max_downloads_per_night: 10
  throttle_seconds: 30
```

---

# 2. Backend: Entry Point & Server Setup

## 2.1 `backend/main.py`

This is the single entry point. It:
1. Loads config
2. Initializes the database
3. Creates the FastAPI app
4. Mounts Socket.IO
5. Registers all API routers
6. Serves the React frontend as static files
7. Starts the scheduler

```python
"""
Slimarr — main.py
Single-process entry point. Run with: python -m backend.main
Or: uvicorn backend.main:app --host 0.0.0.0 --port 9494
"""
```

**Key implementation details:**

```python
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# Socket.IO server — created here, shared globally
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    from backend.config import get_config
    from backend.database import init_db
    from backend.scheduler.scheduler import start_scheduler

    config = get_config()

    # Auto-generate secret_key and api_key if empty (first run)
    import secrets
    if not config.auth.secret_key:
        config.auth.secret_key = secrets.token_urlsafe(32)
        # Write back to config file
    if not config.auth.api_key:
        config.auth.api_key = secrets.token_urlsafe(32)

    # Initialize database (creates tables if not exist)
    await init_db()

    # Create data directories
    import os
    os.makedirs("data/MediaCover", exist_ok=True)
    os.makedirs("data/logs", exist_ok=True)
    os.makedirs(config.files.recycling_bin, exist_ok=True)

    # Start the scheduler (nightly jobs, etc.)
    start_scheduler(config)

    yield

    # SHUTDOWN
    from backend.scheduler.scheduler import stop_scheduler
    stop_scheduler()

app = FastAPI(
    title="Slimarr",
    version="0.1.0",
    docs_url="/api/docs",       # Swagger UI at /api/docs
    redoc_url=None,
    lifespan=lifespan,
)

# --- Register API routers ---
from backend.auth.router import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.library import router as library_router
from backend.api.activity import router as activity_router
from backend.api.settings import router as settings_router
from backend.api.queue import router as queue_router
from backend.api.system import router as system_router
from backend.api.images import router as images_router

app.include_router(auth_router,      prefix="/api/v1/auth",      tags=["Auth"])
app.include_router(dashboard_router, prefix="/api/v1/dashboard",  tags=["Dashboard"])
app.include_router(library_router,   prefix="/api/v1/library",    tags=["Library"])
app.include_router(activity_router,  prefix="/api/v1/activity",   tags=["Activity"])
app.include_router(settings_router,  prefix="/api/v1/settings",   tags=["Settings"])
app.include_router(queue_router,     prefix="/api/v1/queue",      tags=["Queue"])
app.include_router(system_router,    prefix="/api/v1/system",     tags=["System"])
app.include_router(images_router,    prefix="/api/v1/images",     tags=["Images"])

# --- Wrap with Socket.IO ---
socket_app = socketio.ASGIApp(sio, other_app=app)

# --- Serve React frontend (static files) ---
# The React app is built to frontend/dist/
# All non-API routes serve index.html (SPA client-side routing)
import os
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all: serve React's index.html for client-side routing."""
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
```

**How to run:**
```powershell
# Development
cd C:\Slimarr
python -m uvicorn backend.main:socket_app --host 0.0.0.0 --port 9494 --reload

# Production (the app itself)
python -m backend.main
```

The `if __name__ == "__main__"` block in `main.py`:
```python
if __name__ == "__main__":
    import uvicorn
    from backend.config import get_config
    config = get_config()
    uvicorn.run(
        "backend.main:socket_app",
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
    )
```

---

# 3. Backend: Configuration System

## 3.1 `backend/config.py`

Uses Pydantic models for type-safe config. Loads from `config.yaml`, allows runtime overrides via database `settings` table.

```python
"""
Configuration loader.
Priority: database settings > config.yaml > defaults
"""
from pydantic import BaseModel
from typing import Optional
import yaml, os

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9494
    log_level: str = "info"

class AuthConfig(BaseModel):
    secret_key: str = ""
    session_timeout_hours: int = 72
    api_key: str = ""

class PlexConfig(BaseModel):
    url: str = ""
    token: str = ""
    library_sections: list[str] = []

class SabnzbdConfig(BaseModel):
    url: str = ""
    api_key: str = ""
    category: str = "slimarr"

class IndexerConfig(BaseModel):
    name: str
    url: str
    api_key: str
    categories: list[int] = [2000]

class ProwlarrConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    api_key: str = ""

class RadarrConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    api_key: str = ""

class TmdbConfig(BaseModel):
    api_key: str = ""
    language: str = "en-US"

class ComparisonConfig(BaseModel):
    min_savings_percent: float = 10.0
    allow_resolution_downgrade: bool = False
    downgrade_min_savings_percent: float = 40.0
    preferred_codecs: list[str] = ["av1", "h265"]
    max_candidate_age_days: int = 3650
    minimum_file_size_mb: int = 500

class FilesConfig(BaseModel):
    recycling_bin: str = "./data/recycling"
    recycling_bin_cleanup_days: int = 30
    verify_after_download: bool = True

class ScheduleConfig(BaseModel):
    mode: str = "nightly"              # nightly | continuous | manual
    start_time: str = "01:00"
    end_time: str = "07:00"
    days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    max_downloads_per_night: int = 10
    throttle_seconds: int = 30

class SlimarrConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    auth: AuthConfig = AuthConfig()
    plex: PlexConfig = PlexConfig()
    sabnzbd: SabnzbdConfig = SabnzbdConfig()
    indexers: list[IndexerConfig] = []
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    radarr: RadarrConfig = RadarrConfig()
    tmdb: TmdbConfig = TmdbConfig()
    comparison: ComparisonConfig = ComparisonConfig()
    files: FilesConfig = FilesConfig()
    schedule: ScheduleConfig = ScheduleConfig()

_config: Optional[SlimarrConfig] = None

def get_config() -> SlimarrConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config

def load_config(path: str = "config.yaml") -> SlimarrConfig:
    if os.path.exists(path):
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}
        return SlimarrConfig(**raw)
    return SlimarrConfig()

def save_config(config: SlimarrConfig, path: str = "config.yaml"):
    with open(path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)
```

---

# 4. Backend: Database Models & Engine

## 4.1 `backend/database.py`

Uses SQLAlchemy 2.0 async with SQLite. Tables match the schema in DESIGN_DOCUMENT.md but with full ORM models.

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, func
from typing import Optional
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///data/slimarr.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    plex_rating_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # TMDB metadata
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    poster_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backdrop_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    genres: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON array

    # File info
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kbps
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # BluRay, WEB-DL, etc.

    # Tracking
    original_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # size before any replacement
    total_savings: Mapped[int] = mapped_column(Integer, default=0)  # cumulative bytes saved
    times_replaced: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_searched: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    # Status values: pending, scanning, searching, downloading, replacing, optimal, replaced, error, skipped
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    search_results: Mapped[list["SearchResult"]] = relationship(back_populates="movie", cascade="all, delete-orphan")
    downloads: Mapped[list["Download"]] = relationship(back_populates="movie", cascade="all, delete-orphan")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="movie", cascade="all, delete-orphan")


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), index=True)
    indexer_name: Mapped[str] = mapped_column(String)
    release_title: Mapped[str] = mapped_column(String)
    nzb_url: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)  # bytes
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String, default="pending")  # accept, reject, pending
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    searched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    movie: Mapped["Movie"] = relationship(back_populates="search_results")


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), index=True)
    search_result_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_results.id"), nullable=True)
    sabnzbd_nzo_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    # Status: queued, downloading, extracting, completed, failed, imported, replaced
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 to 100.0
    speed: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., "12.5 MB/s"
    eta: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., "5m 23s"
    old_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    old_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    movie: Mapped["Movie"] = relationship(back_populates="downloads")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[Optional[int]] = mapped_column(ForeignKey("movies.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Actions: scanned, searched, skipped, grabbed, downloading, downloaded, replaced, error, optimal
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    movie: Mapped[Optional["Movie"]] = relationship(back_populates="activity_logs")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db() -> AsyncSession:
    """Dependency: yields an async database session."""
    async with async_session() as session:
        yield session
```

**Important:** Add `aiosqlite` to requirements.txt:
```
aiosqlite==0.20.0
```

---

# 5. Backend: Authentication System

## 5.1 `backend/auth/jwt.py`

```python
import jwt
from datetime import datetime, timedelta, timezone
from backend.config import get_config

def create_access_token(username: str) -> str:
    config = get_config()
    expire = datetime.now(timezone.utc) + timedelta(hours=config.auth.session_timeout_hours)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.auth.secret_key, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    config = get_config()
    return jwt.decode(token, config.auth.secret_key, algorithms=["HS256"])
```

## 5.2 `backend/auth/dependencies.py`

Two auth methods: JWT Bearer token (for UI) and X-Api-Key header (for external access).

```python
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.auth.jwt import decode_access_token
from backend.config import get_config

security = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Authenticate via:
    1. Bearer JWT token (from login)
    2. X-Api-Key header (for external/programmatic access)
    """
    # Check API key first
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        config = get_config()
        if api_key == config.auth.api_key:
            return "api_user"
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check JWT bearer token
    if credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            return payload["sub"]
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    raise HTTPException(status_code=401, detail="Authentication required")
```

## 5.3 `backend/auth/router.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from passlib.hash import bcrypt
from sqlalchemy import select
from backend.database import get_db, User, AsyncSession
from backend.auth.jwt import create_access_token

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    username: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not bcrypt.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.username)
    return LoginResponse(token=token, username=user.username)

@router.post("/register", response_model=LoginResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Only allow registration if no users exist (first-run setup)
    result = await db.execute(select(User))
    if result.scalars().first() is not None:
        raise HTTPException(status_code=403, detail="Registration disabled. User already exists.")
    hashed = bcrypt.hash(body.password)
    user = User(username=body.username, password_hash=hashed)
    db.add(user)
    await db.commit()
    token = create_access_token(user.username)
    return LoginResponse(token=token, username=user.username)

@router.get("/check")
async def check_auth_status(db: AsyncSession = Depends(get_db)):
    """Check if any user exists (for setup wizard detection)."""
    result = await db.execute(select(User))
    has_user = result.scalars().first() is not None
    return {"has_user": has_user, "setup_required": not has_user}
```

---

# 6. Backend: Socket.IO Real-Time Events

## 6.1 `backend/realtime/events.py`

Central event emitter. All backend modules import `emit_event()` to push updates to the UI.

```python
"""
Socket.IO event system.
Import `emit_event` anywhere in the backend to push real-time updates to the UI.
"""
from backend.main import sio

async def emit_event(event: str, data: dict):
    """
    Emit a Socket.IO event to all connected clients.

    Events:
        scan:started      - {"total_movies": int}
        scan:progress      - {"movie_id": int, "title": str, "current": int, "total": int}
        scan:completed     - {"total_movies": int, "duration_seconds": float}
        search:started     - {"movie_id": int, "title": str}
        search:results     - {"movie_id": int, "title": str, "count": int, "best_savings_pct": float}
        download:started   - {"movie_id": int, "title": str, "release": str}
        download:progress  - {"movie_id": int, "progress": float, "speed": str, "eta": str}
        download:completed - {"movie_id": int, "title": str}
        download:failed    - {"movie_id": int, "title": str, "error": str}
        replace:completed  - {"movie_id": int, "title": str, "old_size": int, "new_size": int, "savings_pct": float}
        queue:updated      - {"queue_length": int, "current_movie_id": int | None}
        system:health      - {"service": str, "status": str, "detail": str}
        activity:new       - {"id": int, "action": str, "movie_title": str, "detail": str}
    """
    await sio.emit(event, data)
```

**Note on circular imports:** The `sio` object is created in `main.py`. To avoid circular imports, `events.py` should import it lazily or the `sio` object should be in its own tiny module:

Create `backend/realtime/sio_instance.py`:
```python
import socketio
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
```

Then `main.py` imports from there, and `events.py` imports from there. No circular dependency.

---

# 7. Backend: TMDB Integration & Image Cache

## 7.1 `backend/integrations/tmdb.py`

```python
"""TMDB API client for movie metadata and images."""
import httpx
from typing import Optional
from backend.config import get_config

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

class TMDBClient:
    def __init__(self):
        config = get_config()
        self.api_key = config.tmdb.api_key
        self.language = config.tmdb.language

    async def search_movie(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        """Search TMDB by title and year. Returns first match or None."""
        params = {"api_key": self.api_key, "query": title, "language": self.language}
        if year:
            params["year"] = year
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{TMDB_BASE}/search/movie", params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0] if results else None

    async def get_movie(self, tmdb_id: int) -> dict:
        """Get full movie details by TMDB ID."""
        params = {"api_key": self.api_key, "language": self.language}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{TMDB_BASE}/movie/{tmdb_id}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def find_by_imdb(self, imdb_id: str) -> Optional[dict]:
        """Find movie by IMDB ID (most reliable match)."""
        params = {"api_key": self.api_key, "external_source": "imdb_id"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{TMDB_BASE}/find/{imdb_id}", params=params)
            resp.raise_for_status()
            results = resp.json().get("movie_results", [])
            return results[0] if results else None

    async def download_image(self, path: str, size: str = "w300") -> bytes:
        """Download an image from TMDB. Returns raw bytes."""
        url = f"{TMDB_IMAGE_BASE}/{size}{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
```

## 7.2 `backend/core/image_cache.py`

```python
"""
TMDB image cache — mirrors Radarr's MediaCover pattern.
Images are cached to data/MediaCover/{movie_id}/
"""
import os
import aiofiles
from backend.integrations.tmdb import TMDBClient

CACHE_DIR = "data/MediaCover"

async def get_or_cache_image(movie_id: int, image_type: str, tmdb_path: str) -> str:
    """
    Returns the local file path for a cached image.
    Downloads from TMDB if not cached yet.

    image_type: "poster" | "poster-500" | "fanart"
    """
    size_map = {
        "poster": "w300",
        "poster-500": "w500",
        "fanart": "w1280",
    }
    filename_map = {
        "poster": "poster.jpg",
        "poster-500": "poster-500.jpg",
        "fanart": "fanart.jpg",
    }

    movie_dir = os.path.join(CACHE_DIR, str(movie_id))
    os.makedirs(movie_dir, exist_ok=True)

    file_path = os.path.join(movie_dir, filename_map[image_type])

    if not os.path.exists(file_path):
        # Download from TMDB
        client = TMDBClient()
        image_bytes = await client.download_image(tmdb_path, size_map[image_type])
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)

    return file_path
```

## 7.3 `backend/api/images.py`

```python
"""Image proxy API — serves cached TMDB images."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from backend.database import async_session, Movie
from backend.core.image_cache import get_or_cache_image

router = APIRouter()

@router.get("/{movie_id}/{image_type}")
async def get_movie_image(movie_id: int, image_type: str):
    """
    Proxy endpoint for TMDB images.
    GET /api/v1/images/123/poster.jpg
    GET /api/v1/images/123/fanart.jpg
    GET /api/v1/images/123/poster-500.jpg

    No auth required (images are not sensitive).
    """
    # Map filename to image type
    type_map = {
        "poster.jpg": ("poster", "poster_path"),
        "poster-500.jpg": ("poster-500", "poster_path"),
        "fanart.jpg": ("fanart", "backdrop_path"),
    }

    if image_type not in type_map:
        raise HTTPException(404, "Invalid image type. Use: poster.jpg, poster-500.jpg, fanart.jpg")

    cache_type, db_field = type_map[image_type]

    # Look up the TMDB path from database
    async with async_session() as db:
        result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = result.scalar_one_or_none()
        if not movie:
            raise HTTPException(404, "Movie not found")

        tmdb_path = getattr(movie, db_field)
        if not tmdb_path:
            raise HTTPException(404, "No image available for this movie")

    file_path = await get_or_cache_image(movie_id, cache_type, tmdb_path)
    return FileResponse(file_path, media_type="image/jpeg")
```

---

# 8. Backend: Plex Integration

## 8.1 `backend/integrations/plex.py`

```python
"""Plex Media Server API client."""
from plexapi.server import PlexServer
from typing import Optional
from backend.config import get_config

class PlexClient:
    def __init__(self):
        config = get_config()
        self._server: Optional[PlexServer] = None
        self.url = config.plex.url
        self.token = config.plex.token
        self.library_sections = config.plex.library_sections

    @property
    def server(self) -> PlexServer:
        if self._server is None:
            self._server = PlexServer(self.url, self.token)
        return self._server

    def get_all_movies(self) -> list[dict]:
        """
        Scan all configured Plex library sections and return movie info.
        Returns list of dicts with all relevant metadata.
        """
        movies = []
        for section_name in self.library_sections:
            section = self.server.library.section(section_name)
            for plex_movie in section.all():
                for media in plex_movie.media:
                    for part in media.parts:
                        movies.append({
                            "plex_rating_key": str(plex_movie.ratingKey),
                            "title": plex_movie.title,
                            "year": plex_movie.year,
                            "imdb_id": next(
                                (g.id for g in (plex_movie.guids or []) if g.id.startswith("imdb://")),
                                ""
                            ).replace("imdb://", ""),
                            "tmdb_id": int(
                                next(
                                    (g.id for g in (plex_movie.guids or []) if g.id.startswith("tmdb://")),
                                    "tmdb://0"
                                ).replace("tmdb://", "")
                            ),
                            "file_path": part.file,
                            "file_size": part.size,
                            "resolution": media.videoResolution,  # "1080", "720", "4k"
                            "video_codec": media.videoCodec,      # "h264", "hevc"
                            "audio_codec": media.audioCodec,      # "aac", "dts"
                            "bitrate": media.bitrate,             # kbps
                            "container": media.container,         # "mkv", "mp4"
                            "width": media.width,
                            "height": media.height,
                        })
        return movies

    def refresh_library(self, section_name: Optional[str] = None):
        """Trigger a Plex library scan."""
        if section_name:
            self.server.library.section(section_name).update()
        else:
            for name in self.library_sections:
                self.server.library.section(name).update()

    def test_connection(self) -> dict:
        """Test Plex connection and return server info."""
        try:
            server = PlexServer(self.url, self.token)
            sections = [s.title for s in server.library.sections()]
            total_movies = sum(
                s.totalSize for s in server.library.sections()
                if s.type == "movie" and s.title in self.library_sections
            )
            return {
                "success": True,
                "server_name": server.friendlyName,
                "version": server.version,
                "sections": sections,
                "movie_count": total_movies,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

# 9. Backend: Newznab Indexer Client

## 9.1 `backend/integrations/newznab.py`

```python
"""
Newznab API client — the standard protocol used by all *arr apps for Usenet indexer searches.
Queries indexers directly (or Prowlarr, which exposes the same Newznab API).
"""
import httpx
from lxml import etree
from typing import Optional
from backend.config import IndexerConfig

class NewznabClient:
    def __init__(self, indexer: IndexerConfig):
        self.name = indexer.name
        self.url = indexer.url.rstrip("/")
        self.api_key = indexer.api_key
        self.categories = indexer.categories

    async def search_by_imdb(self, imdb_id: str) -> list[dict]:
        """
        Search by IMDB ID (most reliable match method).
        GET {url}/api?t=movie&imdbid=tt0114709&apikey=KEY
        """
        params = {
            "t": "movie",
            "imdbid": imdb_id,
            "apikey": self.api_key,
            "cat": ",".join(str(c) for c in self.categories),
            "limit": 100,
        }
        return await self._do_search(params)

    async def search_by_query(self, query: str) -> list[dict]:
        """
        Fallback: search by text query (title + year).
        GET {url}/api?t=search&q=Toy+Story+1995&cat=2000&apikey=KEY
        """
        params = {
            "t": "search",
            "q": query,
            "apikey": self.api_key,
            "cat": ",".join(str(c) for c in self.categories),
            "limit": 100,
        }
        return await self._do_search(params)

    async def _do_search(self, params: dict) -> list[dict]:
        """Execute search and parse XML response into list of release dicts."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.url}/api", params=params)
            resp.raise_for_status()

        results = []
        root = etree.fromstring(resp.content)

        # Newznab XML namespace
        ns = {"newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"}

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")

            # Size from enclosure
            enclosure = item.find("enclosure")
            size = int(enclosure.get("length", 0)) if enclosure is not None else 0

            # Size from newznab attributes (backup)
            if size == 0:
                for attr in item.findall("newznab:attr", ns):
                    if attr.get("name") == "size":
                        size = int(attr.get("value", 0))
                        break

            # Extract other newznab attributes
            attrs = {}
            for attr in item.findall("newznab:attr", ns):
                attrs[attr.get("name")] = attr.get("value")

            results.append({
                "indexer_name": self.name,
                "release_title": title,
                "nzb_url": link,
                "size": size,
                "imdb_id": attrs.get("imdb", ""),
                "pub_date": pub_date,
                "grabs": int(attrs.get("grabs", 0)),
                "category": attrs.get("category", ""),
            })

        return results

    async def test_connection(self) -> dict:
        """Test indexer connectivity by requesting caps."""
        try:
            params = {"t": "caps", "apikey": self.api_key}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.url}/api", params=params)
                resp.raise_for_status()
            root = etree.fromstring(resp.content)
            server_title = root.find(".//server")
            title = server_title.get("title", "Unknown") if server_title is not None else "Connected"
            return {"success": True, "indexer": self.name, "server": title}
        except Exception as e:
            return {"success": False, "indexer": self.name, "error": str(e)}
```

---

# 10. Backend: Prowlarr Integration

## 10.1 `backend/integrations/prowlarr.py`

```python
"""Prowlarr API client — unified indexer proxy."""
import httpx
from backend.config import get_config

class ProwlarrClient:
    def __init__(self):
        config = get_config()
        self.url = config.prowlarr.url.rstrip("/")
        self.api_key = config.prowlarr.api_key

    async def get_indexers(self) -> list[dict]:
        """List all configured indexers in Prowlarr."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.url}/api/v1/indexer",
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()

    async def search(self, query: str = "", imdb_id: str = "", categories: list[int] = None) -> list[dict]:
        """Search across all Prowlarr indexers."""
        params = {"type": "movie"}
        if query:
            params["query"] = query
        if categories:
            params["categories"] = categories
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.url}/api/v1/search",
                params=params,
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            results = resp.json()

        # Normalize to the same format as NewznabClient
        normalized = []
        for r in results:
            normalized.append({
                "indexer_name": r.get("indexer", "Prowlarr"),
                "release_title": r.get("title", ""),
                "nzb_url": r.get("downloadUrl", r.get("guid", "")),
                "size": r.get("size", 0),
                "imdb_id": str(r.get("imdbId", "")),
                "pub_date": r.get("publishDate", ""),
                "grabs": r.get("grabs", 0),
                "category": ",".join(str(c) for c in r.get("categories", [])),
            })
        return normalized

    async def test_connection(self) -> dict:
        try:
            indexers = await self.get_indexers()
            return {
                "success": True,
                "indexer_count": len(indexers),
                "indexers": [i.get("name") for i in indexers],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

# 11. Backend: SABnzbd Download Client

## 11.1 `backend/integrations/sabnzbd.py`

```python
"""SABnzbd download client API."""
import httpx
from typing import Optional
from backend.config import get_config

class SABnzbdClient:
    def __init__(self):
        config = get_config()
        self.url = config.sabnzbd.url.rstrip("/")
        self.api_key = config.sabnzbd.api_key
        self.category = config.sabnzbd.category

    async def _api(self, mode: str, extra_params: dict = None) -> dict:
        """Generic SABnzbd API call."""
        params = {
            "mode": mode,
            "apikey": self.api_key,
            "output": "json",
        }
        if extra_params:
            params.update(extra_params)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.url}/api", params=params)
            resp.raise_for_status()
            return resp.json()

    async def add_nzb_url(self, nzb_url: str, title: str = "") -> str:
        """
        Send an NZB URL to SABnzbd for download.
        Returns the nzo_id (job ID).
        """
        result = await self._api("addurl", {
            "name": nzb_url,
            "nzbname": title,
            "cat": self.category,
        })
        nzo_ids = result.get("nzo_ids", [])
        if not nzo_ids:
            raise RuntimeError(f"SABnzbd addurl failed: {result}")
        return nzo_ids[0]

    async def get_queue(self) -> list[dict]:
        """Get current download queue."""
        result = await self._api("queue")
        slots = result.get("queue", {}).get("slots", [])
        return [
            {
                "nzo_id": s["nzo_id"],
                "filename": s["filename"],
                "status": s["status"],
                "percentage": float(s.get("percentage", 0)),
                "size": s.get("size", ""),
                "sizeleft": s.get("sizeleft", ""),
                "speed": s.get("speed", ""),
                "timeleft": s.get("timeleft", ""),
                "category": s.get("cat", ""),
            }
            for s in slots
        ]

    async def get_history(self, limit: int = 20) -> list[dict]:
        """Get completed download history."""
        result = await self._api("history", {"limit": limit})
        slots = result.get("history", {}).get("slots", [])
        return [
            {
                "nzo_id": s["nzo_id"],
                "name": s["name"],
                "status": s["status"],          # Completed, Failed
                "storage": s.get("storage", ""),  # Final file path
                "size": s.get("bytes", 0),
                "completed": s.get("completed", 0),  # timestamp
                "category": s.get("category", ""),
            }
            for s in slots
        ]

    async def get_job_status(self, nzo_id: str) -> Optional[dict]:
        """Check a specific job's status in queue or history."""
        # Check queue first
        queue = await self.get_queue()
        for item in queue:
            if item["nzo_id"] == nzo_id:
                return {**item, "location": "queue"}

        # Check history
        history = await self.get_history(limit=50)
        for item in history:
            if item["nzo_id"] == nzo_id:
                return {**item, "location": "history"}

        return None

    async def test_connection(self) -> dict:
        """Test SABnzbd connection."""
        try:
            result = await self._api("version")
            version = result.get("version", "unknown")
            queue = await self._api("queue")
            speed = queue.get("queue", {}).get("speed", "0")
            return {
                "success": True,
                "version": version,
                "speed": speed,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

# 12. Backend: Release Name Parser

## 12.1 `backend/core/parser.py`

This is critical — it extracts quality info from Usenet release titles, identical to how Radarr parses them.

```python
"""
Release name parser — extracts resolution, codec, source, audio from release titles.
Mirrors Radarr's parsing logic.
"""
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedRelease:
    title: str
    year: Optional[int] = None
    resolution: Optional[str] = None   # "2160p", "1080p", "720p", "480p"
    video_codec: Optional[str] = None  # "h265", "h264", "av1", "xvid"
    audio_codec: Optional[str] = None  # "atmos", "truehd", "dts-hd ma", "dts", "aac", "dd5.1"
    source: Optional[str] = None       # "bluray", "remux", "web-dl", "webrip", "hdtv"
    hdr: Optional[str] = None          # "hdr10", "hdr10+", "dolby vision", "hlg", None (SDR)
    group: Optional[str] = None        # release group name

# Resolution priority (higher = better)
RESOLUTION_RANK = {
    "2160p": 4, "4k": 4,
    "1080p": 3,
    "720p": 2,
    "480p": 1,
    "sd": 0,
}

# Codec efficiency ranking (higher = more efficient)
CODEC_RANK = {
    "av1": 100,
    "h265": 80, "hevc": 80, "x265": 80,
    "h264": 50, "x264": 50, "avc": 50,
    "mpeg2": 20,
    "xvid": 10, "divx": 10,
}

def parse_release_title(title: str) -> ParsedRelease:
    """Parse a Usenet release title into structured quality info."""
    result = ParsedRelease(title=title)
    t = title.lower()

    # Year
    year_match = re.search(r'[\.\s\(]((?:19|20)\d{2})[\.\s\)]', title)
    if year_match:
        result.year = int(year_match.group(1))

    # Resolution
    if re.search(r'2160p|4k|uhd', t):
        result.resolution = "2160p"
    elif re.search(r'1080p|1080i', t):
        result.resolution = "1080p"
    elif re.search(r'720p', t):
        result.resolution = "720p"
    elif re.search(r'480p|576p|sd', t):
        result.resolution = "480p"

    # Video codec
    if re.search(r'\bav1\b', t):
        result.video_codec = "av1"
    elif re.search(r'x\.?265|h\.?265|hevc', t):
        result.video_codec = "h265"
    elif re.search(r'x\.?264|h\.?264|avc', t):
        result.video_codec = "h264"
    elif re.search(r'xvid|divx', t):
        result.video_codec = "xvid"
    elif re.search(r'mpeg-?2', t):
        result.video_codec = "mpeg2"

    # Source
    if re.search(r'remux', t):
        result.source = "remux"
    elif re.search(r'blu-?ray|bdremux|bdrip', t):
        result.source = "bluray"
    elif re.search(r'web-?dl|webdl', t):
        result.source = "web-dl"
    elif re.search(r'web-?rip|webrip', t):
        result.source = "webrip"
    elif re.search(r'hdtv', t):
        result.source = "hdtv"
    elif re.search(r'dvdrip|dvd', t):
        result.source = "dvdrip"
    elif re.search(r'\bweb\b', t):
        result.source = "web-dl"

    # Audio codec
    if re.search(r'atmos', t):
        result.audio_codec = "atmos"
    elif re.search(r'truehd|true-hd', t):
        result.audio_codec = "truehd"
    elif re.search(r'dts-?hd[\. ]?ma', t):
        result.audio_codec = "dts-hd ma"
    elif re.search(r'dts-?hd', t):
        result.audio_codec = "dts-hd"
    elif re.search(r'dts', t):
        result.audio_codec = "dts"
    elif re.search(r'dd[\+p]?[\. ]?5[\. ]?1|ac3|dolby digital', t):
        result.audio_codec = "dd5.1"
    elif re.search(r'aac', t):
        result.audio_codec = "aac"
    elif re.search(r'flac', t):
        result.audio_codec = "flac"

    # HDR
    if re.search(r'dolby[\. ]?vision|dovi|dv', t):
        result.hdr = "dolby vision"
    elif re.search(r'hdr10\+|hdr10plus', t):
        result.hdr = "hdr10+"
    elif re.search(r'hdr10|hdr', t):
        result.hdr = "hdr10"
    elif re.search(r'\bhlg\b', t):
        result.hdr = "hlg"

    # Release group (after last dash)
    group_match = re.search(r'-([a-zA-Z0-9]+)(?:\.[a-z]{2,4})?$', title)
    if group_match:
        result.group = group_match.group(1)

    return result

def normalize_resolution(res: str) -> str:
    """Normalize various resolution formats to standard form."""
    if not res:
        return "unknown"
    res = res.lower().strip()
    if res in ("4k", "uhd", "2160"):
        return "2160p"
    if res in ("1080",):
        return "1080p"
    if res in ("720",):
        return "720p"
    if res in ("480", "576", "sd"):
        return "480p"
    if res.endswith("p"):
        return res
    return f"{res}p"

def normalize_codec(codec: str) -> str:
    """Normalize codec names."""
    if not codec:
        return "unknown"
    codec = codec.lower().strip()
    aliases = {
        "hevc": "h265", "x265": "h265",
        "avc": "h264", "x264": "h264",
        "divx": "xvid",
    }
    return aliases.get(codec, codec)

def get_resolution_rank(resolution: str) -> int:
    return RESOLUTION_RANK.get(normalize_resolution(resolution), 0)

def get_codec_rank(codec: str) -> int:
    return CODEC_RANK.get(normalize_codec(codec), 0)
```

---

# 13. Backend: Comparison Engine

## 13.1 `backend/core/comparer.py`

```python
"""
Comparison engine — decides whether a candidate release should replace the local file.
Core rule: NEVER increase file size.
"""
from dataclasses import dataclass
from typing import Optional
from backend.core.parser import (
    ParsedRelease, parse_release_title, normalize_resolution, normalize_codec,
    get_resolution_rank, get_codec_rank,
)
from backend.config import get_config

@dataclass
class ComparisonResult:
    decision: str               # "accept" or "reject"
    score: float                # higher = better candidate
    savings_bytes: int
    savings_pct: float
    reject_reason: Optional[str] = None
    notes: str = ""

def compare_release(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidate_size: int,
    candidate_title: str,
) -> ComparisonResult:
    """
    Compare a local file against a candidate release.
    Returns a ComparisonResult with accept/reject and scoring.
    """
    config = get_config()
    parsed = parse_release_title(candidate_title)

    # --- Hard rule: never increase size ---
    if candidate_size >= local_size:
        return ComparisonResult(
            decision="reject",
            score=0,
            savings_bytes=local_size - candidate_size,
            savings_pct=0,
            reject_reason=f"Candidate is not smaller ({_human_size(candidate_size)} >= {_human_size(local_size)})",
        )

    savings_bytes = local_size - candidate_size
    savings_pct = (savings_bytes / local_size) * 100

    # --- Minimum savings threshold ---
    if savings_pct < config.comparison.min_savings_percent:
        return ComparisonResult(
            decision="reject",
            score=0,
            savings_bytes=savings_bytes,
            savings_pct=savings_pct,
            reject_reason=f"Savings {savings_pct:.1f}% below minimum threshold {config.comparison.min_savings_percent}%",
        )

    # --- Resolution check ---
    local_res_rank = get_resolution_rank(local_resolution)
    cand_res = parsed.resolution or "unknown"
    cand_res_rank = get_resolution_rank(cand_res)

    if cand_res_rank < local_res_rank:
        if not config.comparison.allow_resolution_downgrade:
            return ComparisonResult(
                decision="reject",
                score=0,
                savings_bytes=savings_bytes,
                savings_pct=savings_pct,
                reject_reason=f"Resolution downgrade ({local_resolution} → {cand_res}) not allowed",
            )
        if savings_pct < config.comparison.downgrade_min_savings_percent:
            return ComparisonResult(
                decision="reject",
                score=0,
                savings_bytes=savings_bytes,
                savings_pct=savings_pct,
                reject_reason=f"Resolution downgrade requires {config.comparison.downgrade_min_savings_percent}% savings, only {savings_pct:.1f}%",
            )

    # --- Scoring ---
    score = savings_pct  # Base score is percentage savings

    # Codec bonus (better codec = higher score)
    cand_codec = normalize_codec(parsed.video_codec or "")
    local_codec_rank = get_codec_rank(local_codec)
    cand_codec_rank = get_codec_rank(cand_codec)
    codec_delta = cand_codec_rank - local_codec_rank
    score += codec_delta * 0.5  # Weight codec improvement

    # Resolution upgrade bonus
    if cand_res_rank > local_res_rank:
        score += 20  # Big bonus for getting higher res at smaller size

    # Preferred codec bonus
    if cand_codec in config.comparison.preferred_codecs:
        score += 10

    notes_parts = []
    if cand_res_rank > local_res_rank:
        notes_parts.append(f"Resolution upgrade: {local_resolution} → {cand_res}")
    if codec_delta > 0:
        notes_parts.append(f"Codec upgrade: {local_codec} → {cand_codec}")

    return ComparisonResult(
        decision="accept",
        score=round(score, 2),
        savings_bytes=savings_bytes,
        savings_pct=round(savings_pct, 2),
        notes="; ".join(notes_parts),
    )

def rank_candidates(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidates: list[dict],
) -> list[tuple[dict, ComparisonResult]]:
    """
    Compare all candidates, return sorted list of (candidate, result) tuples.
    Only accepted candidates are returned, sorted by score descending.
    """
    results = []
    for cand in candidates:
        result = compare_release(
            local_size=local_size,
            local_resolution=local_resolution,
            local_codec=local_codec,
            candidate_size=cand["size"],
            candidate_title=cand["release_title"],
        )
        results.append((cand, result))

    # Filter to accepted only, sort by score descending
    accepted = [(c, r) for c, r in results if r.decision == "accept"]
    accepted.sort(key=lambda x: x[1].score, reverse=True)
    return accepted

def _human_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
```

---

# 14. Backend: Scanner Module

## 14.1 `backend/core/scanner.py`

The scanner reads the Plex library and enriches each movie with TMDB metadata.

```python
"""
Library scanner — reads Plex, enriches with TMDB, stores in database.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session, Movie
from backend.integrations.plex import PlexClient
from backend.integrations.tmdb import TMDBClient
from backend.core.parser import normalize_resolution, normalize_codec
from backend.realtime.events import emit_event
from loguru import logger

async def scan_library():
    """
    Full library scan:
    1. Get all movies from Plex
    2. For each movie, upsert into database
    3. Fetch TMDB metadata if missing (poster, backdrop, overview)
    4. Emit real-time events for UI updates
    """
    plex = PlexClient()
    tmdb = TMDBClient()
    plex_movies = plex.get_all_movies()

    await emit_event("scan:started", {"total_movies": len(plex_movies)})
    logger.info(f"Scan started: {len(plex_movies)} movies found in Plex")

    async with async_session() as db:
        for i, pm in enumerate(plex_movies):
            try:
                # Upsert movie
                result = await db.execute(
                    select(Movie).where(Movie.plex_rating_key == pm["plex_rating_key"])
                )
                movie = result.scalar_one_or_none()

                if movie is None:
                    movie = Movie(plex_rating_key=pm["plex_rating_key"])
                    db.add(movie)

                # Update file info from Plex
                movie.title = pm["title"]
                movie.year = pm["year"]
                movie.imdb_id = pm["imdb_id"] or movie.imdb_id
                movie.tmdb_id = pm["tmdb_id"] or movie.tmdb_id
                movie.file_path = pm["file_path"]
                movie.file_size = pm["file_size"]
                movie.resolution = normalize_resolution(pm["resolution"] or "")
                movie.video_codec = normalize_codec(pm["video_codec"] or "")
                movie.audio_codec = pm["audio_codec"]
                movie.bitrate = pm["bitrate"]
                movie.last_scanned = datetime.now(timezone.utc)

                # Track original size (only set once, on first scan)
                if movie.original_file_size is None:
                    movie.original_file_size = pm["file_size"]

                # Fetch TMDB metadata if missing
                if not movie.poster_path and (movie.tmdb_id or movie.imdb_id):
                    try:
                        tmdb_data = None
                        if movie.imdb_id:
                            tmdb_data = await tmdb.find_by_imdb(movie.imdb_id)
                        if not tmdb_data and movie.tmdb_id:
                            tmdb_data = await tmdb.get_movie(movie.tmdb_id)
                        if not tmdb_data:
                            tmdb_data = await tmdb.search_movie(movie.title, movie.year)

                        if tmdb_data:
                            movie.tmdb_id = tmdb_data.get("id", movie.tmdb_id)
                            movie.overview = tmdb_data.get("overview")
                            movie.poster_path = tmdb_data.get("poster_path")
                            movie.backdrop_path = tmdb_data.get("backdrop_path")
                            genres = tmdb_data.get("genres") or tmdb_data.get("genre_ids", [])
                            if isinstance(genres, list) and genres:
                                import json
                                if isinstance(genres[0], dict):
                                    movie.genres = json.dumps([g["name"] for g in genres])
                                else:
                                    movie.genres = json.dumps(genres)
                    except Exception as e:
                        logger.warning(f"TMDB lookup failed for {movie.title}: {e}")

                await db.commit()

                await emit_event("scan:progress", {
                    "movie_id": movie.id,
                    "title": movie.title,
                    "current": i + 1,
                    "total": len(plex_movies),
                })

            except Exception as e:
                logger.error(f"Error scanning {pm['title']}: {e}")
                await db.rollback()

    await emit_event("scan:completed", {"total_movies": len(plex_movies)})
    logger.info(f"Scan completed: {len(plex_movies)} movies processed")
```

---

# 15. Backend: Searcher Module

## 15.1 `backend/core/searcher.py`

```python
"""
Usenet release searcher — queries all configured indexers for a specific movie.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session, Movie, SearchResult
from backend.integrations.newznab import NewznabClient
from backend.integrations.prowlarr import ProwlarrClient
from backend.config import get_config
from backend.core.parser import parse_release_title
from backend.core.comparer import compare_release
from backend.realtime.events import emit_event
from loguru import logger

async def search_for_movie(movie_id: int) -> list[dict]:
    """
    Search all configured indexers for alternative releases of a movie.
    Stores results in the database. Returns the list of search results.
    """
    config = get_config()

    async with async_session() as db:
        result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = result.scalar_one_or_none()
        if not movie:
            raise ValueError(f"Movie {movie_id} not found")

        await emit_event("search:started", {"movie_id": movie.id, "title": movie.title})
        logger.info(f"Searching for: {movie.title} ({movie.year})")

        all_results = []

        # --- Option 1: Use Prowlarr (if enabled) ---
        if config.prowlarr.enabled:
            try:
                prowlarr = ProwlarrClient()
                query = f"{movie.title} {movie.year}" if movie.year else movie.title
                results = await prowlarr.search(query=query, imdb_id=movie.imdb_id or "")
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Prowlarr search failed: {e}")

        # --- Option 2: Query indexers directly ---
        else:
            for indexer_cfg in config.indexers:
                try:
                    client = NewznabClient(indexer_cfg)
                    if movie.imdb_id:
                        results = await client.search_by_imdb(movie.imdb_id)
                    else:
                        query = f"{movie.title} {movie.year}" if movie.year else movie.title
                        results = await client.search_by_query(query)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Indexer {indexer_cfg.name} search failed: {e}")

        logger.info(f"Found {len(all_results)} results for {movie.title}")

        # --- Score and store each result ---
        stored_results = []
        for r in all_results:
            parsed = parse_release_title(r["release_title"])
            comparison = compare_release(
                local_size=movie.file_size or 0,
                local_resolution=movie.resolution or "",
                local_codec=movie.video_codec or "",
                candidate_size=r["size"],
                candidate_title=r["release_title"],
            )

            sr = SearchResult(
                movie_id=movie.id,
                indexer_name=r["indexer_name"],
                release_title=r["release_title"],
                nzb_url=r["nzb_url"],
                size=r["size"],
                resolution=parsed.resolution,
                video_codec=parsed.video_codec,
                audio_codec=parsed.audio_codec,
                source=parsed.source,
                savings_bytes=comparison.savings_bytes,
                savings_pct=comparison.savings_pct,
                score=comparison.score,
                decision=comparison.decision,
                reject_reason=comparison.reject_reason,
            )
            db.add(sr)
            stored_results.append(sr)

        # Update movie search timestamp
        movie.last_searched = datetime.now(timezone.utc)
        await db.commit()

        accepted_count = sum(1 for sr in stored_results if sr.decision == "accept")
        best_savings = max((sr.savings_pct for sr in stored_results if sr.decision == "accept"), default=0)

        await emit_event("search:results", {
            "movie_id": movie.id,
            "title": movie.title,
            "total_results": len(stored_results),
            "accepted_count": accepted_count,
            "best_savings_pct": best_savings,
        })

        return [{"id": sr.id, "release_title": sr.release_title, "size": sr.size,
                 "decision": sr.decision, "score": sr.score, "savings_pct": sr.savings_pct}
                for sr in stored_results]
```

---

# 16. Backend: Downloader & Replacer

## 16.1 `backend/core/downloader.py`

```python
"""
Download orchestration — sends NZB to SABnzbd, monitors progress, waits for completion.
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session, Movie, SearchResult, Download
from backend.integrations.sabnzbd import SABnzbdClient
from backend.realtime.events import emit_event
from loguru import logger

async def start_download(movie_id: int, search_result_id: int) -> int:
    """
    Send the selected NZB to SABnzbd and create a Download record.
    Returns the download ID.
    """
    sab = SABnzbdClient()

    async with async_session() as db:
        movie = (await db.execute(select(Movie).where(Movie.id == movie_id))).scalar_one()
        sr = (await db.execute(select(SearchResult).where(SearchResult.id == search_result_id))).scalar_one()

        # Send to SABnzbd
        nzo_id = await sab.add_nzb_url(sr.nzb_url, title=f"{movie.title} ({movie.year})")
        logger.info(f"Sent to SABnzbd: {movie.title} -> nzo_id={nzo_id}")

        # Create download record
        download = Download(
            movie_id=movie.id,
            search_result_id=sr.id,
            sabnzbd_nzo_id=nzo_id,
            status="downloading",
            old_file_path=movie.file_path,
            old_file_size=movie.file_size,
            started_at=datetime.now(timezone.utc),
        )
        db.add(download)

        # Update movie status
        movie.status = "downloading"
        await db.commit()

        await emit_event("download:started", {
            "movie_id": movie.id,
            "title": movie.title,
            "release": sr.release_title,
        })

        return download.id

async def monitor_download(download_id: int) -> dict:
    """
    Poll SABnzbd until the download completes or fails.
    Emits progress events. Returns final status dict.
    """
    sab = SABnzbdClient()

    async with async_session() as db:
        download = (await db.execute(select(Download).where(Download.id == download_id))).scalar_one()

        while True:
            status = await sab.get_job_status(download.sabnzbd_nzo_id)

            if status is None:
                # Job vanished — error
                download.status = "failed"
                download.error_message = "Job not found in SABnzbd queue or history"
                await db.commit()
                return {"status": "failed", "error": download.error_message}

            if status["location"] == "queue":
                # Still downloading
                download.progress = status["percentage"]
                download.speed = status.get("speed", "")
                download.eta = status.get("timeleft", "")
                download.status = "downloading"
                await db.commit()

                await emit_event("download:progress", {
                    "movie_id": download.movie_id,
                    "download_id": download.id,
                    "progress": status["percentage"],
                    "speed": status.get("speed", ""),
                    "eta": status.get("timeleft", ""),
                })

            elif status["location"] == "history":
                # Completed or failed
                if status["status"] == "Completed":
                    download.status = "completed"
                    download.new_file_path = status.get("storage", "")
                    download.completed_at = datetime.now(timezone.utc)
                    download.progress = 100.0
                    await db.commit()

                    await emit_event("download:completed", {
                        "movie_id": download.movie_id,
                        "title": f"Download {download.id}",
                    })
                    return {"status": "completed", "storage": status.get("storage", "")}
                else:
                    download.status = "failed"
                    download.error_message = f"SABnzbd status: {status['status']}"
                    await db.commit()

                    await emit_event("download:failed", {
                        "movie_id": download.movie_id,
                        "title": f"Download {download.id}",
                        "error": download.error_message,
                    })
                    return {"status": "failed", "error": download.error_message}

            await asyncio.sleep(5)  # Poll every 5 seconds
```

## 16.2 `backend/core/replacer.py`

```python
"""
File replacer — safely swaps the old file with the downloaded one.
Follows the pattern: verify → recycle old → move new → refresh Plex.
"""
import os
import shutil
import subprocess
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database import async_session, Movie, Download, ActivityLog
from backend.integrations.plex import PlexClient
from backend.config import get_config
from backend.realtime.events import emit_event
from loguru import logger

async def replace_file(download_id: int) -> bool:
    """
    Replace the old movie file with the downloaded one.
    Returns True on success, False on failure.
    """
    config = get_config()

    async with async_session() as db:
        download = (await db.execute(select(Download).where(Download.id == download_id))).scalar_one()
        movie = (await db.execute(select(Movie).where(Movie.id == download.movie_id))).scalar_one()

        old_path = download.old_file_path
        download_dir = download.new_file_path  # SABnzbd storage directory

        if not download_dir or not os.path.exists(download_dir):
            download.status = "failed"
            download.error_message = f"Download directory not found: {download_dir}"
            movie.status = "error"
            movie.error_message = download.error_message
            await db.commit()
            return False

        # --- Step 1: Find the video file in the download directory ---
        video_extensions = {".mkv", ".mp4", ".avi", ".m4v", ".wmv"}
        video_files = []
        for root, dirs, files in os.walk(download_dir):
            for f in files:
                if os.path.splitext(f)[1].lower() in video_extensions:
                    video_files.append(os.path.join(root, f))

        if not video_files:
            download.status = "failed"
            download.error_message = "No video file found in download"
            movie.status = "error"
            movie.error_message = download.error_message
            await db.commit()
            return False

        # Pick the largest video file (the main movie)
        new_file = max(video_files, key=os.path.getsize)
        new_size = os.path.getsize(new_file)

        # --- Step 2: Verify the new file (optional) ---
        if config.files.verify_after_download:
            if not _verify_video_file(new_file):
                download.status = "failed"
                download.error_message = "Downloaded file failed integrity check"
                movie.status = "error"
                movie.error_message = download.error_message
                await db.commit()
                return False

        # --- Step 3: Final size check (safety net) ---
        if new_size >= (download.old_file_size or 0):
            download.status = "failed"
            download.error_message = f"New file ({new_size}) is not smaller than old file ({download.old_file_size})"
            movie.status = "error"
            movie.error_message = download.error_message
            await db.commit()
            return False

        # --- Step 4: Move old file to recycling bin ---
        if old_path and os.path.exists(old_path):
            recycle_dir = config.files.recycling_bin
            os.makedirs(recycle_dir, exist_ok=True)
            recycled_name = os.path.basename(old_path)
            recycled_path = os.path.join(recycle_dir, recycled_name)
            # Avoid overwriting in recycling bin
            if os.path.exists(recycled_path):
                base, ext = os.path.splitext(recycled_name)
                recycled_path = os.path.join(recycle_dir, f"{base}_{int(datetime.now().timestamp())}{ext}")
            shutil.move(old_path, recycled_path)
            logger.info(f"Moved old file to recycling bin: {recycled_path}")

        # --- Step 5: Move new file to library ---
        # Put the new file in the same directory as the old one, preserving the directory structure
        target_dir = os.path.dirname(old_path) if old_path else download_dir
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, os.path.basename(new_file))
        shutil.move(new_file, target_path)
        logger.info(f"Placed new file: {target_path}")

        # --- Step 6: Update database ---
        savings = (download.old_file_size or 0) - new_size
        download.new_file_path = target_path
        download.new_file_size = new_size
        download.savings_bytes = savings
        download.status = "replaced"

        movie.file_path = target_path
        movie.file_size = new_size
        movie.total_savings += savings
        movie.times_replaced += 1
        movie.status = "replaced"
        movie.error_message = None

        # Activity log
        log_entry = ActivityLog(
            movie_id=movie.id,
            action="replaced",
            detail=f"Replaced: {_human_size(download.old_file_size or 0)} → {_human_size(new_size)} (saved {_human_size(savings)})",
            old_size=download.old_file_size,
            new_size=new_size,
            savings_bytes=savings,
        )
        db.add(log_entry)
        await db.commit()

        # --- Step 7: Trigger Plex library refresh ---
        try:
            plex = PlexClient()
            plex.refresh_library()
            logger.info("Plex library refresh triggered")
        except Exception as e:
            logger.warning(f"Plex refresh failed (non-fatal): {e}")

        # --- Step 8: Clean up SABnzbd download directory ---
        try:
            shutil.rmtree(download_dir, ignore_errors=True)
        except Exception:
            pass

        await emit_event("replace:completed", {
            "movie_id": movie.id,
            "title": movie.title,
            "old_size": download.old_file_size,
            "new_size": new_size,
            "savings_pct": round((savings / (download.old_file_size or 1)) * 100, 1),
        })

        logger.info(f"REPLACED: {movie.title} — {_human_size(download.old_file_size or 0)} → {_human_size(new_size)}")
        return True

def _verify_video_file(file_path: str) -> bool:
    """Basic integrity check using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", file_path],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0 and len(result.stdout.strip()) > 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # ffprobe not installed or timed out — skip verification
        return True

def _human_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
```

---

# 17. Backend: Orchestrator / Job Queue

## 17.1 `backend/core/orchestrator.py`

The master coordinator. Processes movies one at a time: scan → search → compare → download → replace → next.

```python
"""
Orchestrator — one-at-a-time sequential movie processing.
This is the heart of Slimarr. It coordinates scanner, searcher, comparer,
downloader, and replacer into a single pipeline.
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, or_
from backend.database import async_session, Movie, SearchResult, ActivityLog
from backend.core.scanner import scan_library
from backend.core.searcher import search_for_movie
from backend.core.comparer import rank_candidates
from backend.core.downloader import start_download, monitor_download
from backend.core.replacer import replace_file
from backend.config import get_config
from backend.realtime.events import emit_event
from loguru import logger

# Global state
_running = False
_current_movie_id = None
_stop_requested = False

async def run_full_cycle():
    """
    Run a full optimization cycle:
    1. Scan library (refresh from Plex + TMDB)
    2. For each unprocessed movie: search → compare → download → replace
    """
    global _running, _current_movie_id, _stop_requested
    if _running:
        logger.warning("Orchestrator already running, skipping")
        return

    _running = True
    _stop_requested = False
    config = get_config()

    try:
        # Step 1: Scan library
        await scan_library()

        # Step 2: Get movies to process
        async with async_session() as db:
            result = await db.execute(
                select(Movie)
                .where(or_(Movie.status == "pending", Movie.status == "error"))
                .where(Movie.file_size > (config.comparison.minimum_file_size_mb * 1024 * 1024))
                .order_by(Movie.file_size.desc())  # Process largest files first (most savings potential)
            )
            movies = result.scalars().all()

        logger.info(f"Orchestrator: {len(movies)} movies to process")

        for movie in movies:
            if _stop_requested:
                logger.info("Orchestrator: stop requested, halting")
                break

            await process_single_movie(movie.id)

            # Throttle between movies
            if config.schedule.throttle_seconds > 0:
                await asyncio.sleep(config.schedule.throttle_seconds)

    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
    finally:
        _running = False
        _current_movie_id = None

async def process_single_movie(movie_id: int):
    """Process a single movie through the full pipeline."""
    global _current_movie_id
    _current_movie_id = movie_id

    async with async_session() as db:
        movie = (await db.execute(select(Movie).where(Movie.id == movie_id))).scalar_one_or_none()
        if not movie:
            return

        logger.info(f"Processing: {movie.title} ({movie.year}) — {_human_size(movie.file_size or 0)}")

        try:
            # --- SEARCH ---
            movie.status = "searching"
            await db.commit()

            search_results = await search_for_movie(movie.id)

            # --- COMPARE ---
            await db.refresh(movie)
            accepted = [r for r in search_results if r["decision"] == "accept"]

            if not accepted:
                movie.status = "optimal"
                db.add(ActivityLog(
                    movie_id=movie.id,
                    action="optimal",
                    detail=f"No smaller release found ({len(search_results)} candidates checked)",
                ))
                await db.commit()
                logger.info(f"OPTIMAL: {movie.title} — no smaller release found")
                return

            # Get the best candidate (highest score)
            best = max(accepted, key=lambda x: x["score"])
            logger.info(
                f"BEST CANDIDATE: {movie.title} — savings {best['savings_pct']:.1f}%, "
                f"score {best['score']}"
            )

            # --- DOWNLOAD ---
            download_id = await start_download(movie.id, best["id"])

            # --- MONITOR ---
            result = await monitor_download(download_id)

            if result["status"] != "completed":
                movie.status = "error"
                movie.error_message = result.get("error", "Download failed")
                await db.commit()
                return

            # --- REPLACE ---
            success = await replace_file(download_id)
            if not success:
                logger.error(f"REPLACE FAILED: {movie.title}")
                # Movie status already set to error in replace_file

        except Exception as e:
            logger.error(f"Error processing {movie.title}: {e}")
            movie.status = "error"
            movie.error_message = str(e)
            await db.commit()

    _current_movie_id = None

def stop_orchestrator():
    """Request the orchestrator to stop after current movie."""
    global _stop_requested
    _stop_requested = True

def get_orchestrator_status() -> dict:
    return {
        "running": _running,
        "current_movie_id": _current_movie_id,
        "stop_requested": _stop_requested,
    }

def _human_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
```

---

# 18. Backend: Scheduler

## 18.1 `backend/scheduler/scheduler.py`

```python
"""
APScheduler setup — handles nightly, continuous, and manual scheduling modes.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.config import SlimarrConfig
from loguru import logger

_scheduler: AsyncIOScheduler = None

def start_scheduler(config: SlimarrConfig):
    global _scheduler
    _scheduler = AsyncIOScheduler()

    if config.schedule.mode == "nightly":
        # Parse start time
        hour, minute = map(int, config.schedule.start_time.split(":"))

        # Convert day names to cron day_of_week
        day_map = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
                   "fri": "fri", "sat": "sat", "sun": "sun"}
        days = ",".join(day_map[d] for d in config.schedule.days if d in day_map)

        _scheduler.add_job(
            _run_nightly_cycle,
            trigger=CronTrigger(hour=hour, minute=minute, day_of_week=days),
            id="nightly_scan",
            name="Nightly Optimization Cycle",
            replace_existing=True,
        )
        logger.info(f"Scheduler: nightly mode at {config.schedule.start_time} on {days}")

    elif config.schedule.mode == "continuous":
        # Run immediately and keep going
        _scheduler.add_job(
            _run_continuous_cycle,
            trigger="interval",
            minutes=1,  # Check every minute if orchestrator should restart
            id="continuous_scan",
            name="Continuous Optimization",
            replace_existing=True,
        )
        logger.info("Scheduler: continuous mode")

    elif config.schedule.mode == "manual":
        logger.info("Scheduler: manual mode (no automatic scheduling)")

    # Recycling bin cleanup — daily at 4 AM
    _scheduler.add_job(
        _cleanup_recycling_bin,
        trigger=CronTrigger(hour=4, minute=0),
        id="recycle_cleanup",
        name="Recycling Bin Cleanup",
        replace_existing=True,
    )

    _scheduler.start()

def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)

async def _run_nightly_cycle():
    from backend.core.orchestrator import run_full_cycle
    logger.info("Nightly cycle triggered by scheduler")
    await run_full_cycle()

async def _run_continuous_cycle():
    from backend.core.orchestrator import run_full_cycle, get_orchestrator_status
    status = get_orchestrator_status()
    if not status["running"]:
        await run_full_cycle()

async def _cleanup_recycling_bin():
    """Remove old files from recycling bin."""
    import os
    import time
    from backend.config import get_config
    config = get_config()
    recycle_dir = config.files.recycling_bin
    if not os.path.exists(recycle_dir):
        return
    max_age_seconds = config.files.recycling_bin_cleanup_days * 86400
    now = time.time()
    for f in os.listdir(recycle_dir):
        path = os.path.join(recycle_dir, f)
        if os.path.isfile(path) and (now - os.path.getmtime(path)) > max_age_seconds:
            os.remove(path)
            logger.info(f"Recycling bin cleanup: removed {f}")

def get_scheduled_tasks() -> list[dict]:
    """Return list of scheduled tasks for the System page."""
    if not _scheduler:
        return []
    tasks = []
    for job in _scheduler.get_jobs():
        tasks.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return tasks
```

---

# 19. Backend: API Routes — Complete Specification

## 19.1 `backend/api/dashboard.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from backend.database import get_db, Movie, Download, ActivityLog, AsyncSession
from backend.auth.dependencies import get_current_user

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    GET /api/v1/dashboard/stats
    Returns: {
        total_movies: int,
        optimal_count: int,
        replaced_count: int,
        pending_count: int,
        error_count: int,
        total_library_size: int,       // bytes
        total_savings: int,            // bytes
        total_original_size: int,      // bytes (what the library was before Slimarr)
    }
    """
    total = (await db.execute(select(func.count(Movie.id)))).scalar() or 0
    optimal = (await db.execute(select(func.count(Movie.id)).where(Movie.status == "optimal"))).scalar() or 0
    replaced = (await db.execute(select(func.count(Movie.id)).where(Movie.status == "replaced"))).scalar() or 0
    pending = (await db.execute(select(func.count(Movie.id)).where(Movie.status == "pending"))).scalar() or 0
    error = (await db.execute(select(func.count(Movie.id)).where(Movie.status == "error"))).scalar() or 0
    total_size = (await db.execute(select(func.sum(Movie.file_size)))).scalar() or 0
    total_savings = (await db.execute(select(func.sum(Movie.total_savings)))).scalar() or 0
    total_original = (await db.execute(select(func.sum(Movie.original_file_size)))).scalar() or 0

    return {
        "total_movies": total,
        "optimal_count": optimal,
        "replaced_count": replaced,
        "pending_count": pending,
        "error_count": error,
        "total_library_size": total_size,
        "total_savings": total_savings,
        "total_original_size": total_original,
    }

@router.get("/savings-history")
async def get_savings_history(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    GET /api/v1/dashboard/savings-history
    Returns cumulative savings over time for the area chart.
    Returns: [{ date: "2026-01-15", cumulative_savings: 1234567890 }, ...]
    """
    result = await db.execute(
        select(
            func.date(ActivityLog.created_at).label("date"),
            func.sum(ActivityLog.savings_bytes).label("daily_savings"),
        )
        .where(ActivityLog.action == "replaced")
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
    )
    rows = result.all()

    # Build cumulative
    history = []
    cumulative = 0
    for row in rows:
        cumulative += row.daily_savings or 0
        history.append({"date": str(row.date), "cumulative_savings": cumulative})

    return history

@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    GET /api/v1/dashboard/recent-activity?limit=10
    Returns the most recent activity log entries.
    """
    result = await db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "movie_id": log.movie_id,
            "action": log.action,
            "detail": log.detail,
            "old_size": log.old_size,
            "new_size": log.new_size,
            "savings_bytes": log.savings_bytes,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
```

## 19.2 `backend/api/library.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from backend.database import get_db, Movie, SearchResult, ActivityLog, AsyncSession
from backend.auth.dependencies import get_current_user

router = APIRouter()

@router.get("/movies")
async def list_movies(
    status: str = Query(None, description="Filter by status: pending, optimal, replaced, error"),
    sort: str = Query("title", description="Sort by: title, size, savings, year, updated"),
    order: str = Query("asc", description="Sort order: asc, desc"),
    search: str = Query(None, description="Search by movie title"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    GET /api/v1/library/movies?status=pending&sort=size&order=desc&page=1&per_page=50
    Returns paginated movie list for the library grid/table.
    """
    query = select(Movie)

    if status:
        query = query.where(Movie.status == status)
    if search:
        query = query.where(Movie.title.ilike(f"%{search}%"))

    # Sorting
    sort_map = {
        "title": Movie.title,
        "size": Movie.file_size,
        "savings": Movie.total_savings,
        "year": Movie.year,
        "updated": Movie.updated_at,
    }
    sort_col = sort_map.get(sort, Movie.title)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    # Pagination
    total = (await db.execute(select(func.count(Movie.id)).where(query.whereclause) if query.whereclause is not None else select(func.count(Movie.id)))).scalar() or 0
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    movies = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "movies": [_movie_to_dict(m) for m in movies],
    }

@router.get("/movies/{movie_id}")
async def get_movie_detail(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    GET /api/v1/library/movies/123
    Returns full movie detail for the movie detail page.
    """
    movie = (await db.execute(select(Movie).where(Movie.id == movie_id))).scalar_one_or_none()
    if not movie:
        raise HTTPException(404, "Movie not found")

    # Get search results
    search_results = (await db.execute(
        select(SearchResult)
        .where(SearchResult.movie_id == movie_id)
        .order_by(SearchResult.score.desc())
    )).scalars().all()

    # Get history
    history = (await db.execute(
        select(ActivityLog)
        .where(ActivityLog.movie_id == movie_id)
        .order_by(ActivityLog.created_at.desc())
    )).scalars().all()

    return {
        **_movie_to_dict(movie),
        "search_results": [
            {
                "id": sr.id,
                "indexer_name": sr.indexer_name,
                "release_title": sr.release_title,
                "size": sr.size,
                "resolution": sr.resolution,
                "video_codec": sr.video_codec,
                "source": sr.source,
                "savings_bytes": sr.savings_bytes,
                "savings_pct": sr.savings_pct,
                "score": sr.score,
                "decision": sr.decision,
                "reject_reason": sr.reject_reason,
                "searched_at": sr.searched_at.isoformat(),
            }
            for sr in search_results
        ],
        "history": [
            {
                "id": h.id,
                "action": h.action,
                "detail": h.detail,
                "old_size": h.old_size,
                "new_size": h.new_size,
                "savings_bytes": h.savings_bytes,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ],
    }

@router.post("/movies/{movie_id}/search")
async def trigger_manual_search(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """
    POST /api/v1/library/movies/123/search
    Trigger an on-demand indexer search for this movie (like Radarr's interactive search).
    """
    from backend.core.searcher import search_for_movie
    results = await search_for_movie(movie_id)
    return {"results": results}

@router.post("/movies/{movie_id}/process")
async def trigger_process_movie(
    movie_id: int,
    user: str = Depends(get_current_user),
):
    """
    POST /api/v1/library/movies/123/process
    Trigger full pipeline (search → compare → download → replace) for one movie.
    Runs asynchronously.
    """
    import asyncio
    from backend.core.orchestrator import process_single_movie
    asyncio.create_task(process_single_movie(movie_id))
    return {"status": "started", "movie_id": movie_id}

def _movie_to_dict(movie: Movie) -> dict:
    return {
        "id": movie.id,
        "plex_rating_key": movie.plex_rating_key,
        "title": movie.title,
        "year": movie.year,
        "imdb_id": movie.imdb_id,
        "tmdb_id": movie.tmdb_id,
        "overview": movie.overview,
        "poster_url": f"/api/v1/images/{movie.id}/poster.jpg" if movie.poster_path else None,
        "fanart_url": f"/api/v1/images/{movie.id}/fanart.jpg" if movie.backdrop_path else None,
        "genres": movie.genres,
        "file_path": movie.file_path,
        "file_size": movie.file_size,
        "resolution": movie.resolution,
        "video_codec": movie.video_codec,
        "audio_codec": movie.audio_codec,
        "bitrate": movie.bitrate,
        "source_type": movie.source_type,
        "original_file_size": movie.original_file_size,
        "total_savings": movie.total_savings,
        "times_replaced": movie.times_replaced,
        "status": movie.status,
        "error_message": movie.error_message,
        "last_scanned": movie.last_scanned.isoformat() if movie.last_scanned else None,
        "last_searched": movie.last_searched.isoformat() if movie.last_searched else None,
    }
```

## 19.3 `backend/api/settings.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from backend.auth.dependencies import get_current_user
from backend.config import get_config, save_config

router = APIRouter()

@router.get("/")
async def get_all_settings(user: str = Depends(get_current_user)):
    """GET /api/v1/settings — return full config (with API keys masked)."""
    config = get_config()
    d = config.model_dump()
    # Mask sensitive values
    if d.get("plex", {}).get("token"):
        d["plex"]["token"] = "••••••••"
    if d.get("sabnzbd", {}).get("api_key"):
        d["sabnzbd"]["api_key"] = "••••••••"
    if d.get("tmdb", {}).get("api_key"):
        d["tmdb"]["api_key"] = "••••••••"
    for idx in d.get("indexers", []):
        if idx.get("api_key"):
            idx["api_key"] = "••••••••"
    if d.get("prowlarr", {}).get("api_key"):
        d["prowlarr"]["api_key"] = "••••••••"
    if d.get("radarr", {}).get("api_key"):
        d["radarr"]["api_key"] = "••••••••"
    if d.get("auth", {}).get("secret_key"):
        d["auth"]["secret_key"] = "••••••••"
    if d.get("auth", {}).get("api_key"):
        d["auth"]["api_key"] = d["auth"]["api_key"][:8] + "••••••••"  # Show prefix for identification
    return d

class UpdateSettingsRequest(BaseModel):
    section: str           # "plex", "sabnzbd", "tmdb", "comparison", etc.
    values: dict           # The key-value pairs to update

@router.put("/")
async def update_settings(
    body: UpdateSettingsRequest,
    user: str = Depends(get_current_user),
):
    """PUT /api/v1/settings — update a configuration section."""
    config = get_config()
    section = getattr(config, body.section, None)
    if section is None:
        return {"error": f"Unknown section: {body.section}"}

    for key, value in body.values.items():
        if value == "••••••••":
            continue  # Skip masked values (don't overwrite with mask)
        if hasattr(section, key):
            setattr(section, key, value)

    save_config(config)
    return {"status": "saved"}

@router.post("/test/{service}")
async def test_connection(
    service: str,
    user: str = Depends(get_current_user),
):
    """
    POST /api/v1/settings/test/plex
    POST /api/v1/settings/test/sabnzbd
    POST /api/v1/settings/test/tmdb
    POST /api/v1/settings/test/prowlarr
    POST /api/v1/settings/test/radarr
    POST /api/v1/settings/test/indexer/{name}
    """
    if service == "plex":
        from backend.integrations.plex import PlexClient
        return PlexClient().test_connection()
    elif service == "sabnzbd":
        from backend.integrations.sabnzbd import SABnzbdClient
        return await SABnzbdClient().test_connection()
    elif service == "tmdb":
        from backend.integrations.tmdb import TMDBClient
        try:
            client = TMDBClient()
            result = await client.search_movie("The Matrix", 1999)
            return {"success": True, "test_result": result.get("title", "OK") if result else "No results"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    elif service == "prowlarr":
        from backend.integrations.prowlarr import ProwlarrClient
        return await ProwlarrClient().test_connection()
    elif service == "radarr":
        from backend.integrations.radarr import RadarrClient
        return await RadarrClient().test_connection()
    else:
        # Test a specific indexer by name
        config = get_config()
        for idx in config.indexers:
            if idx.name.lower() == service.lower():
                from backend.integrations.newznab import NewznabClient
                return await NewznabClient(idx).test_connection()
        return {"success": False, "error": f"Unknown service: {service}"}
```

## 19.4 `backend/api/system.py`

```python
from fastapi import APIRouter, Depends
from backend.auth.dependencies import get_current_user
from backend.config import get_config

router = APIRouter()

@router.get("/health")
async def get_health(user: str = Depends(get_current_user)):
    """
    GET /api/v1/system/health
    Check all integrations and return health status.
    """
    config = get_config()
    checks = []

    # Plex
    if config.plex.url:
        from backend.integrations.plex import PlexClient
        result = PlexClient().test_connection()
        checks.append({"service": "Plex", "status": "ok" if result["success"] else "error", "detail": result})

    # SABnzbd
    if config.sabnzbd.url:
        from backend.integrations.sabnzbd import SABnzbdClient
        result = await SABnzbdClient().test_connection()
        checks.append({"service": "SABnzbd", "status": "ok" if result["success"] else "error", "detail": result})

    # TMDB
    if config.tmdb.api_key:
        from backend.integrations.tmdb import TMDBClient
        try:
            await TMDBClient().search_movie("test")
            checks.append({"service": "TMDB", "status": "ok", "detail": {"success": True}})
        except Exception as e:
            checks.append({"service": "TMDB", "status": "error", "detail": {"success": False, "error": str(e)}})

    # Indexers
    for idx in config.indexers:
        from backend.integrations.newznab import NewznabClient
        result = await NewznabClient(idx).test_connection()
        checks.append({"service": idx.name, "status": "ok" if result["success"] else "error", "detail": result})

    # Prowlarr
    if config.prowlarr.enabled and config.prowlarr.url:
        from backend.integrations.prowlarr import ProwlarrClient
        result = await ProwlarrClient().test_connection()
        checks.append({"service": "Prowlarr", "status": "ok" if result["success"] else "error", "detail": result})

    return {"checks": checks}

@router.get("/tasks")
async def get_tasks(user: str = Depends(get_current_user)):
    """GET /api/v1/system/tasks — list scheduled tasks."""
    from backend.scheduler.scheduler import get_scheduled_tasks
    return {"tasks": get_scheduled_tasks()}

@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str, user: str = Depends(get_current_user)):
    """POST /api/v1/system/tasks/nightly_scan/run — trigger a task immediately."""
    import asyncio
    if task_id == "nightly_scan":
        from backend.core.orchestrator import run_full_cycle
        asyncio.create_task(run_full_cycle())
        return {"status": "started"}
    return {"error": f"Unknown task: {task_id}"}

@router.get("/status")
async def get_system_status(user: str = Depends(get_current_user)):
    """GET /api/v1/system/status — orchestrator status + system info."""
    from backend.core.orchestrator import get_orchestrator_status
    import os
    return {
        "orchestrator": get_orchestrator_status(),
        "version": "0.1.0",
        "data_dir": os.path.abspath("data"),
        "config_path": os.path.abspath("config.yaml"),
    }
```

## 19.5 `backend/api/queue.py` and `backend/api/activity.py`

```python
# queue.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from backend.database import get_db, Download, Movie, AsyncSession
from backend.auth.dependencies import get_current_user

router = APIRouter()

@router.get("/")
async def get_queue(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """GET /api/v1/queue — active and recent downloads."""
    result = await db.execute(
        select(Download, Movie)
        .join(Movie, Download.movie_id == Movie.id)
        .where(Download.status.in_(["queued", "downloading", "extracting", "completed"]))
        .order_by(Download.started_at.desc())
        .limit(50)
    )
    items = result.all()
    return {
        "queue": [
            {
                "download_id": dl.id,
                "movie_id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "poster_url": f"/api/v1/images/{movie.id}/poster.jpg" if movie.poster_path else None,
                "status": dl.status,
                "progress": dl.progress,
                "speed": dl.speed,
                "eta": dl.eta,
                "old_size": dl.old_file_size,
                "new_size": dl.new_file_size,
                "savings_bytes": dl.savings_bytes,
                "started_at": dl.started_at.isoformat() if dl.started_at else None,
            }
            for dl, movie in items
        ]
    }
```

```python
# activity.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from backend.database import get_db, ActivityLog, Movie, AsyncSession
from backend.auth.dependencies import get_current_user

router = APIRouter()

@router.get("/")
async def get_activity(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    db: AsyncSession = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """GET /api/v1/activity?page=1&per_page=50&action=replaced"""
    query = select(ActivityLog, Movie).outerjoin(Movie, ActivityLog.movie_id == Movie.id)
    if action:
        query = query.where(ActivityLog.action == action)
    query = query.order_by(ActivityLog.created_at.desc())

    total_query = select(func.count(ActivityLog.id))
    if action:
        total_query = total_query.where(ActivityLog.action == action)
    total = (await db.execute(total_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": log.id,
                "movie_id": log.movie_id,
                "movie_title": movie.title if movie else None,
                "movie_year": movie.year if movie else None,
                "poster_url": f"/api/v1/images/{movie.id}/poster.jpg" if movie and movie.poster_path else None,
                "action": log.action,
                "detail": log.detail,
                "old_size": log.old_size,
                "new_size": log.new_size,
                "savings_bytes": log.savings_bytes,
                "created_at": log.created_at.isoformat(),
            }
            for log, movie in items
        ],
    }
```

---

# 20. Backend: Radarr Integration (Optional)

## 20.1 `backend/integrations/radarr.py`

```python
"""Radarr API v3 client — optional integration for metadata enrichment."""
import httpx
from backend.config import get_config

class RadarrClient:
    def __init__(self):
        config = get_config()
        self.url = config.radarr.url.rstrip("/")
        self.api_key = config.radarr.api_key

    async def _get(self, endpoint: str, params: dict = None) -> dict | list:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3{endpoint}",
                params=params,
                headers={"X-Api-Key": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_movies(self) -> list[dict]:
        return await self._get("/movie")

    async def get_movie(self, radarr_id: int) -> dict:
        return await self._get(f"/movie/{radarr_id}")

    async def search_releases(self, movie_id: int) -> list[dict]:
        """Search all Radarr-configured indexers for a movie."""
        return await self._get("/release", {"movieId": movie_id})

    async def test_connection(self) -> dict:
        try:
            status = await self._get("/system/status")
            movies = await self._get("/movie")
            return {
                "success": True,
                "version": status.get("version", "unknown"),
                "movie_count": len(movies),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

# 21. Backend: Windows Service

## 21.1 `backend/service/windows_service.py`

```python
"""
Windows service wrapper using NSSM.
Provides CLI commands: --install-service, --uninstall-service, --start-service, --stop-service
"""
import subprocess
import sys
import os

SERVICE_NAME = "Slimarr"
DISPLAY_NAME = "Slimarr - Plex Library Optimizer"
DESCRIPTION = "Automatically finds smaller, better-compressed copies of movies in your Plex library"

def get_python_path() -> str:
    return sys.executable

def get_main_script() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))

def install_service():
    """Install Slimarr as a Windows service using NSSM."""
    nssm = _find_nssm()
    python = get_python_path()
    script = get_main_script()

    subprocess.run([nssm, "install", SERVICE_NAME, python, script], check=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "AppDirectory", os.path.dirname(os.path.dirname(script))], check=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "DisplayName", DISPLAY_NAME], check=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "Description", DESCRIPTION], check=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "Start", "SERVICE_AUTO_START"], check=True)
    # Redirect stdout/stderr to log files
    log_dir = os.path.abspath("data/logs")
    os.makedirs(log_dir, exist_ok=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "AppStdout", os.path.join(log_dir, "service_stdout.log")], check=True)
    subprocess.run([nssm, "set", SERVICE_NAME, "AppStderr", os.path.join(log_dir, "service_stderr.log")], check=True)
    print(f"Service '{SERVICE_NAME}' installed. Start with: nssm start {SERVICE_NAME}")

def uninstall_service():
    nssm = _find_nssm()
    subprocess.run([nssm, "stop", SERVICE_NAME], check=False)
    subprocess.run([nssm, "remove", SERVICE_NAME, "confirm"], check=True)
    print(f"Service '{SERVICE_NAME}' removed.")

def _find_nssm() -> str:
    """Find nssm.exe on PATH or in common locations."""
    for path in [
        "nssm",
        r"C:\nssm\nssm.exe",
        r"C:\tools\nssm\nssm.exe",
        os.path.join(os.path.dirname(__file__), "..", "..", "nssm.exe"),
    ]:
        try:
            subprocess.run([path, "version"], capture_output=True, check=True)
            return path
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    raise FileNotFoundError(
        "NSSM not found. Download from https://nssm.cc/download and add to PATH."
    )
```

---

# 22. Frontend: Project Setup

## 22.1 `frontend/vite.config.ts`

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:9494",
        changeOrigin: true,
      },
      "/socket.io": {
        target: "http://localhost:9494",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
```

## 22.2 `frontend/tailwind.config.js`

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Slimarr brand colors (from logo)
        slimarr: {
          green: "#4CAF50",
          "dark-blue": "#1B3A5C",
          blue: "#2196F3",
        },
        // UI palette
        background: "#1a1d23",
        surface: "#272b33",
        sidebar: "#1B2838",
        "sidebar-active": "#253447",
        border: "#2a2e37",
        accent: {
          green: "#4CAF50",
          blue: "#2196F3",
        },
        badge: "#35394a",
        success: "#4CAF50",
        warning: "#f0ad4e",
        danger: "#f05050",
        "text-primary": "#E0E0E0",
        "text-secondary": "#8e8e8e",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
    },
  },
  plugins: [],
};
```

## 22.3 `frontend/src/index.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body {
  @apply bg-background text-text-primary font-sans;
  margin: 0;
}

/* Scrollbar styling (dark theme) */
::-webkit-scrollbar {
  width: 8px;
}
::-webkit-scrollbar-track {
  @apply bg-background;
}
::-webkit-scrollbar-thumb {
  @apply bg-border rounded;
}
::-webkit-scrollbar-thumb:hover {
  @apply bg-text-secondary;
}

/* Poster card hover effect */
.poster-card {
  @apply transition-transform duration-200 ease-out;
}
.poster-card:hover {
  transform: translateY(-4px);
}
```

---

# 23. Frontend: App Shell & Routing

## 23.1 `frontend/src/App.tsx`

```typescript
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Login } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { Library } from "@/pages/Library";
import { MovieDetail } from "@/pages/MovieDetail";
import { Activity } from "@/pages/Activity";
import { Queue } from "@/pages/Queue";
import { Settings } from "@/pages/Settings";
import { System } from "@/pages/System";

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#272b33",
            color: "#E0E0E0",
            border: "1px solid #2a2e37",
          },
        }}
      />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/library" element={<Library />} />
            <Route path="/library/:id" element={<MovieDetail />} />
            <Route path="/activity" element={<Activity />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/system" element={<System />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

---

# 24. Frontend: Sidebar Component

## 24.1 `frontend/src/components/Sidebar.tsx`

The sidebar uses the Slimarr logo from `/images/header-logo.PNG` at the top.

```typescript
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Film, Activity, Download, Settings, Monitor } from "lucide-react";
import clsx from "clsx";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/library", icon: Film, label: "Library" },
  { to: "/activity", icon: Activity, label: "Activity" },
  { to: "/queue", icon: Download, label: "Queue" },
];

const bottomItems = [
  { to: "/settings", icon: Settings, label: "Settings" },
  { to: "/system", icon: Monitor, label: "System" },
];

export function Sidebar() {
  return (
    <aside className="w-52 bg-sidebar border-r border-border flex flex-col h-screen fixed left-0 top-0 z-50">
      {/* Logo */}
      <div className="p-4 border-b border-border">
        <img
          src="/logo.png"
          alt="Slimarr"
          className="h-8 w-auto"
        />
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-active text-accent-green border-l-3 border-accent-green"
                  : "text-text-secondary hover:text-text-primary hover:bg-sidebar-active/50"
              )
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Divider + bottom nav */}
      <div className="border-t border-border py-2">
        {bottomItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-active text-accent-green border-l-3 border-accent-green"
                  : "text-text-secondary hover:text-text-primary hover:bg-sidebar-active/50"
              )
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </div>

      {/* Version */}
      <div className="px-4 py-3 border-t border-border text-xs text-text-secondary">
        v0.1.0
      </div>
    </aside>
  );
}
```

---

# 25-32. Frontend Pages

Due to length, the frontend pages are specified here as **component contracts** — the exact props, state, API calls, and layout each page must implement. The agent should implement these as full React components.

## 25. Dashboard Page

**File:** `frontend/src/pages/Dashboard.tsx`

**API calls on mount:**
- `GET /api/v1/dashboard/stats` → stat cards
- `GET /api/v1/dashboard/savings-history` → area chart data
- `GET /api/v1/dashboard/recent-activity?limit=8` → recent activity list

**Layout:**
1. **Stat cards row** (4 cards): Total Movies, Optimal, Replaced, Space Saved — use `<StatCard>` component
2. **Area chart** (Recharts `<AreaChart>`): X-axis = dates, Y-axis = cumulative savings. Green fill matching `accent-green`
3. **Two-column bottom:** "Currently Processing" card (uses Socket.IO `download:progress` events) + "Recent Activity" list

## 26. Library Page

**File:** `frontend/src/pages/Library.tsx`

**API calls:**
- `GET /api/v1/library/movies?page=1&per_page=50&sort=title&order=asc` — paginated

**State:** `viewMode: "grid" | "table"`, `statusFilter`, `sortBy`, `searchQuery`, `page`

**Layout:**
1. **FilterBar** at top: search input, status dropdown, sort dropdown, grid/table toggle
2. **Poster grid** (default): CSS grid of `<PosterCard>` components, 5 columns on desktop, 3 on tablet, 2 on mobile
3. **Table view** (alternative): standard HTML table with columns: poster thumbnail, title, year, size, codec, resolution, status, savings

Each `<PosterCard>` click navigates to `/library/{id}`.

## 27. Movie Detail Page

**File:** `frontend/src/pages/MovieDetail.tsx`

**API calls:**
- `GET /api/v1/library/movies/{id}` — includes movie, search_results, history

**Layout (matches the wireframe in DESIGN_DOCUMENT.md):**
1. **Fanart backdrop** — full-width `<img>` of `fanart_url` with CSS gradient overlay fading to `background` at bottom
2. **Poster + metadata row** — poster on left, title/year/badges/overview on right
3. **File Info panel** — card showing path, size, codec, bitrate, original size, savings
4. **History panel** — chronological list of all actions on this movie
5. **Search Results panel** — table of last search results with "Search Now" button
6. **Action buttons**: "Search Now" (POST `/api/v1/library/movies/{id}/search`), "Process Now" (POST `/api/v1/library/movies/{id}/process`)

## 28-29. Activity & Queue Pages

Standard paginated list/table views calling their respective API endpoints. Activity shows an icon per action type (scanned, searched, replaced, error). Queue shows active downloads with progress bars.

## 30. Settings Page

**File:** `frontend/src/pages/Settings.tsx`

**Tabs:** Connections | Indexers | Download Client | General | UI

Each tab is a form with input fields for the relevant config section. Every integration section has a `<TestConnectionButton>` that calls `POST /api/v1/settings/test/{service}` and shows success/failure.

## 31. System Page

**Tabs:** Status | Health | Tasks | About

- **Health tab:** calls `GET /api/v1/system/health`, displays `<HealthCheck>` component per service
- **Tasks tab:** calls `GET /api/v1/system/tasks`, shows scheduled jobs with "Run Now" buttons
- **Status tab:** orchestrator status, version, data directory
- **About tab:** Slimarr logo, version, links

## 32. Login Page

**File:** `frontend/src/pages/Login.tsx`

Centered card on dark background. Shows the full Slimarr header logo (`/images/header-logo.PNG`). Username + password fields. Calls `POST /api/v1/auth/login`. Stores JWT token in `localStorage`. If no users exist (checked via `GET /api/v1/auth/check`), shows "Create Account" form instead (first-run setup).

---

# 33. Frontend: Shared Components

## 33.1 Key Component Specifications

### `PosterCard.tsx`
```
Props: { movie: MovieSummary; onClick: () => void }
- Shows poster image (lazy loaded with skeleton placeholder)
- Title + year below poster
- QualityBadge showing video_codec
- File size text
- Status bar at bottom (colored strip: green/amber/red/gray based on status)
- Hover: translateY(-4px) lift effect
```

### `QualityBadge.tsx`
```
Props: { label: string; variant?: "default" | "success" | "warning" | "danger" }
- Rounded pill: bg-badge text-white text-xs px-2 py-0.5
- Variant overrides background color (success=green, warning=amber, danger=red)
```

### `StatCard.tsx`
```
Props: { label: string; value: string | number; icon: LucideIcon; color?: string }
- Card with bg-surface, border-border
- Large number, small label below, icon on right
```

### `SizeBar.tsx`
```
Props: { oldSize: number; newSize: number }
- Visual bar showing before/after comparison
- Old size (full width, gray), new size (proportional width, green)
- Labels showing sizes and % savings
```

### `TestConnectionButton.tsx`
```
Props: { service: string; onResult: (result) => void }
- Button that calls POST /api/v1/settings/test/{service}
- Shows spinner during test, then checkmark/X with result
```

### `HealthCheck.tsx`
```
Props: { service: string; status: "ok" | "warning" | "error"; detail: string }
- Row with colored dot (green/amber/red), service name, detail text
```

---

# 34. Frontend: Socket.IO Hook & Real-Time

## 34.1 `frontend/src/lib/socket.ts`

```typescript
import { io, Socket } from "socket.io-client";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io(window.location.origin, {
      transports: ["websocket", "polling"],
    });
  }
  return socket;
}
```

## 34.2 `frontend/src/hooks/useSocket.ts`

```typescript
import { useEffect } from "react";
import { getSocket } from "@/lib/socket";

export function useSocket(event: string, handler: (data: any) => void) {
  useEffect(() => {
    const socket = getSocket();
    socket.on(event, handler);
    return () => { socket.off(event, handler); };
  }, [event, handler]);
}
```

**Usage in components:**
```typescript
// In Dashboard.tsx
useSocket("download:progress", (data) => {
  setCurrentDownload(data);
});

useSocket("replace:completed", (data) => {
  toast.success(`${data.title} — saved ${formatSize(data.old_size - data.new_size)}`);
  refreshStats();
});
```

---

# 35. Frontend: API Client

## 35.1 `frontend/src/lib/api.ts`

```typescript
const BASE = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem("slimarr_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const resp = await fetch(`${BASE}${path}`, { ...options, headers });

  if (resp.status === 401) {
    localStorage.removeItem("slimarr_token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(error.detail || resp.statusText);
  }

  return resp.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: any) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: any) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
```

## 35.2 `frontend/src/lib/types.ts`

```typescript
export interface Movie {
  id: number;
  plex_rating_key: string;
  title: string;
  year: number | null;
  imdb_id: string | null;
  tmdb_id: number | null;
  overview: string | null;
  poster_url: string | null;
  fanart_url: string | null;
  genres: string | null;
  file_path: string | null;
  file_size: number | null;
  resolution: string | null;
  video_codec: string | null;
  audio_codec: string | null;
  bitrate: number | null;
  source_type: string | null;
  original_file_size: number | null;
  total_savings: number;
  times_replaced: number;
  status: string;
  error_message: string | null;
  last_scanned: string | null;
  last_searched: string | null;
}

export interface DashboardStats {
  total_movies: number;
  optimal_count: number;
  replaced_count: number;
  pending_count: number;
  error_count: number;
  total_library_size: number;
  total_savings: number;
  total_original_size: number;
}

export interface SavingsHistoryPoint {
  date: string;
  cumulative_savings: number;
}

export interface ActivityItem {
  id: number;
  movie_id: number | null;
  movie_title: string | null;
  movie_year: number | null;
  poster_url: string | null;
  action: string;
  detail: string | null;
  old_size: number | null;
  new_size: number | null;
  savings_bytes: number | null;
  created_at: string;
}

export interface SearchResult {
  id: number;
  indexer_name: string;
  release_title: string;
  size: number;
  resolution: string | null;
  video_codec: string | null;
  source: string | null;
  savings_bytes: number | null;
  savings_pct: number | null;
  score: number | null;
  decision: string;
  reject_reason: string | null;
  searched_at: string;
}

export interface QueueItem {
  download_id: number;
  movie_id: number;
  title: string;
  year: number | null;
  poster_url: string | null;
  status: string;
  progress: number;
  speed: string | null;
  eta: string | null;
  old_size: number | null;
  new_size: number | null;
  savings_bytes: number | null;
  started_at: string | null;
}

export interface HealthCheck {
  service: string;
  status: "ok" | "warning" | "error";
  detail: Record<string, any>;
}
```

---

# 36. Testing Strategy

## 36.1 Backend Tests

Use `pytest` with `pytest-asyncio` for async tests:

```
pip install pytest pytest-asyncio httpx
```

**Key test files:**
```
tests/
├── test_parser.py         # Test release name parsing (most critical)
├── test_comparer.py       # Test comparison logic
├── test_api_auth.py       # Test login, registration, JWT
├── test_api_library.py    # Test movie list/detail endpoints
├── test_api_settings.py   # Test settings CRUD
├── test_scanner.py        # Test Plex scan with mocked PlexServer
├── test_newznab.py        # Test Newznab XML parsing with sample data
└── conftest.py            # Shared fixtures (test DB, test client)
```

**`tests/test_parser.py` — example test cases:**
```python
import pytest
from backend.core.parser import parse_release_title

@pytest.mark.parametrize("title,expected_res,expected_codec,expected_source", [
    ("Toy.Story.1995.2160p.UHD.BluRay.x265.HDR.DTS-HD.MA.7.1-GROUP", "2160p", "h265", "bluray"),
    ("The.Matrix.1999.1080p.WEB-DL.H264.AAC-GROUP", "1080p", "h264", "web-dl"),
    ("Inception.2010.720p.BluRay.x264.DTS-GROUP", "720p", "h264", "bluray"),
    ("Dune.2021.2160p.WEB-DL.AV1.Atmos-GROUP", "2160p", "av1", "web-dl"),
    ("Movie.2023.1080p.REMUX.AVC.DTS-HD.MA-GROUP", "1080p", "h264", "remux"),
])
def test_parse_release_title(title, expected_res, expected_codec, expected_source):
    parsed = parse_release_title(title)
    assert parsed.resolution == expected_res
    assert parsed.video_codec == expected_codec
    assert parsed.source == expected_source
```

## 36.2 Frontend Tests

Use Vitest for unit tests on utility functions. Manual testing for UI.

---

# 37. Build & Deployment

## 37.1 Development Workflow

```powershell
# Terminal 1: Backend (with hot-reload)
cd C:\Slimarr
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:socket_app --host 0.0.0.0 --port 9494 --reload

# Terminal 2: Frontend dev server (with Vite proxy to backend)
cd C:\Slimarr\frontend
npm install
npm run dev
# → opens http://localhost:3000 (proxies API to :9494)
```

## 37.2 Production Build

```powershell
# Build frontend
cd C:\Slimarr\frontend
npm run build
# → outputs to frontend/dist/

# Copy logo to frontend public
Copy-Item images\header-logo.PNG frontend\public\logo.png
Copy-Item images\icon.PNG frontend\public\favicon.ico  # (convert to .ico first)

# Run production
cd C:\Slimarr
python -m backend.main
# → serves API + frontend on http://localhost:9494
```

## 37.3 Install as Windows Service

```powershell
# Download NSSM from https://nssm.cc/download
# Place nssm.exe in PATH or C:\Slimarr\

cd C:\Slimarr
python -c "from backend.service.windows_service import install_service; install_service()"
# → Service installed and set to auto-start
```

---

# 38. First Run / Setup Wizard

On first launch, Slimarr detects that:
1. No users exist in the database
2. Config values are empty (no Plex URL, no indexers, no TMDB key)

**Flow:**
1. User opens `http://localhost:9494` → frontend calls `GET /api/v1/auth/check`
2. Response: `{ "has_user": false, "setup_required": true }`
3. Frontend redirects to `/login` which shows "Create Account" form (not "Login")
4. After account creation, user is logged in with JWT
5. Frontend redirects to `/settings` with a "Welcome to Slimarr" banner prompting setup
6. User configures: Plex → SABnzbd → Indexers → TMDB key
7. Each step has "Test Connection" to verify
8. When all required services are configured, "Start First Scan" button appears
9. First scan: library scan + TMDB metadata fetch (populates poster grid)

---

# APPENDIX: Utility Functions

## `formatSize()` — used everywhere in the frontend

```typescript
export function formatSize(bytes: number | null): string {
  if (bytes == null || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
```

## `formatSavings()` — show size reduction

```typescript
export function formatSavings(oldSize: number, newSize: number): string {
  const saved = oldSize - newSize;
  const pct = ((saved / oldSize) * 100).toFixed(1);
  return `${formatSize(saved)} (${pct}%)`;
}
```

## `getStatusColor()` — map status to Tailwind class

```typescript
export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    optimal: "bg-success",
    replaced: "bg-success",
    pending: "bg-warning",
    downloading: "bg-accent-blue",
    searching: "bg-accent-blue",
    error: "bg-danger",
    skipped: "bg-text-secondary",
  };
  return map[status] || "bg-text-secondary";
}
```

---

# END OF IMPLEMENTATION GUIDE

This document, combined with `DESIGN_DOCUMENT.md`, contains everything needed to build Slimarr from scratch. The agent should:

1. Create the directory structure (Section 1.1)
2. Install dependencies (Section 1.2, 1.3)
3. Implement backend modules in order (Sections 2-21)
4. Implement frontend (Sections 22-35)
5. Test (Section 36)
6. Build and deploy (Section 37)

Every file path, every function signature, every API route, and every component contract is specified above.
