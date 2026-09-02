"""Shared API response/request models for OpenAPI consistency."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionStatusResponse(BaseModel):
    status: str
    movie_id: int | None = None
    task_id: str | None = None
    job_id: str | None = None
    search_result_id: int | None = None


class MovieRemoveResponse(BaseModel):
    success: bool
    message: str


class SearchTestRequest(BaseModel):
    title: str
    year: int | None = None
    imdb_id: str | None = None
    include_raw: bool = True


class SearchDiagnosticsResponse(BaseModel):
    checked_at: str
    degradation: dict[str, Any]
    recent_events: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    failure_heatmap: dict[str, int]
    indexer_reliability: dict[str, dict[str, Any]]
    last_successful_search: dict[str, Any] | None = None


class SearchDiagnosticsHistoryResponse(BaseModel):
    page: int
    per_page: int
    total: int
    pages: int
    items: list[dict[str, Any]]


class SearchTestResponse(BaseModel):
    query: dict[str, Any]
    providers: list[dict[str, Any]]
    raw_total: int
    parsed_total: int
    accepted_count: int
    rejected_count: int
    rejected_results: list[dict[str, Any]]
    accepted_results: list[dict[str, Any]]
    filtering_stages: list[dict[str, Any]]


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
    preferred_release_title: str | None = None
    quality_intent: str = "space_saver"
    force_keep: bool = False
    allow_larger_replacements: bool = False
    quality_profile_overrides: dict[str, Any] = Field(default_factory=dict)
    last_scanned: str | None = None
    last_searched: str | None = None


class MovieQualityIntentUpdateRequest(BaseModel):
    quality_intent: str = Field(
        pattern="^(space_saver|balanced|premium|reference|locked|pinned)$"
    )
    force_keep: bool = False
    allow_larger_replacements: bool = False
    quality_profile_overrides: dict[str, Any] = Field(default_factory=dict)


class SearchResultOut(BaseModel):
    id: int
    indexer_name: str
    release_title: str
    size: int
    resolution: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_channels: str | None = None
    source: str | None = None
    age_days: int | None = None
    hdr: str | None = None
    languages: list[str] = Field(default_factory=list)
    media_health_score: float | None = None
    media_health_rating: str | None = None
    media_health_reasons: list[str] = Field(default_factory=list)
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


class QueueSummaryResponse(BaseModel):
    active: int
    failed: int
    orphaned: int


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


class ServiceCheckResponse(BaseModel):
    success: bool
    error: str | None = None
    version: str | None = None
    message: str | None = None
    model_config = ConfigDict(extra="allow")


class DownloadClientCapabilitiesResponse(BaseModel):
    active: str
    clients: dict[str, Any]


class BlacklistEntryOut(BaseModel):
    id: int
    release_title: str
    release_hash: str | None = None
    uploader: str | None = None
    indexer_name: str | None = None
    reason: str | None = None
    manual: bool
    added_at: str | None = None
    expires_at: str | None = None


class AddBlacklistResponse(BaseModel):
    success: bool
    id: int
    release_hash: str | None = None


class RemoveBlacklistResponse(BaseModel):
    success: bool
    message: str


class SystemHealthResponse(BaseModel):
    status: str


class SystemInfoResponse(BaseModel):
    version: str
    python: str
    platform: str
    arch: str | None = None
    db_backend: str | None = None
    db_schema_version: int | None = None
    db_pool_checked_out: int | None = None
    in_docker: bool | None = None
    container_id: str | None = None
    uptime_seconds: int
    db_size_bytes: int
    port: int


class UpdateCheckResponse(BaseModel):
    update_available: bool
    current: str
    latest: str | None = None
    latest_name: str | None = None
    release_url: str | None = None
    published_at: str | None = None
    error: str | None = None


class RecyclingBinInfoResponse(BaseModel):
    enabled: bool
    path: str
    exists: bool
    files: int
    bytes: int


class RecyclingBinEmptyResponse(BaseModel):
    status: str
    removed_files: int
    removed_dirs: int
    freed_bytes: int


class DuplicateCleanupSampleItem(BaseModel):
    title: str
    best_file: str
    duplicate_count: int
    estimated_reclaimable_bytes: int
    confidence: str


class DuplicateCleanupPreviewResponse(BaseModel):
    status: str
    reason: str | None = None
    job_id: str | None = None
    movies_scanned: int
    duplicates_found: int
    estimated_reclaimable_bytes: int
    confidence: dict[str, int]
    sample: list[DuplicateCleanupSampleItem] = Field(default_factory=list)
    truncated: bool = False


class UtilitiesMaintenanceInsightsResponse(BaseModel):
    generated_at: str
    maintenance_score: float
    maintenance_state: str
    signals: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    telemetry: dict[str, Any]


class NasPressureResponse(BaseModel):
    checked_at: str
    pressure_state: str
    recommended_preset: str
    nas_prefixes: list[str] = Field(default_factory=list)
    nas_policy_enabled: bool
    recent: dict[str, Any]
    top_movies: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SystemStatusResponse(BaseModel):
    cycle: dict[str, Any]
    scheduler_running: bool
    jobs: list[dict[str, Any]]


class PreflightCheckItem(BaseModel):
    status: str
    name: str
    message: str
    detail: Any | None = None


class PreflightResponse(BaseModel):
    status: str
    checked_at: str
    checks: list[PreflightCheckItem]


class StoragePreflightResponse(BaseModel):
    purpose: str
    path: str
    classification: str
    matched_prefix: str | None = None
    exists: bool
    parent_path: str | None = None
    parent_exists: bool
    free_bytes: int | None = None
    required_bytes: int
    status: str
    messages: list[str] = Field(default_factory=list)


class StorageOperationsResponse(BaseModel):
    recent: list[dict[str, Any]]
    recent_failures: list[dict[str, Any]] = Field(default_factory=list)
    recent_failure_window_seconds: int = 3600
    counters: dict[str, int]
    history_size: int
    nas_policy: dict[str, Any]
    persisted: dict[str, Any] = Field(default_factory=dict)


class TelemetryPurgeResponse(BaseModel):
    status: str
    keep_days: int
    jobs_removed: int
    storage_operations_removed: int


class ReplacementRecoveryResponse(BaseModel):
    status: str
    checked_at: str
    records: list[dict[str, Any]] = Field(default_factory=list)


class JobsListResponse(BaseModel):
    jobs: list[dict[str, Any]]
    active_statuses: list[str] = Field(default_factory=list)


class JobDetailResponse(BaseModel):
    id: str
    kind: str
    status: str
    priority: int
    payload: dict[str, Any] = Field(default_factory=dict)
    progress_current: int
    progress_total: int
    heartbeat_at: str | None = None
    attempt: int
    max_attempts: int
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cancel_requested_at: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class JobActionResponse(BaseModel):
    status: str
    job: dict[str, Any] | None = None
    retried_job: dict[str, Any] | None = None


class IntegrationMatrixResponse(BaseModel):
    status: str
    active_download_client: str
    checked_at: str
    services: list[dict[str, Any]]


class HealthMatrixResponse(BaseModel):
    status: str
    checked_at: str
    components: dict[str, dict[str, Any]]


class DecisionAuditItem(BaseModel):
    id: int
    movie_id: int | None = None
    movie_title: str | None = None
    indexer_name: str | None = None
    release_title: str
    candidate_size: int | None = None
    local_size: int | None = None
    decision: str
    score: float | None = None
    confidence_score: float | None = None
    confidence_breakdown: dict[str, Any]
    media_health_score: float | None = None
    media_health_rating: str | None = None
    media_health_reasons: list[str] = Field(default_factory=list)
    savings_bytes: int | None = None
    savings_pct: float | None = None
    reject_reason: str | None = None
    notes: str | None = None
    created_at: str | None = None


class TVShowsListResponse(BaseModel):
    total: int
    stale_days_filter: int
    shows: list[dict[str, Any]]


# ── Recommendation & Collection Completion ───────────────────────────────
# See docs/RECOMMENDATION_ARCHITECTURE.md for the data model these mirror.


class RecommendationReasonOut(BaseModel):
    reason_code: str
    explanation: str
    source_movie_id: int | None = None
    source_provider: str | None = None
    weight: float | None = None


class StreamingAvailabilityOut(BaseModel):
    region: str
    provider_id: int
    provider_name: str
    display_priority: int | None = None
    availability_type: str
    source: str
    source_url: str | None = None
    checked_at: str | None = None
    stale: bool = False


class RecommendationOut(BaseModel):
    id: int
    candidate_id: int
    media_type: str
    title: str
    year: int | None = None
    tmdb_id: int
    imdb_id: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    overview: str | None = None
    popularity: float | None = None
    vote_average: float | None = None
    category: str
    score: float
    state: str
    created_at: str | None = None
    expires_at: str | None = None
    reasons: list[RecommendationReasonOut] = Field(default_factory=list)
    availability: list[StreamingAvailabilityOut] = Field(default_factory=list)
    already_in_plex: bool = False


class RecommendationListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    recommendations: list[RecommendationOut]


class RecommendationActionResponse(BaseModel):
    success: bool
    id: int
    state: str
    message: str | None = None


class RecommendationRefreshResponse(BaseModel):
    status: str
    job_id: str | None = None
    already_running: bool = False


class RecommendationCapabilitiesResponse(BaseModel):
    """Reports what each hand-off action can actually do right now — the
    brief's 'capability detection, disable gracefully' requirement made
    inspectable by the frontend rather than assumed."""
    radarr: dict[str, Any]
    sonarr: dict[str, Any]
    seerr: dict[str, Any]


class SendToRadarrRequest(BaseModel):
    root_folder_path: str
    quality_profile_id: int
    monitored: bool = True
    search_now: bool = False


class SendToSonarrRequest(BaseModel):
    root_folder_path: str
    quality_profile_id: int
    monitored: bool = True
    search_now: bool = False


class TVDeleteResponse(BaseModel):
    title: str
    plex_rating_key: str
    sonarr_unmonitored: bool
    plex_deleted: bool
    errors: list[str]
