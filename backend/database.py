"""
SQLAlchemy 2.0 async database models and engine.
Database: SQLite via aiosqlite.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.utils.platform import is_docker

# Database URL selection.
#
# Priority:
# 1) SLIMARR_DB_URL (full SQLAlchemy async URL)
# 2) SLIMARR_DB (SQLite path, legacy-compatible)
#
# Supported backends:
# - sqlite+aiosqlite:///data/slimarr.db   (default)
# - postgresql+asyncpg://user:pass@host/db
_RAW_DB_URL = (os.environ.get("SLIMARR_DB_URL") or "").strip()
_DB_PATH = os.environ.get("SLIMARR_DB") or "data/slimarr.db"

if _RAW_DB_URL:
    DATABASE_URL = _RAW_DB_URL
else:
    DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"


def get_db_backend() -> str:
    url = DATABASE_URL.lower()
    if url.startswith("postgresql+") or url.startswith("postgres+"):
        return "postgresql"
    return "sqlite"

_engine_kwargs: dict = {
    "echo": False,
    "pool_pre_ping": True,
}

if get_db_backend() == "sqlite":
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Conservative defaults for homelab PostgreSQL usage.
    _engine_kwargs.update(
        {
            "pool_size": int(os.environ.get("SLIMARR_DB_POOL_SIZE") or "10"),
            "max_overflow": int(os.environ.get("SLIMARR_DB_MAX_OVERFLOW") or "20"),
            "pool_timeout": int(os.environ.get("SLIMARR_DB_POOL_TIMEOUT") or "30"),
            "pool_recycle": int(os.environ.get("SLIMARR_DB_POOL_RECYCLE") or "1800"),
        }
    )

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    elapsed_ms = (time.perf_counter() - context._query_start_time) * 1000
    if elapsed_ms >= float(os.environ.get("SLIMARR_DB_SLOW_QUERY_MS", "250")):
        from loguru import logger

        compact = " ".join((statement or "").split())
        logger.warning(
            "DB slow query ({:.1f} ms): {}",
            elapsed_ms,
            compact[:240],
        )


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    plex_rating_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # TMDB metadata
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    poster_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backdrop_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    genres: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON array string

    # File info
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kbps
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Tracking
    original_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_savings: Mapped[int] = mapped_column(Integer, default=0)
    times_replaced: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_searched: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    slimarr_locked: Mapped[bool] = mapped_column(Integer, default=0)  # 0=False, 1=True (SQLite bool)
    preferred_release_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quality_intent: Mapped[str] = mapped_column(String, default="space_saver", index=True)
    force_keep: Mapped[bool] = mapped_column(Integer, default=0)
    allow_larger_replacements: Mapped[bool] = mapped_column(Integer, default=0)
    quality_profile_overrides: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    search_results: Mapped[list[SearchResult]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )
    downloads: Mapped[list[Download]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list[ActivityLog]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), index=True)
    indexer_name: Mapped[str] = mapped_column(String)
    release_title: Mapped[str] = mapped_column(String)
    nzb_url: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hdr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    languages: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    media_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    media_health_rating: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    media_health_reasons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String, default="pending")
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    searched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    movie: Mapped[Movie] = relationship(back_populates="search_results")


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), index=True)
    search_result_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("search_results.id"), nullable=True
    )
    nzo_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    release_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expected_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cleanup_status: Mapped[str] = mapped_column(String, default="pending", nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    grabbed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    blacklist_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    movie: Mapped[Movie] = relationship(back_populates="downloads")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("movies.id"), nullable=True, index=True
    )
    movie_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event: Mapped[str] = mapped_column(String, nullable=False, index=True)
    old_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    old_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )

    movie: Mapped[Optional[Movie]] = relationship(back_populates="activity_logs")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())




class DownloadBlacklist(Base):
    __tablename__ = "download_blacklist"

    id: Mapped[int] = mapped_column(primary_key=True)
    release_title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    release_hash: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    uploader: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    indexer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    manual: Mapped[bool] = mapped_column(default=False)


class OrphanedDownload(Base):
    __tablename__ = "orphaned_downloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    downloader_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    downloader_job_id: Mapped[str] = mapped_column(String, nullable=False)
    release_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    found_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    cleanup_scheduled: Mapped[bool] = mapped_column(default=False)
    cleanup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    age_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class UploaderStats(Base):
    __tablename__ = "uploader_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploader: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    corruption_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    health_score: Mapped[float] = mapped_column(Float, default=0.5)


class DecisionAuditLog(Base):
    __tablename__ = "decision_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[Optional[int]] = mapped_column(ForeignKey("movies.id"), nullable=True, index=True)
    movie_title: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    indexer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    release_title: Mapped[str] = mapped_column(String, nullable=False)
    candidate_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    local_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False, index=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    media_health_rating: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    media_health_reasons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


async def init_db() -> None:
    """Create all tables if they don't exist.

    Includes startup retry/backoff so transient DB startup races in Docker
    (e.g. PostgreSQL not ready yet) do not hard-fail immediately.
    """
    backend = get_db_backend()

    if backend == "sqlite":
        os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)

    attempts = int(os.environ.get("SLIMARR_DB_CONNECT_RETRIES", "5"))
    base_delay = float(os.environ.get("SLIMARR_DB_CONNECT_RETRY_BASE_SECONDS", "0.8"))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await _run_lightweight_migrations(conn)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            from loguru import logger

            delay = base_delay * (2 ** (attempt - 1))
            jitter = min(0.5, delay * 0.15)
            sleep_for = delay + jitter
            logger.warning(
                "DB init attempt {}/{} failed (backend={}): {}. Retrying in {:.2f}s",
                attempt,
                attempts,
                backend,
                exc,
                sleep_for,
            )
            import asyncio

            await asyncio.sleep(sleep_for)

    if last_error is not None:
        raise last_error


async def _table_columns(conn, table_name: str) -> set[str]:
    backend = get_db_backend()
    if backend == "sqlite":
        rows = await conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
        return {row[1] for row in rows.fetchall()}

    rows = await conn.exec_driver_sql(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
        """,
        {"table_name": table_name},
    )
    return {row[0] for row in rows.fetchall()}


