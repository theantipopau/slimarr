"""Settings API routes — read/write config and connection tests."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.config import IndexerConfig, get_config, reload_config, save_config

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
    categories: Optional[list[int]] = []


@router.post("/test/{service}")
async def test_connection(service: str, body: Optional[IndexerTestBody] = None, user=Depends(get_current_user)):
    config = get_config()

    if service == "plex":
        from backend.integrations.plex import PlexClient
        return PlexClient().test_connection()

    if service == "tmdb":
        from backend.integrations.tmdb import TMDBClient
        return await TMDBClient().test_connection()

    if service == "sabnzbd":
        from backend.integrations.sabnzbd import SABnzbdClient
        return await SABnzbdClient().test_connection()

    if service == "nzbget":
        from backend.integrations.nzbget import NZBGetClient
        return await NZBGetClient().test_connection()

    if service == "prowlarr":
        if not config.prowlarr.url or not config.prowlarr.url.startswith(("http://", "https://")):
            return {"success": False, "error": "Prowlarr URL is not configured. Enter a valid URL and save first."}
        from backend.integrations.prowlarr import ProwlarrClient
        return await ProwlarrClient().test_connection()

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

    raise HTTPException(status_code=400, detail=f"Unknown service: {service}")


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
