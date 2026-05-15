# Slimarr Docker Deployment Guide

> **v1.4 — "Containerised"**

This guide covers deploying Slimarr with Docker on Linux, including Unraid, Synology, Proxmox, TrueNAS SCALE, and Ubuntu/Debian servers.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [PostgreSQL Backend (Optional)](#postgresql-backend-optional)
2. [Environment Variables](#environment-variables)
3. [Volume Mapping](#volume-mapping)
4. [Media Path Setup](#media-path-setup)
5. [Reverse Proxy (Traefik / nginx)](#reverse-proxy)
6. [Unraid Setup](#unraid-setup)
7. [Synology Setup](#synology-setup)
8. [Permissions](#permissions)
9. [Health Checks & Monitoring](#health-checks--monitoring)
10. [Upgrading](#upgrading)
11. [Troubleshooting](#troubleshooting)
12. [Migration from v1.3](#migration-from-v13)

---

## Quick Start

```bash
# 1. Create a directory for Slimarr
mkdir -p ~/slimarr/config
cd ~/slimarr

# 2. Copy the env template
curl -fsSL https://raw.githubusercontent.com/theantipopau/slimarr/main/.env.example -o .env
nano .env   # Fill in your Plex token, SABnzbd key, etc.

# 3. Start
docker compose up -d

# 4. Open
open http://localhost:9494
```

First run creates the admin account via the web UI.

---

## PostgreSQL Backend (Optional)

SQLite remains the default and recommended backend for small single-node setups.

If your deployment has higher write volume (large diagnostics history, heavy automation,
long-running operation), Slimarr supports optional PostgreSQL via `SLIMARR_DB_URL`.

Use the included compose template:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Key env var:

```env
SLIMARR_DB_URL=postgresql+asyncpg://slimarr:change_me@postgres:5432/slimarr
```

You can verify runtime backend from the API:

```bash
curl -fsS http://localhost:9494/api/v1/system/info | jq .db_backend
```

Expected output: `"postgresql"`.

---

## Environment Variables

All `SLIMARR_*` environment variables override the equivalent `config.yaml` key. This means you can run Slimarr **without** a config.yaml at all in Docker.

| Variable | Description | Default |
|---|---|---|
| `SLIMARR_PLEX_URL` | Plex Media Server URL | — |
| `SLIMARR_PLEX_TOKEN` | Plex authentication token | — |
| `SLIMARR_DOWNLOAD_CLIENT` | `sabnzbd` or `nzbget` | `sabnzbd` |
| `SLIMARR_SABNZBD_URL` | SABnzbd URL | — |
| `SLIMARR_SABNZBD_API_KEY` | SABnzbd API key | — |
| `SLIMARR_NZBGET_URL` | NZBGet URL | — |
| `SLIMARR_NZBGET_USERNAME` | NZBGet username | — |
| `SLIMARR_NZBGET_PASSWORD` | NZBGet password | — |
| `SLIMARR_PROWLARR_URL` | Prowlarr URL | — |
| `SLIMARR_PROWLARR_API_KEY` | Prowlarr API key | — |
| `SLIMARR_RADARR_URL` | Radarr URL | — |
| `SLIMARR_RADARR_API_KEY` | Radarr API key | — |
| `SLIMARR_SONARR_URL` | Sonarr URL | — |
| `SLIMARR_SONARR_API_KEY` | Sonarr API key | — |
| `SLIMARR_TMDB_API_KEY` | TMDB API key for metadata | — |
| `SLIMARR_PORT` | Web UI port | `9494` |
| `SLIMARR_LOG_LEVEL` | `debug`, `info`, `warning`, `error` | `info` |
| `SLIMARR_LOG_FORMAT` | `plain` or `json` | `plain` |
| `SLIMARR_DB` | SQLite database path | `/app/data/slimarr.db` |
| `TZ` | Timezone (e.g. `America/New_York`) | `UTC` |

### Config precedence

```
SLIMARR_* env vars  →  config.yaml  →  built-in defaults
```

---

## Volume Mapping

| Container path | Purpose | Required |
|---|---|---|
| `/app/data` | SQLite DB, logs, image cache | **Yes** |
| `/app/config` | `config.yaml` mount point | Optional (use env vars) |
| `/media/*` | Your media library paths | Required for file probing |

### Named volumes (recommended)

```yaml
volumes:
  slimarr_data:
    driver: local
```

```yaml
services:
  slimarr:
    volumes:
      - slimarr_data:/app/data
      - ./config:/app/config
```

### Bind mount example (advanced)

```yaml
    volumes:
      - /opt/slimarr/data:/app/data
      - /opt/slimarr/config:/app/config
      - /mnt/media/movies:/media/movies:ro
```

---

## Media Path Setup

Slimarr needs to read the same files that Plex sees. Mount media volumes with `:ro` (read-only) unless you want Slimarr to replace files directly.

```yaml
    volumes:
      - /mnt/tank/movies:/media/movies:ro
      - /mnt/tank/tv:/media/tv:ro
```

Then configure path mappings in `config.yaml` (or Settings → Files):

```yaml
files:
  plex_path_mappings:
    - plex_path: /data/movies
      local_path: /media/movies
```

### SMB / NFS mounts

Mount network shares **on the host** and pass them through as bind mounts. Never mount SMB/NFS inside the container.

```bash
# On the host
sudo mount -t nfs 192.168.1.50:/volume1/media /mnt/nas-media

# In compose
volumes:
  - /mnt/nas-media/movies:/media/movies:ro
```

---

## Reverse Proxy

### Traefik

Copy `docker-compose.traefik.yml` from the repository and set `SLIMARR_HOST` in your `.env`:

```env
SLIMARR_HOST=slimarr.yourdomain.com
```

```bash
docker compose -f docker-compose.traefik.yml up -d
```

### nginx (manual)

```nginx
server {
    listen 80;
    server_name slimarr.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name slimarr.yourdomain.com;

    ssl_certificate     /etc/ssl/certs/yourdomain.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.key;

    location / {
        proxy_pass         http://127.0.0.1:9494;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

---

## Unraid Setup

1. Open **Community Applications** and search for **Slimarr** (or use the template URL below).
2. If adding manually: Apps → Add Container
   - **Repository**: `ghcr.io/theantipopau/slimarr:latest`
   - **Port**: `9494:9494`
   - **Path `/app/data`**: map to `/mnt/user/appdata/slimarr`
   - **Path `/app/config`**: map to `/mnt/user/appdata/slimarr/config`
   - **Media paths**: add extra paths for each media share
3. Add environment variables in the **Extra Parameters** section.
4. Apply and Start.

---

## Synology Setup

### Via Container Manager (DSM 7.2+)

1. Open **Container Manager** → Registry → search `ghcr.io/theantipopau/slimarr`
2. Download the `latest` tag.
3. Create container:
   - **Port**: `9494 → 9494`
   - **Volume**: `/docker/slimarr/data → /app/data`
   - **Volume**: `/docker/slimarr/config → /app/config`
   - **Environment**: add `SLIMARR_*` variables
4. Start.

### Via Portainer / SSH (docker compose)

```bash
ssh admin@your-nas
mkdir -p /volume1/docker/slimarr/{data,config}
cd /volume1/docker/slimarr
# Copy docker-compose.yml and .env here, then:
docker compose up -d
```

---

## Permissions

The container runs as UID/GID `1000:1000` by default.

### Custom UID/GID

Build with custom IDs:

```bash
docker build --build-arg PUID=1026 --build-arg PGID=100 -t slimarr .
```

Or override at runtime:

```yaml
services:
  slimarr:
    user: "1026:100"
```

### Fix existing volume permissions

```bash
docker exec slimarr chown -R 1000:1000 /app/data
```

---

## Health Checks & Monitoring

### Built-in health endpoint

```
GET /api/v1/system/health
```

Returns `200 {"status":"ok"}` when healthy.

Docker uses this automatically for `HEALTHCHECK`.

### Prometheus metrics

```
GET /api/v1/system/metrics
```

No authentication required. Exposes:

| Metric | Description |
|---|---|
| `slimarr_uptime_seconds` | Seconds since process start |
| `slimarr_movies_total` | Total movies in library |
| `slimarr_downloads_active` | Active downloads |
| `slimarr_db_size_bytes` | SQLite database size |
| `slimarr_disk_free_bytes` | Free bytes on data partition |
| `slimarr_cycle_running` | 1 if automation cycle is active |
| `slimarr_search_degraded` | 1 if search pipeline is degraded |

#### Prometheus scrape config

```yaml
scrape_configs:
  - job_name: slimarr
    static_configs:
      - targets: ['slimarr:9494']
    metrics_path: /api/v1/system/metrics
```

---

## Upgrading

```bash
docker compose pull
docker compose up -d
```

Slimarr auto-migrates the database on startup. No manual migration steps required for patch and minor releases.

---

## Troubleshooting

### Container won't start

```bash
docker logs slimarr
```

Look for `[FATAL]` or `[startup]` lines. Common causes:
- Missing Plex token — set `SLIMARR_PLEX_TOKEN`
- Data volume not writable — check permissions
- Port conflict — change `SLIMARR_PORT`

### "Missing mount" warnings in UI

Open **System → Container** in the web UI. The **Data Directories** section will show which paths are not writable.

### Database locked / corrupt

```bash
docker exec slimarr python -c "
import sqlite3
conn = sqlite3.connect('/app/data/slimarr.db')
print(conn.execute('PRAGMA integrity_check').fetchone())
"
```

If corrupted, stop the container, rename `slimarr.db`, and restart (fresh DB, config preserved).

### Logs

```bash
# Live container logs (Docker-friendly plain text)
docker logs -f slimarr

# Full rotating log file
docker exec slimarr tail -f /app/data/logs/slimarr.log

# JSON structured logs (set SLIMARR_LOG_FORMAT=json)
docker logs slimarr | jq .
```

---

## Migration from v1.3

v1.4 is fully backward compatible with v1.3 databases and config files.

1. Stop the running instance.
2. Back up your `data/` directory and `config.yaml`.
3. Update the image tag to `v1.4` (or `latest`).
4. Restart — the DB migrates automatically.

If upgrading from a Windows install to Docker:

1. Copy `data/slimarr.db` and `config.yaml` to your Docker data volume and config mount.
2. Start the container.
3. All history, settings, and library data will be intact.
