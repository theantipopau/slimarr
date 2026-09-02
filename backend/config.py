"""
Configuration loader.
Priority: SLIMARR_* environment variables > config.yaml > defaults
"""
from __future__ import annotations
import os
import secrets
import tempfile
import yaml
from typing import Optional
from pydantic import BaseModel


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9494
    log_level: str = "info"
    # CORS allowed origins. Defaults to localhost only.
    # Add your LAN IP (e.g. 'http://192.168.1.10:9494') if accessing from another machine.
    allowed_origins: list[str] = [
        "http://localhost:9494",
        "http://127.0.0.1:9494",
    ]


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


class NzbgetConfig(BaseModel):
    url: str = ""
    username: str = ""
    password: str = ""
    category: str = "slimarr"


class IndexerConfig(BaseModel):
    enabled: bool = True
    name: str = ""
    url: str = ""
    api_key: str = ""
    categories: list[int] = [2000]
    rate_limit_cooldown_minutes: int = 720


class ProwlarrConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    api_key: str = ""


class RadarrConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    api_key: str = ""
    tls_verify: bool = True
    post_replace_action: str = "rescan"  # "rescan" | "rescan_unmonitor" | "none"


class SonarrConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    api_key: str = ""
    tls_verify: bool = True


class TmdbConfig(BaseModel):
    api_key: str = ""
    language: str = "en-US"


class ComparisonConfig(BaseModel):
    min_savings_percent: float = 10.0
    min_savings_mb_for_nas: int = 0
    allow_resolution_downgrade: bool = False
    downgrade_min_savings_percent: float = 40.0
    preferred_codecs: list[str] = ["av1", "h265"]
    preferred_audio_codecs: list[str] = []
    require_preferred_audio_match: bool = False
    preferred_language: str = "english"
    max_candidate_age_days: int = 3650
    minimum_file_size_mb: int = 500
    reject_upscaled: bool = True
    minimum_confidence_score: float = 55.0
    require_year_match: bool = True
    avoid_dolby_vision: bool = True
    allow_dolby_vision_with_hdr_fallback: bool = False
    require_english_audio: bool = True
    reject_dual_audio: bool = False
    reject_multi_audio: bool = False
    reject_hardcoded_subs: bool = True
    allow_size_increase_for_low_quality: bool = True
    max_size_increase_percent_for_quality_upgrade: float = 250.0
    max_quality_upgrade_size_gb: float = 8.0


class PathMapping(BaseModel):
    plex_path: str = ""
    local_path: str = ""


class FilesConfig(BaseModel):
    recycling_bin: str = ""   # Empty = delete originals directly (recommended). Set a path to keep copies.
    recycling_bin_cleanup_days: int = 30
    verify_after_download: bool = True
    enable_media_probe: bool = False
    nas_probe_enabled: bool = False  # Set true to allow pymediainfo to read NAS-mounted files during scans.
    media_probe_timeout_seconds: int = 30
    nas_path_prefixes: list[str] = []
    nas_max_write_gb_per_day: float = 150.0
    nas_max_replacements_per_day: int = 3
    nas_max_concurrent_operations: int = 1
    nas_failure_cooldown_minutes: int = 15
    nas_max_transfer_mbps: float = 50.0
    nas_copy_chunk_mb: int = 8
    plex_path_mappings: list[PathMapping] = []


class ScheduleConfig(BaseModel):
    mode: str = "nightly"
    timezone: str = "local"
    start_time: str = "01:00"
    end_time: str = "07:00"
    days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    min_cycle_interval_minutes: int = 60
    max_downloads_per_night: int = 10
    throttle_seconds: int = 30
    max_active_download_hours: int = 24


class AutomationConfig(BaseModel):
    dry_run: bool = False
    review_required: bool = False


class ExclusionConfig(BaseModel):
    movie_ids: list[int] = []
    title_keywords: list[str] = []
    folders: list[str] = []
    codecs: list[str] = []
    resolutions: list[str] = []
    minimum_file_size_mb: int = 0
    maximum_age_days: int = 0


class BlacklistConfig(BaseModel):
    auto_expire_days: int = 30
    max_retry_count: int = 3


