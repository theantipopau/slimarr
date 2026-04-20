"""Settings API routes — read/write config and connection tests."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import get_current_user
from backend.config import get_config, reload_config, save_config

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user=Depends(get_current_user)):
    config = get_config()
    d = config.model_dump()
    # Redact secrets from response
    if "auth" in d:
        d["auth"]["secret_key"] = "***"
    return d


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
    return {"status": "saved"}


@router.post("/test/{service}")
async def test_connection(service: str, user=Depends(get_current_user)):
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

    if service == "prowlarr":
        from backend.integrations.prowlarr import ProwlarrClient
        return await ProwlarrClient().test_connection()

    if service == "radarr":
        from backend.integrations.radarr import RadarrClient
        return await RadarrClient().test_connection()

    if service.startswith("indexer-"):
        try:
            idx = int(service.split("-", 1)[1])
            indexer_cfg = config.indexers[idx]
        except (IndexError, ValueError):
            raise HTTPException(status_code=404, detail="Indexer not found")
        from backend.integrations.newznab import NewznabClient
        return await NewznabClient(indexer_cfg).test_connection()

    raise HTTPException(status_code=400, detail=f"Unknown service: {service}")


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
