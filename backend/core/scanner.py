"""
Library scanner — reads Plex, enriches with TMDB metadata, stores in database.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.parser import normalize_codec, normalize_resolution
from backend.database import ActivityLog, Movie, async_session
from backend.realtime.events import emit_event


_scan_running = False


def is_scan_running() -> bool:
    return _scan_running


async def scan_library() -> int:
    """
    Full library scan. Returns the number of movies processed.
    1. Get all movies from Plex
    2. Upsert each into the database
    3. Fetch TMDB metadata if missing
    4. Emit real-time events
    """
    global _scan_running
    if _scan_running:
        logger.warning("Scan already in progress — skipping duplicate trigger")
        return 0

    _scan_running = True
    try:
        return await _run_scan()
    finally:
        _scan_running = False


async def _run_scan() -> int:
    from backend.integrations.plex import PlexClient
    from backend.integrations.tmdb import TMDBClient
    from backend.config import get_config

    config = get_config()

    if not config.plex.url or not config.plex.token:
        logger.warning("Plex not configured — skipping library scan")
        return 0

    plex = PlexClient()
    tmdb = TMDBClient()

    try:
        plex_movies = plex.get_all_movies()
    except Exception as e:
        logger.error(f"Plex connection failed during scan: {e}")
        return 0

    total = len(plex_movies)
    await emit_event("scan:started", {"total_movies": total})
    logger.info(f"Scan started: {total} movies in Plex")

    for i, pm in enumerate(plex_movies):
        # Fetch enrichment data OUTSIDE the DB session to avoid long-held locks
        poster_path: str | None = None
        backdrop_path: str | None = None
        overview: str | None = None
        tmdb_id_found: int | None = None
        genres_json: str | None = None

        try:
            # We need the existing movie's current poster to decide whether to fetch
            async with async_session() as db:
                result = await db.execute(
                    select(Movie).where(Movie.plex_rating_key == pm["plex_rating_key"])
                )
                existing = result.scalar_one_or_none()
                needs_poster = existing is None or not existing.poster_path
                existing_imdb = existing.imdb_id if existing else None
                existing_tmdb = existing.tmdb_id if existing else None
                existing_overview = existing.overview if existing else None

            if needs_poster:
                if config.tmdb.api_key:
                    try:
                        tmdb_data = None
                        imdb_id = pm.get("imdb_id") or existing_imdb
                        tmdb_id = pm.get("tmdb_id") or existing_tmdb
                        if imdb_id:
                            tmdb_data = await tmdb.find_by_imdb(imdb_id)
                        if not tmdb_data and tmdb_id:
                            tmdb_data = await tmdb.get_movie(tmdb_id)
                        if not tmdb_data:
                            tmdb_data = await tmdb.search_movie(pm["title"], pm.get("year"))
                        if tmdb_data:
                            tmdb_id_found = tmdb_data.get("id")
                            overview = tmdb_data.get("overview")
                            poster_path = tmdb_data.get("poster_path")
                            backdrop_path = tmdb_data.get("backdrop_path")
                            genres = tmdb_data.get("genres") or []
                            if genres and isinstance(genres[0], dict):
                                genres_json = json.dumps([g["name"] for g in genres])
                    except Exception as te:
                        logger.warning(f"TMDB lookup failed for {pm['title']}: {te}")

                if not poster_path and config.radarr.enabled and (pm.get("imdb_id") or existing_imdb):
                    try:
                        from backend.integrations.radarr import RadarrClient
                        imgs = await RadarrClient().get_movie_images(pm.get("imdb_id") or existing_imdb)
                        if imgs:
                            poster_path = imgs.get("poster_url")
                            backdrop_path = backdrop_path or imgs.get("fanart_url")
                    except Exception as re:
                        logger.warning(f"Radarr image fallback failed for {pm['title']}: {re}")

        except Exception as e:
            logger.warning(f"Enrichment fetch failed for {pm.get('title', '?')}: {e}")

        # Short-lived DB write per movie
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Movie).where(Movie.plex_rating_key == pm["plex_rating_key"])
                )
                movie = result.scalar_one_or_none()

                if movie is None:
                    movie = Movie(plex_rating_key=pm["plex_rating_key"], status="pending")
                    db.add(movie)

                movie.title = pm["title"]
                movie.year = pm.get("year")
                movie.imdb_id = pm.get("imdb_id") or movie.imdb_id
                movie.tmdb_id = tmdb_id_found or pm.get("tmdb_id") or movie.tmdb_id
                movie.file_path = pm.get("file_path")
                movie.file_size = pm.get("file_size") or 0
                movie.resolution = normalize_resolution(pm.get("resolution") or "")
                movie.video_codec = normalize_codec(pm.get("video_codec") or "")
                movie.audio_codec = pm.get("audio_codec")
                movie.bitrate = pm.get("bitrate") or 0
                movie.last_scanned = datetime.now(timezone.utc)

                if movie.original_file_size is None:
                    movie.original_file_size = movie.file_size

                if poster_path:
                    movie.poster_path = poster_path
                if backdrop_path:
                    movie.backdrop_path = backdrop_path
                if overview and not movie.overview:
                    movie.overview = overview
                if genres_json and not movie.genres:
                    movie.genres = genres_json

                await db.commit()

                await emit_event("scan:progress", {
                    "movie_id": movie.id,
                    "title": movie.title,
                    "current": i + 1,
                    "total": total,
                })

        except Exception as e:
            logger.error(f"Error saving {pm.get('title', '?')}: {e}")

    await emit_event("scan:completed", {"total_movies": total})
    logger.info(f"Scan completed: {total} movies processed")
    return total

