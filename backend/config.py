"""
Configuration loader.
Priority: SLIMARR_* environment variables > config.yaml > defaults
"""
from __future__ import annotations
import os
import secrets
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
    name: str = ""
    url: str = ""
    api_key: str = ""
    categories: list[int] = [2000]


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
    allow_resolution_downgrade: bool = False
    downgrade_min_savings_percent: float = 40.0
    preferred_codecs: list[str] = ["av1", "h265"]
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
    plex_path_mappings: list[PathMapping] = []


class ScheduleConfig(BaseModel):
    mode: str = "nightly"
    timezone: str = "local"
    start_time: str = "01:00"
    end_time: str = "07:00"
    days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
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
    with open(target, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


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
