"""
Orchestrator — coordinates scan → search → download → replace.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.blacklist import get_blacklist_reasons
from backend.core.download_workflow import process_search_result_download
from backend.core.exclusions import is_movie_excluded
from backend.core.schedule_window import is_within_schedule_window
from backend.core.search_diagnostics import (
    SearchPipelineDegraded,
    emit_search_warning,
    raise_if_degraded,
)
from backend.core.scanner import scan_library
from backend.core.parser import parse_release_title
from backend.core.searcher import search_for_movie
from backend.database import Movie, async_session
from backend.realtime.events import emit_event

_running = False
_stop_requested = False
_lock = asyncio.Lock()
_last_cycle_started_at: datetime | None = None


def is_running() -> bool:
    return _running


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True


def get_status() -> dict:
    return {"running": _running, "stop_requested": _stop_requested}


async def process_single_movie(movie_id: int) -> dict:
    """
    Run full pipeline for one movie: search → pick best → download → replace.
    Returns a summary dict.
    """
    from backend.config import get_config

    config = get_config()
    preferred_release_title: str | None = None
    force_keep = False
    slimarr_locked = False
    quality_intent = "space_saver"
    excluded = False
    excluded_reason: str | None = None
    async with async_session() as db:
        movie = await db.get(Movie, movie_id)
        if movie:
            preferred_release_title = movie.preferred_release_title
            force_keep = bool(movie.force_keep)
            slimarr_locked = bool(movie.slimarr_locked)
            quality_intent = movie.quality_intent or "space_saver"
            excluded, excluded_reason = is_movie_excluded(movie, config)

    if excluded:
        logger.info(
            "Skipping movie {}: excluded by exclusion rule ({})",
            movie_id,
            excluded_reason,
        )
        return {"movie_id": movie_id, "status": "excluded", "excluded_reason": excluded_reason}

    if force_keep or slimarr_locked or quality_intent in {"locked", "pinned"}:
        logger.info(
            "Skipping movie {}: protected by quality policy (locked={}, force_keep={}, intent={})",
            movie_id,
            slimarr_locked,
            force_keep,
            quality_intent,
        )
        return {"movie_id": movie_id, "status": "protected"}

    results = await search_for_movie(movie_id)
    # Releases that already failed (SABnzbd aborted, etc.) sit on the blacklist. Without this
    # filter the top-scored release is re-grabbed every cycle, which is what kept re-queuing the same NZBs.
    blocked = await _blacklisted_titles(results)
    accepted = [r for r in results if r["decision"] == "accept" and r.get("release_title") not in blocked]
    preferred = None
    if preferred_release_title:
        preferred_key = preferred_release_title.strip().lower()
        preferred_match = next(
            (
                r
                for r in results
                if str(r.get("release_title") or "").strip().lower() == preferred_key
            ),
            None,
        )
        if preferred_match and preferred_match.get("decision") == "accept" and preferred_match.get("release_title") not in blocked:
            preferred = preferred_match
        elif preferred_match:
            logger.info(
                "Preferred release override for movie {} was found but rejected ({}); falling back to normal scoring",
                movie_id,
                preferred_match.get("reject_reason") or "no reject reason",
            )
        else:
            logger.info(
                "Preferred release override not found for movie {} in this search pass: {}",
                movie_id,
                preferred_release_title,
            )

    if not accepted and not preferred:
        return {"movie_id": movie_id, "status": "no_candidates", "results": len(results)}

    selected = preferred if preferred else max(accepted, key=lambda x: x["score"])
    if preferred:
        logger.info(
            "Using preferred release override for movie {}: {}",
            movie_id,
            selected.get("release_title"),
        )

    if config.automation.dry_run:
        logger.info(
            f"Dry-run: selected {selected['release_title']} for movie {movie_id} "
            "without queueing a download"
        )
        return {
            "movie_id": movie_id,
            "status": "dry_run_candidate",
            "search_result_id": selected["id"],
            "results": len(results),
            "accepted": len(accepted),
            "used_preferred_override": bool(preferred),
        }

    if config.automation.review_required:
        async with async_session() as db:
            movie = await db.get(Movie, movie_id)
            if movie:
                movie.status = "review_required"
                movie.error_message = f"{len(accepted)} accepted candidate(s) awaiting approval"
                await db.commit()
        logger.info(f"Review required: movie {movie_id} has {len(accepted)} accepted candidate(s)")
        return {
            "movie_id": movie_id,
            "status": "review_required",
            "search_result_id": selected["id"],
            "results": len(results),
            "accepted": len(accepted),
            "used_preferred_override": bool(preferred),
        }

    result = await process_search_result_download(selected["id"])
    return {
        "movie_id": movie_id,
        "status": result.get("status", "unknown"),
        "used_preferred_override": bool(preferred),
        **result,
    }


async def _blacklisted_titles(results: list[dict]) -> set[str]:
    """Release titles from a search pass that are currently blacklisted."""
    keys = []
    for r in results:
        title = str(r.get("release_title") or "")
        keys.append((title, parse_release_title(title).uploader, r.get("indexer_name")))
    reasons = await get_blacklist_reasons(keys)
    return {keys[i][0] for i in reasons}


async def run_full_cycle() -> dict:
    """
    Full cycle: scan library → search + process movies that need improvement.
    """
    global _running, _stop_requested, _last_cycle_started_at
    from backend.config import get_config

    config = get_config()

    if _lock.locked():
        return {"status": "already_running"}

    async with _lock:
        if _running:
            return {"status": "already_running"}
        min_interval_minutes = max(0, int(getattr(config.schedule, "min_cycle_interval_minutes", 60) or 0))
        now_utc = datetime.now(timezone.utc)
        if _last_cycle_started_at and min_interval_minutes > 0:
            elapsed_seconds = (now_utc - _last_cycle_started_at).total_seconds()
            required_seconds = min_interval_minutes * 60
            if elapsed_seconds < required_seconds:
                remaining_seconds = int(required_seconds - elapsed_seconds)
                logger.info(
                    "Cycle skipped due cooldown: {}s remaining (min interval {}m)",
                    remaining_seconds,
                    min_interval_minutes,
                )
                return {
                    "status": "cooldown",
                    "remaining_seconds": remaining_seconds,
                    "min_cycle_interval_minutes": min_interval_minutes,
                }

        _last_cycle_started_at = now_utc
        _running = True
        _stop_requested = False
    summary = {
        "scanned": 0,
        "processed": 0,
        "improved": 0,
        "failed": 0,
        "skipped": 0,
        "excluded": 0,
        "no_candidates": 0,
        "review_required": 0,
        "stopped_reason": "",
    }

    try:
        await emit_event("cycle:started", {"timestamp": datetime.now(timezone.utc).isoformat()})
        summary["scanned"] = await scan_library()

        async with async_session() as db:
            result = await db.execute(
                select(Movie).where(
                    Movie.status.in_(["pending", "failed"]),
                    Movie.slimarr_locked == False,  # noqa: E712
                    Movie.force_keep == False,  # noqa: E712
                )
            )
            movies = result.scalars().all()

        logger.info(f"Cycle: {len(movies)} movies to process")

        configured_search_sources = int(bool(config.prowlarr.enabled and config.prowlarr.url)) + len(
            [idx for idx in config.indexers if idx.name and idx.url]
        )
        if configured_search_sources == 0 and movies:
            summary["stopped_reason"] = "search_not_configured"
            summary["failed"] = len(movies)
            message = "Cycle stopped: no enabled Prowlarr instance and no direct indexers are configured"
            logger.error(message)
            await emit_search_warning(
                message, {"queued_movies": len(movies)}, code="search_not_configured"
            )
            return summary

        try:
            raise_if_degraded()
        except SearchPipelineDegraded as e:
            summary["stopped_reason"] = "search_degraded"
            summary["failed"] = len(movies)
            logger.error(f"Cycle stopped before processing: search pipeline degraded ({e})")
            await emit_search_warning(
                "Automation stopped because the search pipeline is degraded.",
                {"reason": str(e), "queued_movies": len(movies)},
                code="search_degraded",
            )
            return summary

        max_downloads = max(1, int(config.schedule.max_downloads_per_night or 1))
        throttle_seconds = max(0, int(config.schedule.throttle_seconds or 0))

        for movie in movies:
            if _stop_requested:
                logger.info("Cycle stopped by request")
                break

            if summary["improved"] >= max_downloads:
                summary["stopped_reason"] = "max_downloads_reached"
                logger.info(
                    "Cycle stopped: reached max_downloads_per_night ({})",
                    max_downloads,
                )
                break

            if not is_within_schedule_window(config):
                logger.info("Cycle stopped: outside configured schedule window")
                break

            try:
                result = await process_single_movie(movie.id)
                summary["processed"] += 1
                status = str(result.get("status") or "")
                if status == "replaced":
                    summary["improved"] += 1
                    if throttle_seconds > 0:
                        logger.debug(
                            "Post-replacement throttle: sleeping {}s before next movie",
                            throttle_seconds,
                        )
                        await asyncio.sleep(throttle_seconds)
                elif status == "no_candidates":
                    summary["no_candidates"] += 1
                elif status == "excluded":
                    summary["excluded"] += 1
                elif status in {"protected", "skipped"}:
                    summary["skipped"] += 1
                elif status == "review_required":
                    summary["review_required"] += 1
                elif status in {"dry_run_candidate", "already_running"}:
                    summary["skipped"] += 1
                else:
                    summary["failed"] += 1
                raise_if_degraded()
            except SearchPipelineDegraded as e:
                summary["stopped_reason"] = "search_degraded"
                logger.error(f"Cycle stopped: search pipeline degraded ({e})")
                await emit_search_warning(
                    "Automation stopped because the search pipeline is degraded.",
                    {"reason": str(e), "processed": summary["processed"]},
                    code="search_degraded",
                )
                break
            except Exception as e:
                logger.error(f"Error processing {movie.title}: {e}")
                summary["failed"] += 1

    except Exception as e:
        logger.error(f"Cycle error: {e}")
    finally:
        _running = False
        _stop_requested = False
        await emit_event("cycle:completed", {**summary, "timestamp": datetime.now(timezone.utc).isoformat()})

    return summary
