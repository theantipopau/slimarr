"""
TV Show Stale Media API.

Provides read-only show analysis (size, watch history) and a user-triggered
delete action. Nothing runs automatically — all actions require explicit
user confirmation from the UI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.config import get_config
from backend.realtime.events import emit_event
from loguru import logger

router = APIRouter(prefix="/tv", tags=["tv"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _show_is_stale(show: dict, days_threshold: int) -> bool:
    """Return True if the show has never been watched OR was last watched more
    than `days_threshold` days ago."""
    if show["never_watched"]:
        return True
    if show["last_watched_at"] and days_threshold > 0:
        last = datetime.fromisoformat(show["last_watched_at"].replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        return last < cutoff
    return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/shows")
async def list_shows(
    stale_days: int = 0,
    sort: str = "size",
    user=Depends(get_current_user),
):
    """
    Return all TV shows from Plex with watch history and disk usage.

    Query params:
      stale_days  — if > 0, only return shows not watched in this many days
                    (or never watched). 0 = return everything.
      sort        — 'size' (default, largest first) | 'title' | 'last_watched'
    """
    config = get_config()
    if not config.plex.url or not config.plex.token:
        raise HTTPException(status_code=503, detail="Plex is not configured")

    from backend.integrations.plex import PlexClient
    plex = PlexClient()

    try:
        shows = plex.get_all_shows()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Plex connection failed: {e}")

    # Apply stale filter
    if stale_days > 0:
        shows = [s for s in shows if _show_is_stale(s, stale_days)]

    # Sort
    if sort == "title":
        shows.sort(key=lambda s: s["title"].lower())
    elif sort == "last_watched":
        # Never-watched float to the top, then oldest-watched first
        shows.sort(key=lambda s: s["last_watched_at"] or "", reverse=False)
    else:  # default: size descending
        shows.sort(key=lambda s: s["total_size_bytes"], reverse=True)

    return {
        "total": len(shows),
        "stale_days_filter": stale_days,
        "shows": shows,
    }


class DeleteShowRequest(BaseModel):
    plex_rating_key: str
    title: str
    unmonitor_sonarr: bool = True
    """If True and Sonarr is configured, also unmonitor the series in Sonarr
    so it will not be re-downloaded."""


@router.delete("/shows/{plex_rating_key}")
async def delete_show(
    plex_rating_key: str,
    body: DeleteShowRequest,
    user=Depends(get_current_user),
):
    """
    User-triggered deletion of a TV show.

    Steps:
      1. Unmonitor in Sonarr (if enabled and requested) — prevents re-download
      2. Delete via Plex API (removes files from disk)

    This endpoint intentionally requires an explicit body so the client must
    confirm the title and options before we touch anything.
    """
    if body.plex_rating_key != plex_rating_key:
        raise HTTPException(status_code=400, detail="Rating key mismatch")

    config = get_config()
    if not config.plex.url or not config.plex.token:
        raise HTTPException(status_code=503, detail="Plex is not configured")

    from backend.integrations.plex import PlexClient
    plex = PlexClient()

    result = {
        "title": body.title,
        "plex_rating_key": plex_rating_key,
        "sonarr_unmonitored": False,
        "plex_deleted": False,
        "errors": [],
    }

    # Step 1: Sonarr unmonitor
    if body.unmonitor_sonarr and config.sonarr.enabled and config.sonarr.url and config.sonarr.api_key:
        try:
            from backend.integrations.sonarr import SonarrClient
            sonarr = SonarrClient()
            unmonitored = await sonarr.unmonitor_series_by_title(body.title)
            result["sonarr_unmonitored"] = unmonitored
            if unmonitored:
                logger.info(f"TV Cleanup: Unmonitored '{body.title}' in Sonarr")
            else:
                logger.warning(f"TV Cleanup: '{body.title}' not found in Sonarr — skipping unmonitor")
        except Exception as e:
            err = f"Sonarr unmonitor failed: {e}"
            logger.error(err)
            result["errors"].append(err)
            # Don't abort — still proceed with Plex deletion

    # Step 2: Delete from Plex (removes files from disk)
    try:
        deleted = plex.delete_show(plex_rating_key)
        result["plex_deleted"] = deleted
        if deleted:
            logger.info(f"TV Cleanup: Deleted '{body.title}' from Plex and disk")
        else:
            err = "Plex deletion returned False — check that 'Allow media deletion' is enabled in Plex server settings"
            logger.error(err)
            result["errors"].append(err)
    except Exception as e:
        err = f"Plex deletion failed: {e}"
        logger.error(err)
        result["errors"].append(err)

    await emit_event("tv:deleted", {
        "title": body.title,
        "plex_rating_key": plex_rating_key,
        "success": result["plex_deleted"],
    })

    if result["errors"] and not result["plex_deleted"]:
        raise HTTPException(status_code=500, detail="; ".join(result["errors"]))

    return result
