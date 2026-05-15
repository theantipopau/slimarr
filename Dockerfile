# ──────────────────────────────────────────────────────────────────────────────
# Slimarr v1.4 — Multi-stage Dockerfile
# Target: linux/amd64, linux/arm64
#
# Stage 1  (builder)   — build the React frontend
# Stage 2  (runtime)   — slim Python image, no build tools
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Frontend build ───────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Layer-cache npm install separately from source
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Metadata
LABEL org.opencontainers.image.title="Slimarr"
LABEL org.opencontainers.image.description="Smart Usenet replacement manager for Plex libraries"
LABEL org.opencontainers.image.url="https://github.com/theantipopau/slimarr"
LABEL org.opencontainers.image.source="https://github.com/theantipopau/slimarr"
LABEL org.opencontainers.image.licenses="MIT"

# ── System dependencies ───────────────────────────────────────────────────────
# mediainfo: required by pymediainfo for local media probing
# ca-certificates: required for TLS verification against external services
RUN apt-get update && apt-get install -y --no-install-recommends \
        mediainfo \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────────
# Running as a dedicated non-root user follows Docker security best practices.
# Override PUID/PGID at runtime with --user if your media volumes require it.
ARG PUID=1000
ARG PGID=1000
RUN groupadd -g "${PGID}" slimarr \
 && useradd  -u "${PUID}" -g "${PGID}" -d /app -s /sbin/nologin slimarr

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app

# Install deps as root before chowning the workdir (faster layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY backend/   ./backend/
COPY run.py     ./run.py
COPY config.yaml.example ./config.yaml.example

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# ── Persistent data directories ───────────────────────────────────────────────
# These are the paths that MUST be mapped to named volumes or bind mounts.
#   /app/data        — SQLite database, logs, media cover cache
#   /app/config      — config.yaml (mounted as a single file or directory)
#
# Media paths are mounted by the user and configured in config.yaml / env vars.
# They are not created here — they come from your Plex/NAS setup.
RUN install -d -o slimarr -g slimarr \
        /app/data \
        /app/data/logs \
        /app/data/MediaCover \
        /app/config

# Default config location inside the container
# Mount your config.yaml at /app/config/config.yaml or use SLIMARR_* env vars.
ENV SLIMARR_CONFIG=/app/config/config.yaml \
    SLIMARR_DB=/app/data/slimarr.db \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root for runtime
USER slimarr

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9494/api/v1/system/health', timeout=8)" || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
EXPOSE 9494

# run.py detects non-Windows → headless mode (uvicorn directly)
ENTRYPOINT ["python", "run.py", "--headless"]