class QualityConfig(BaseModel):
    stale_release_days: int = 30
    reject_uploader_health_below: float = 0.3


class RecommendationAIConfig(BaseModel):
    """Optional, provider-neutral, disabled by default. AI is used only to
    rerank/explain/theme an already-generated candidate set — it never
    invents titles, availability, or franchise relationships, and every
    AI-returned TMDB ID is re-validated against TMDB before use. See
    docs/RECOMMENDATION_ARCHITECTURE.md and docs/RECOMMENDATION_PRIVACY.md.
    """
    enabled: bool = False
    provider: str = "none"  # "none" | "openai_compatible" | "anthropic" | "ollama"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: int = 20
    # Separate, more restrictive opt-in than recommendations.use_plex_watch_history —
    # enabling watch-history-based scoring does NOT imply sharing it with an AI provider.
    share_watch_history: bool = False


class RecommendationsConfig(BaseModel):
    """See docs/RECOMMENDATION_ARCHITECTURE.md for the full data model and
    scoring design this backs. The whole feature is inert (no scans, no
    external calls beyond what tmdb: already makes for poster enrichment)
    until `enabled` is explicitly set true.
    """
    enabled: bool = False
    # ISO 3166-1 alpha-2 region code (e.g. "US", "AU", "GB"). Deliberately
    # empty by default rather than assuming a region — streaming-availability
    # lookups are skipped entirely until this is set.
    region: str = ""
    subscribed_providers: list[int] = []  # TMDB watch-provider IDs
    enabled_categories: list[str] = [
        "collection_completion",
        "sequel_prequel",
        "related_title",
    ]
    media_types: list[str] = ["movie"]
    minimum_score: float = 40.0
    languages: list[str] = []
    genres_include: list[str] = []
    genres_exclude: list[str] = []
    excluded_keywords: list[str] = []
    use_plex_watch_history: bool = False
    refresh_interval_hours: int = 24
    max_recommendations_retained: int = 500
    ai: RecommendationAIConfig = RecommendationAIConfig()


class SlimarrConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    auth: AuthConfig = AuthConfig()
    plex: PlexConfig = PlexConfig()
    download_client: str = "sabnzbd"
    sabnzbd: SabnzbdConfig = SabnzbdConfig()
    nzbget: NzbgetConfig = NzbgetConfig()
    indexers: list[IndexerConfig] = []
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    radarr: RadarrConfig = RadarrConfig()
    sonarr: SonarrConfig = SonarrConfig()
    tmdb: TmdbConfig = TmdbConfig()
    comparison: ComparisonConfig = ComparisonConfig()
    files: FilesConfig = FilesConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    automation: AutomationConfig = AutomationConfig()
    exclusions: ExclusionConfig = ExclusionConfig()
    blacklist: BlacklistConfig = BlacklistConfig()
    quality: QualityConfig = QualityConfig()
    recommendations: RecommendationsConfig = RecommendationsConfig()


# Module-level config path — can be overridden before first get_config() call
_CONFIG_PATH = os.environ.get("SLIMARR_CONFIG", "config.yaml")
_config: Optional[SlimarrConfig] = None


def set_config_path(path: str) -> None:
    global _CONFIG_PATH, _config
    _CONFIG_PATH = path
    _config = None  # Force reload


def get_config() -> SlimarrConfig:
    global _config
    if _config is None:
        _config = load_config(_CONFIG_PATH)
    return _config


def reload_config() -> SlimarrConfig:
    global _config
    _config = load_config(_CONFIG_PATH)
    return _config


def load_config(path: str = "config.yaml") -> SlimarrConfig:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        config = SlimarrConfig(**raw)
    else:
        config = SlimarrConfig()
    _apply_env_overrides(config)
    return config


