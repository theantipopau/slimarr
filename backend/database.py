"""
SQLAlchemy 2.0 async database models and engine.
Database: SQLite via aiosqlite.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


if get_db_backend() == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        """WAL mode lets readers (API requests, dashboard queries) proceed
        while a writer (a scan or replacement) holds the connection, instead
        of blocking behind SQLite's default rollback-journal exclusive lock.
        busy_timeout makes any remaining lock contention retry for a few
        seconds instead of raising "database is locked" immediately, which
        was the dominant error in production logs under concurrent writes.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


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
    added_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Plex library-add time

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
    audio_channels: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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
    __table_args__ = (
        # Storage-pressure insights filters this table by decision + a created_at
        # window on every dashboard refresh; without a composite index this table
        # scan gets slow once it accumulates the reject-heavy history a running
        # instance produces (most analyzed candidates are rejected).
        Index("ix_decision_audit_log_decision_created_at", "decision", "created_at"),
    )

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


class StorageOperationLog(Base):
    __tablename__ = "storage_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_classification: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_classification: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    estimated_bytes: Mapped[int] = mapped_column(Integer, default=0)
    actual_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    messages: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class StoragePathHealth(Base):
    __tablename__ = "storage_path_health"

    id: Mapped[int] = mapped_column(primary_key=True)
    path_prefix: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String, nullable=False, index=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ReplacementRecoveryRecord(Base):
    __tablename__ = "replacement_recovery"

    id: Mapped[int] = mapped_column(primary_key=True)
    download_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    movie_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    movie_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    phase: Mapped[str] = mapped_column(String, default="initialized", index=True)
    original_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mapped_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    recycle_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fallback_backup_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=1)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    job: Mapped[JobRecord] = relationship(back_populates="events")


# ── Recommendation & Collection Completion (see docs/RECOMMENDATION_ARCHITECTURE.md) ──
#
# RecommendationCandidate rows are never Movie rows — no shared primary-key space,
# no shared status vocabulary, and process_single_movie() only ever looks at the
# Movie table. This keeps "recommended" and "queued for replacement" structurally
# impossible to confuse.


class RecommendationCandidate(Base):
    __tablename__ = "recommendation_candidates"
    __table_args__ = (
        UniqueConstraint("media_type", "tmdb_id", name="uq_candidate_media_tmdb"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # "movie" | "tv"
    title: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    poster_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backdrop_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    popularity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vote_average: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    genres: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON array string

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    availability: Mapped[list["StreamingAvailability"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("candidate_id", "category", name="uq_recommendation_candidate_category"),
        Index("ix_recommendations_state_score", "state", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("recommendation_candidates.id"), index=True)

    # Single-user app today — always "default" in this release. Exists so a
    # future multi-user migration doesn't require a schema rewrite; not
    # exposed anywhere in the API/UI as a selectable dimension yet.
    user_scope: Mapped[str] = mapped_column(String, default="default", index=True)

    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    state: Mapped[str] = mapped_column(String, default="active", index=True)
    # active | dismissed | hidden | watchlisted | actioned | already_available
    # | already_managed | expired

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    candidate: Mapped[RecommendationCandidate] = relationship(back_populates="recommendations")
    reasons: Mapped[list["RecommendationReason"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["RecommendationFeedback"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )


class RecommendationReason(Base):
    __tablename__ = "recommendation_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    reason_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    explanation: Mapped[str] = mapped_column(String, nullable=False)
    source_movie_id: Mapped[Optional[int]] = mapped_column(ForeignKey("movies.id"), nullable=True)
    source_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # "tmdb" | "plex" | "ai"
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    recommendation: Mapped[Recommendation] = relationship(back_populates="reasons")


class StreamingAvailability(Base):
    __tablename__ = "streaming_availability"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "region", "provider_id", "availability_type",
            name="uq_availability_candidate_region_provider_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("recommendation_candidates.id"), index=True)
    region: Mapped[str] = mapped_column(String, nullable=False, index=True)  # ISO 3166-1 alpha-2, e.g. "AU"
    provider_id: Mapped[int] = mapped_column(Integer, nullable=False)  # TMDB provider_id
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    display_priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    availability_type: Mapped[str] = mapped_column(String, nullable=False)  # flatrate|rent|buy|ads|free
    source: Mapped[str] = mapped_column(String, default="tmdb")
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    candidate: Mapped[RecommendationCandidate] = relationship(back_populates="availability")


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # shown|opened|dismissed|hidden|watchlisted|sent_to_radarr|sent_to_sonarr
    # |sent_to_seerr|marked_owned|availability_refreshed
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    recommendation: Mapped[Recommendation] = relationship(back_populates="feedback")


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


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _assert_safe_identifier(name: str) -> str:
    """Guard against SQL injection if a table/column name ever stops being a literal.

    These migration helpers only ever receive hardcoded names today, but they build
    DDL via f-strings, so this is a defense-in-depth check rather than a no-op.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


async def _table_columns(conn, table_name: str) -> set[str]:
    _assert_safe_identifier(table_name)
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

    _assert_safe_identifier(table_name)
    _assert_safe_identifier(column_name)
    await conn.exec_driver_sql(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )
    existing_columns.add(column_name)


# Current migration generation - increment whenever a new migration step is added
# to _run_lightweight_migrations(), OR when new tables are added (even though
# Base.metadata.create_all() creates those automatically with no migration step
# needed) so the diagnostics bundle reflects the schema generation accurately.
SCHEMA_VERSION = 6


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
    await _add_column_if_missing(conn, "search_results", search_result_columns, "audio_channels", "VARCHAR")
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
    await _add_column_if_missing(conn, "movies", movie_columns, "added_at", "DATETIME")

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
    # The storage-pressure insights query filters by decision equality first and
    # created_at range second; SQLite's planner prefers the single-column
    # ix_decision_audit_log_decision index over the (created_at, decision)
    # composite above for that shape, falling back to a row-by-row created_at
    # filter across the whole reject history. A (decision, created_at) leading
    # composite lets it seek directly instead.
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_decision_audit_log_decision_created_at "
        "ON decision_audit_log (decision, created_at)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_activity_log_created_event "
        "ON activity_log (created_at, event)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_movies_quality_intent "
        "ON movies (quality_intent)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_storage_operations_completed_status "
        "ON storage_operations (completed_at, status)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_storage_operations_classification_status "
        "ON storage_operations (source_classification, status)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_storage_path_health_classification_failure "
        "ON storage_path_health (classification, last_failure_at)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_replacement_recovery_status_updated "
        "ON replacement_recovery (status, updated_at)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_replacement_recovery_download_status "
        "ON replacement_recovery (download_id, status)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_jobs_status_priority_created "
        "ON jobs (status, priority, created_at)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_jobs_kind_status_created "
        "ON jobs (kind, status, created_at)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_job_events_job_created "
        "ON job_events (job_id, created_at)"
    )


def database_runtime_info() -> dict[str, object]:
    """Return non-secret database runtime metadata for diagnostics endpoints."""
    backend = get_db_backend()
    info: dict[str, object] = {
        "backend": backend,
        "url_driver": DATABASE_URL.split("://", 1)[0],
        "schema_version": SCHEMA_VERSION,
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