async def _add_column_if_missing(
    conn,
    table_name: str,
    existing_columns: set[str],
    column_name: str,
    column_definition: str,
) -> None:
    if column_name in existing_columns:
        return

    await conn.exec_driver_sql(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )
    existing_columns.add(column_name)


async def _run_lightweight_migrations(conn) -> None:
    """Apply additive SQLite migrations for existing installs.

    SQLAlchemy's create_all creates missing tables, but it intentionally does
    not alter existing tables. Keep these migrations additive so upgrades do
    not risk user data.
    """
    download_columns = await _table_columns(conn, "downloads")
    await _add_column_if_missing(
        conn, "downloads", download_columns, "cleanup_status", "VARCHAR DEFAULT 'pending'"
    )
    await _add_column_if_missing(
        conn, "downloads", download_columns, "retry_count", "INTEGER DEFAULT 0"
    )
    await _add_column_if_missing(conn, "downloads", download_columns, "grabbed_at", "DATETIME")
    await _add_column_if_missing(conn, "downloads", download_columns, "last_error_at", "DATETIME")
    await _add_column_if_missing(conn, "downloads", download_columns, "blacklist_reason", "VARCHAR")

    search_result_columns = await _table_columns(conn, "search_results")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "age_days", "INTEGER")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "confidence_score", "FLOAT")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "confidence_breakdown", "TEXT")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "hdr", "VARCHAR")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "languages", "VARCHAR")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "media_health_score", "FLOAT")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "media_health_rating", "VARCHAR")
    await _add_column_if_missing(conn, "search_results", search_result_columns, "media_health_reasons", "TEXT")

    decision_columns = await _table_columns(conn, "decision_audit_log")
    await _add_column_if_missing(conn, "decision_audit_log", decision_columns, "confidence_score", "FLOAT")
    await _add_column_if_missing(conn, "decision_audit_log", decision_columns, "confidence_breakdown", "TEXT")
    await _add_column_if_missing(conn, "decision_audit_log", decision_columns, "media_health_score", "FLOAT")
    await _add_column_if_missing(conn, "decision_audit_log", decision_columns, "media_health_rating", "VARCHAR")
    await _add_column_if_missing(conn, "decision_audit_log", decision_columns, "media_health_reasons", "TEXT")

    movie_columns = await _table_columns(conn, "movies")
    await _add_column_if_missing(conn, "movies", movie_columns, "slimarr_locked", "INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "movies", movie_columns, "preferred_release_title", "VARCHAR")
    await _add_column_if_missing(conn, "movies", movie_columns, "quality_intent", "VARCHAR DEFAULT 'space_saver'")
    await _add_column_if_missing(conn, "movies", movie_columns, "force_keep", "INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "movies", movie_columns, "allow_larger_replacements", "INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "movies", movie_columns, "quality_profile_overrides", "TEXT")

    activity_columns = await _table_columns(conn, "activity_log")
    await _add_column_if_missing(conn, "activity_log", activity_columns, "actor", "VARCHAR")
    await _add_column_if_missing(conn, "activity_log", activity_columns, "details", "TEXT")

    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_search_results_movie_decision_score "
        "ON search_results (movie_id, decision, score)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_decision_audit_created_decision "
        "ON decision_audit_log (created_at, decision)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_activity_log_created_event "
        "ON activity_log (created_at, event)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_movies_quality_intent "
        "ON movies (quality_intent)"
    )


def database_runtime_info() -> dict[str, object]:
    """Return non-secret database runtime metadata for diagnostics endpoints."""
    backend = get_db_backend()
    info: dict[str, object] = {
        "backend": backend,
        "url_driver": DATABASE_URL.split("://", 1)[0],
        "pool": {
            "size": getattr(engine.sync_engine.pool, "size", lambda: None)(),
            "checked_in": getattr(engine.sync_engine.pool, "checkedin", lambda: None)(),
            "checked_out": getattr(engine.sync_engine.pool, "checkedout", lambda: None)(),
            "overflow": getattr(engine.sync_engine.pool, "overflow", lambda: None)(),
        },
    }

    if backend == "sqlite":
        db_path = os.environ.get("SLIMARR_DB") or "data/slimarr.db"
        info["sqlite"] = {
            "path": db_path,
            "wal_enabled": bool(os.path.exists(db_path + "-wal")),
            "size_bytes": os.path.getsize(db_path) if os.path.exists(db_path) else 0,
            "vacuum_recommended": (
                os.path.exists(db_path) and os.path.getsize(db_path) > 1_500_000_000
            ),
        }
    return info


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields an async session."""
    async with async_session() as session:
        yield session