# ── Environment variable overrides ───────────────────────────────────────────
# Env vars take precedence over the YAML file.
# This enables Docker-first deployments where secrets are injected via env.
#
# Supported variables (all prefixed SLIMARR_):
#
#   SLIMARR_HOST              server.host
#   SLIMARR_PORT              server.port
#   SLIMARR_LOG_LEVEL         server.log_level
#   SLIMARR_SECRET_KEY        auth.secret_key
#   SLIMARR_API_KEY           auth.api_key
#   SLIMARR_PLEX_URL          plex.url
#   SLIMARR_PLEX_TOKEN        plex.token
#   SLIMARR_SABNZBD_URL       sabnzbd.url
#   SLIMARR_SABNZBD_API_KEY   sabnzbd.api_key
#   SLIMARR_NZBGET_URL        nzbget.url
#   SLIMARR_NZBGET_USERNAME   nzbget.username
#   SLIMARR_NZBGET_PASSWORD   nzbget.password
#   SLIMARR_PROWLARR_URL      prowlarr.url
#   SLIMARR_PROWLARR_API_KEY  prowlarr.api_key
#   SLIMARR_RADARR_URL        radarr.url
#   SLIMARR_RADARR_API_KEY    radarr.api_key
#   SLIMARR_SONARR_URL        sonarr.url
#   SLIMARR_SONARR_API_KEY    sonarr.api_key
#   SLIMARR_TMDB_API_KEY      tmdb.api_key
#   SLIMARR_RECYCLING_BIN     files.recycling_bin
#   SLIMARR_ENABLE_MEDIA_PROBE files.enable_media_probe
#   SLIMARR_NAS_PATH_PREFIXES files.nas_path_prefixes (comma-separated)
#   SLIMARR_NAS_MAX_WRITE_GB_PER_DAY files.nas_max_write_gb_per_day
#   SLIMARR_NAS_MAX_REPLACEMENTS_PER_DAY files.nas_max_replacements_per_day
#   SLIMARR_NAS_MAX_CONCURRENT_OPERATIONS files.nas_max_concurrent_operations
#   SLIMARR_NAS_FAILURE_COOLDOWN_MINUTES files.nas_failure_cooldown_minutes
#   SLIMARR_NAS_MAX_TRANSFER_MBPS files.nas_max_transfer_mbps
#   SLIMARR_NAS_COPY_CHUNK_MB files.nas_copy_chunk_mb
#   SLIMARR_MIN_SAVINGS_MB_FOR_NAS comparison.min_savings_mb_for_nas
#   SLIMARR_MIN_CYCLE_INTERVAL_MINUTES schedule.min_cycle_interval_minutes
#   SLIMARR_MAX_DOWNLOADS_PER_NIGHT schedule.max_downloads_per_night
#   SLIMARR_THROTTLE_SECONDS schedule.throttle_seconds
#   SLIMARR_MAX_ACTIVE_DOWNLOAD_HOURS schedule.max_active_download_hours
#   SLIMARR_DOWNLOAD_CLIENT   download_client
#   SLIMARR_TZ                schedule.timezone  (alias)
#   TZ                        schedule.timezone  (standard Docker TZ)

