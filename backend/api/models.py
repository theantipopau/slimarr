"""Shared API response/request models for OpenAPI consistency."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ActionStatusResponse(BaseModel):
    status: str
    movie_id: int | None = None
    task_id: str | None = None
    search_result_id: int | None = None


class AuthCheckResponse(BaseModel):
    has_user: bool
    setup_required: bool


class MovieOut(BaseModel):
    id: int
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    original_file_size: int | None = None
    resolution: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    status: str
    slimarr_locked: bool
    last_scanned: str | None = None
    last_searched: str | None = None


class SearchResultOut(BaseModel):
    id: int
    indexer_name: str
    release_title: str
    size: int
    resolution: str | None = None
    video_codec: str | None = None
    age_days: int | None = None
    score: float | None = None
    confidence_score: float | None = None
    confidence_breakdown: dict[str, float] | dict[str, Any]
    savings_bytes: int | None = None
    savings_pct: float | None = None
    decision: str
    reject_reason: str | None = None


class MovieListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    movies: list[MovieOut]


class DownloadOut(BaseModel):
    id: int
    movie_id: int
    release_title: str | None = None
    status: str
    progress_pct: float
    expected_size: int | None = None
    nzo_id: str | None = None
    storage_path: str | None = None
    cleanup_status: str | None = None
    retry_count: int
    grabbed_at: str | None = None
    last_error_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class ResumeDownloadsResponse(BaseModel):
    status: str
    resumed: int


class RetryDownloadResponse(BaseModel):
    success: bool
    message: str
    download_id: int
    retried_download_id: int | None = None


class OrphanCleanupResponse(BaseModel):
    success: bool
    message: str
    orphan_id: int


class DashboardStatsResponse(BaseModel):
    total_movies: int
    improved: int
    pending: int
    failed_items: int
    library_size_bytes: int
    total_savings_bytes: int
    active_downloads: int
    last_successful_scan: str | None = None


class SavingsHistoryPoint(BaseModel):
    date: str
    movie_title: str | None = None
    savings_bytes: int | None = None
    savings_pct: float | None = None
    cumulative_bytes: int


class RecentActivityItem(BaseModel):
    id: int
    event: str
    movie_title: str | None = None
    savings_bytes: int | None = None
    savings_pct: float | None = None
    created_at: str


class ActivityItemOut(BaseModel):
    id: int
    event: str
    movie_id: int | None = None
    movie_title: str | None = None
    old_file_path: str | None = None
    new_file_path: str | None = None
    old_size: int | None = None
    new_size: int | None = None
    savings_bytes: int | None = None
    savings_pct: float | None = None
    actor: str | None = None
    details: str | None = None
    created_at: str


class ActivityListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    activity: list[ActivityItemOut]
