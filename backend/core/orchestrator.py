"""
Orchestrator — coordinates scan → search → download → replace.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.download_workflow import process_search_result_download
from backend.core.scanner import scan_library
from backend.core.searcher import search_for_movie
from backend.database import Movie, async_session
from backend.realtime.events import emit_event

_running = False
_stop_requested = False
_lock = asyncio.Lock()


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
    results = await search_for_movie(movie_id)
    accepted = [r for r in results if r["decision"] == "accept"]

    if not accepted:
        return {"movie_id": movie_id, "status": "no_candidates", "results": len(results)}

    # Best candidate (highest score)
    best = max(accepted, key=lambda x: x["score"])

    result = await process_search_result_download(best["id"])
    return {"movie_id": movie_id, "status": result.get("status", "unknown"), **result}


async def run_full_cycle() -> dict:
    """
    Full cycle: scan library → search + process movies that need improvement.
    """
    global _running, _stop_requested

    if _lock.locked():
        return {"status": "already_running"}

    async with _lock:
        if _running:
            return {"status": "already_running"}
        _running = True
        _stop_requested = False
    summary = {"scanned": 0, "processed": 0, "improved": 0, "failed": 0}

    try:
        await emit_event("cycle:started", {"timestamp": datetime.now(timezone.utc).isoformat()})
        summary["scanned"] = await scan_library()

        async with async_session() as db:
            result = await db.execute(
                select(Movie).where(Movie.status.in_(["pending", "failed"]))
            )
            movies = result.scalars().all()

        logger.info(f"Cycle: {len(movies)} movies to process")

        for movie in movies:
            if _stop_requested:
                logger.info("Cycle stopped by request")
                break

            try:
                result = await process_single_movie(movie.id)
                summary["processed"] += 1
                if result.get("status") == "replaced":
                    summary["improved"] += 1
                else:
                    summary["failed"] += 1
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