_ENV_MAP: list[tuple[str, list[str]]] = [
    ("SLIMARR_HOST",             ["server", "host"]),
    ("SLIMARR_PORT",             ["server", "port"]),
    ("SLIMARR_LOG_LEVEL",        ["server", "log_level"]),
    ("SLIMARR_SECRET_KEY",       ["auth", "secret_key"]),
    ("SLIMARR_API_KEY",          ["auth", "api_key"]),
    ("SLIMARR_PLEX_URL",         ["plex", "url"]),
    ("SLIMARR_PLEX_TOKEN",       ["plex", "token"]),
    ("SLIMARR_SABNZBD_URL",      ["sabnzbd", "url"]),
    ("SLIMARR_SABNZBD_API_KEY",  ["sabnzbd", "api_key"]),
    ("SLIMARR_NZBGET_URL",       ["nzbget", "url"]),
    ("SLIMARR_NZBGET_USERNAME",  ["nzbget", "username"]),
    ("SLIMARR_NZBGET_PASSWORD",  ["nzbget", "password"]),
    ("SLIMARR_PROWLARR_URL",     ["prowlarr", "url"]),
    ("SLIMARR_PROWLARR_API_KEY", ["prowlarr", "api_key"]),
    ("SLIMARR_RADARR_URL",       ["radarr", "url"]),
    ("SLIMARR_RADARR_API_KEY",   ["radarr", "api_key"]),
    ("SLIMARR_SONARR_URL",       ["sonarr", "url"]),
    ("SLIMARR_SONARR_API_KEY",   ["sonarr", "api_key"]),
    ("SLIMARR_TMDB_API_KEY",     ["tmdb", "api_key"]),
    ("SLIMARR_RECYCLING_BIN",    ["files", "recycling_bin"]),
    ("SLIMARR_ENABLE_MEDIA_PROBE", ["files", "enable_media_probe"]),
    ("SLIMARR_NAS_PATH_PREFIXES", ["files", "nas_path_prefixes"]),
    ("SLIMARR_NAS_MAX_WRITE_GB_PER_DAY", ["files", "nas_max_write_gb_per_day"]),
    ("SLIMARR_NAS_MAX_REPLACEMENTS_PER_DAY", ["files", "nas_max_replacements_per_day"]),
    ("SLIMARR_NAS_MAX_CONCURRENT_OPERATIONS", ["files", "nas_max_concurrent_operations"]),
    ("SLIMARR_NAS_FAILURE_COOLDOWN_MINUTES", ["files", "nas_failure_cooldown_minutes"]),
    ("SLIMARR_NAS_MAX_TRANSFER_MBPS", ["files", "nas_max_transfer_mbps"]),
    ("SLIMARR_NAS_COPY_CHUNK_MB", ["files", "nas_copy_chunk_mb"]),
    ("SLIMARR_MIN_SAVINGS_MB_FOR_NAS", ["comparison", "min_savings_mb_for_nas"]),
    ("SLIMARR_MIN_CYCLE_INTERVAL_MINUTES", ["schedule", "min_cycle_interval_minutes"]),
    ("SLIMARR_MAX_DOWNLOADS_PER_NIGHT", ["schedule", "max_downloads_per_night"]),
    ("SLIMARR_THROTTLE_SECONDS", ["schedule", "throttle_seconds"]),
    ("SLIMARR_MAX_ACTIVE_DOWNLOAD_HOURS", ["schedule", "max_active_download_hours"]),
    ("SLIMARR_DOWNLOAD_CLIENT",  ["download_client"]),
]


def _apply_env_overrides(config: SlimarrConfig) -> None:
    """Overlay SLIMARR_* environment variables onto a loaded config object."""
    for env_key, path in _ENV_MAP:
        raw = os.environ.get(env_key)
        if raw is None or raw == "":
            continue
        _set_nested(config, path, raw)

    # TZ / SLIMARR_TZ → schedule.timezone
    tz = os.environ.get("SLIMARR_TZ") or os.environ.get("TZ")
    if tz:
        config.schedule.timezone = tz


def _set_nested(obj: object, path: list[str], value: str) -> None:
    """Set a (possibly nested) attribute on a pydantic model using a dotted path.

    Performs basic type coercion so string env values land as the correct type.
    """
    if len(path) == 1:
        field = path[0]
        # Coerce to the field's annotated type
        try:
            current = getattr(obj, field, None)
            if isinstance(current, bool):
                coerced = value.lower() in ("1", "true", "yes")
            elif isinstance(current, int):
                coerced: object = int(value)
            elif isinstance(current, float):
                coerced = float(value)
            elif isinstance(current, list):
                coerced = [
                    item.strip()
                    for item in value.replace("|", ",").split(",")
                    if item.strip()
                ]
            else:
                coerced = value
            setattr(obj, field, coerced)
        except (ValueError, TypeError):
            pass  # Leave existing value intact on coercion failure
        return
    child = getattr(obj, path[0], None)
    if child is not None:
        _set_nested(child, path[1:], value)


def save_config(config: SlimarrConfig, path: str | None = None) -> None:
    target = path or _CONFIG_PATH
    data = config.model_dump()
    parent = os.path.dirname(os.path.abspath(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".slimarr-config-", suffix=".tmp", dir=parent or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def ensure_secrets(config: SlimarrConfig, path: str | None = None) -> bool:
    """Generate secret_key and api_key if empty. Returns True if config was modified."""
    changed = False
    if not config.auth.secret_key:
        config.auth.secret_key = secrets.token_urlsafe(32)
        changed = True
    if not config.auth.api_key:
        config.auth.api_key = secrets.token_urlsafe(32)
        changed = True
    if changed:
        save_config(config, path)
    return changed
