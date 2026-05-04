"""Settings API routes — read/write config and connection tests."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.config import IndexerConfig, get_config, reload_config, save_config
from backend.utils.responses import validation_error, get_correlation_id

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user=Depends(get_current_user)):
    config = get_config()
    d = config.model_dump()
    # Redact secrets from response
    if "auth" in d:
        d["auth"]["secret_key"] = "***"
    return d


@router.get("/download-clients/capabilities")
async def download_client_capabilities(user=Depends(get_current_user)):
    from backend.integrations.download_client import (
        get_active_download_client_name,
        list_download_client_capabilities,
    )

    return {
        "active": get_active_download_client_name(),
        "clients": list_download_client_capabilities(),
    }


@router.put("")
async def update_settings(body: dict, user=Depends(get_current_user)):
    config = get_config()
    d = config.model_dump()
    _deep_merge(d, body)
    # Preserve redacted secret_key
    if body.get("auth", {}).get("secret_key") == "***":
        d["auth"]["secret_key"] = config.auth.secret_key

    from backend.config import SlimarrConfig, _CONFIG_PATH, save_config
    new_config = SlimarrConfig(**d)
    save_config(new_config, _CONFIG_PATH)
    reload_config()
    from backend.api.system import invalidate_services_health_cache
    invalidate_services_health_cache()
    return {"status": "saved"}


class IndexerTestBody(BaseModel):
    name: Optional[str] = ""
    url: Optional[str] = ""
    api_key: Optional[str] = ""
    token: Optional[str] = ""
    username: Optional[str] = ""
    password: Optional[str] = ""
    category: Optional[str] = ""
    categories: Optional[list[int]] = []


@router.post("/test/{service}")
async def test_connection(service: str, body: Optional[IndexerTestBody] = None, user=Depends(get_current_user)):
    config = get_config()

    if service == "plex":
        from backend.integrations.plex import PlexClient
        client = PlexClient()
        if body:
            client.url = body.url or config.plex.url
            client.token = body.token or body.api_key or config.plex.token
        if not client.url or not client.token:
            return {"success": False, "error": "Enter a Plex URL and token before testing."}
        return client.test_connection()

    if service == "tmdb":
        from backend.integrations.tmdb import TMDBClient
        client = TMDBClient()
        if body:
            client.api_key = body.api_key or config.tmdb.api_key
        if not client.api_key:
            return {"success": False, "error": "Enter a TMDB API key before testing."}
        return await client.test_connection()

    if service == "sabnzbd":
        from backend.integrations.sabnzbd import SABnzbdClient
        client = SABnzbdClient()
        if body:
            client.url = (body.url or config.sabnzbd.url).rstrip("/")
            client.api_key = body.api_key or config.sabnzbd.api_key
            client.category = body.category or config.sabnzbd.category
        if not client.url or not client.api_key:
            return {"success": False, "error": "Enter a SABnzbd URL and API key before testing."}
        return await client.test_connection()

    if service == "nzbget":
        from backend.integrations.nzbget import NZBGetClient
        client = NZBGetClient()
        if body:
            client.url = (body.url or config.nzbget.url).rstrip("/")
            client.username = body.username or config.nzbget.username
            client.password = body.password or config.nzbget.password
            client.category = body.category or config.nzbget.category
        if not client.url:
            return {"success": False, "error": "Enter an NZBGet URL before testing."}
        return await client.test_connection()

    if service == "prowlarr":
        from backend.integrations.prowlarr import ProwlarrClient
        client = ProwlarrClient()
        if body:
            client.url = (body.url or config.prowlarr.url).rstrip("/")
            client.api_key = body.api_key or config.prowlarr.api_key
        if not client.url or not client.url.startswith(("http://", "https://")):
            return {"success": False, "error": "Enter a valid Prowlarr URL (including http:// or https://) and try again."}
        if not client.api_key:
            return {"success": False, "error": "Enter a Prowlarr API key before testing."}
        return await client.test_connection()

    if service == "radarr":
        from backend.integrations.radarr import RadarrClient
        url = (body and body.url) or config.radarr.url
        api_key = (body and body.api_key) or config.radarr.api_key
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "error": "Enter a valid Radarr URL (including http:// or https://) and try again."}
        return await RadarrClient(url=url, api_key=api_key).test_connection()

    if service == "sonarr":
        from backend.integrations.sonarr import SonarrClient
        url = (body and body.url) or config.sonarr.url
        api_key = (body and body.api_key) or config.sonarr.api_key
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "error": "Enter a valid Sonarr URL (including http:// or https://) and try again."}
        return await SonarrClient(url=url, api_key=api_key).test_connection()

    if service.startswith("indexer-"):
        # Prefer body data (unsaved indexer) over saved config
        if body and body.url:
            indexer_cfg = IndexerConfig(
                name=body.name or "",
                url=body.url,
                api_key=body.api_key or "",
                categories=body.categories or [],
            )
        else:
            try:
                idx = int(service.split("-", 1)[1])
                indexer_cfg = config.indexers[idx]
            except (IndexError, ValueError):
                return {"success": False, "error": "Indexer not found in config. Fill in the URL and try again."}
        if not indexer_cfg.url or not indexer_cfg.url.startswith(("http://", "https://")):
            return {"success": False, "error": "Indexer URL is missing or invalid. Enter a full URL including http:// or https://."}
        from backend.integrations.newznab import NewznabClient
        return await NewznabClient(indexer_cfg).test_connection()

    raise validation_error(
        f"Unknown service: {service}",
        correlation_id=get_correlation_id(),
    )


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# Blacklist management endpoints
@router.get("/blacklist")
async def get_blacklist(user=Depends(get_current_user)):
    """Get all active blacklist entries."""
    from backend.core.blacklist import get_all_blacklist_entries
    
    entries = await get_all_blacklist_entries()
    return [
        {
            "id": e.id,
            "release_title": e.release_title,
            "release_hash": e.release_hash,
            "uploader": e.uploader,
            "indexer_name": e.indexer_name,
            "reason": e.reason,
            "manual": e.manual,
            "added_at": e.added_at.isoformat() if e.added_at else None,
            "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        }
        for e in entries
    ]


class BlacklistAddBody(BaseModel):
    release_title: str
    uploader: Optional[str] = None
    indexer_name: Optional[str] = None
    reason: str = "manual"
    expires_in_days: Optional[int] = 30


@router.post("/blacklist")
async def add_blacklist_entry(body: BlacklistAddBody, user=Depends(get_current_user)):
    """Add a release to the blacklist."""
    from backend.core.blacklist import add_to_blacklist
    
    entry = await add_to_blacklist(
        release_title=body.release_title,
        uploader=body.uploader,
        indexer_name=body.indexer_name,
        reason=body.reason,
        manual=True,
        expires_in_days=body.expires_in_days,
    )
    
    return {
        "success": True,
        "id": entry.id,
        "release_hash": entry.release_hash,
    }


@router.delete("/blacklist/{release_hash}")
async def remove_blacklist_entry(release_hash: str, user=Depends(get_current_user)):
    """Remove a release from the blacklist."""
    from backend.core.blacklist import remove_from_blacklist
    
    removed = await remove_from_blacklist(release_hash)
    
    return {
        "success": removed,
        "message": "Blacklist entry removed" if removed else "Entry not found",
    }
