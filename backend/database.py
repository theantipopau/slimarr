"""
SQLAlchemy 2.0 async database models and engine.
Database: SQLite via aiosqlite.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Database file path — relative to cwd (the project root)
_DB_PATH = os.environ.get("SLIMARR_DB", "data/slimarr.db")
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    savings_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_lightweight_migrations(conn)


async def _table_columns(conn, table_name: str) -> set[str]:
    rows = await conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
    return {row[1] for row in rows.fetchall()}


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


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields an async session."""
    async with async_session() as session:
        yield session
