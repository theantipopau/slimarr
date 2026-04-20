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


async def scan_library() -> int:
    """
    Full library scan. Returns the number of movies processed.
    1. Get all movies from Plex
    2. Upsert each into the database
    3. Fetch TMDB metadata if missing
    4. Emit real-time events
    """
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

    async with async_session() as db:
        for i, pm in enumerate(plex_movies):
            try:
                result = await db.execute(
                    select(Movie).where(Movie.plex_rating_key == pm["plex_rating_key"])
                )
                movie = result.scalar_one_or_none()

                if movie is None:
                    movie = Movie(plex_rating_key=pm["plex_rating_key"], status="pending")
                    db.add(movie)

                # Update from Plex data
                movie.title = pm["title"]
                movie.year = pm.get("year")
                movie.imdb_id = pm.get("imdb_id") or movie.imdb_id
                movie.tmdb_id = pm.get("tmdb_id") or movie.tmdb_id
                movie.file_path = pm.get("file_path")
                movie.file_size = pm.get("file_size") or 0
                movie.resolution = normalize_resolution(pm.get("resolution") or "")
                movie.video_codec = normalize_codec(pm.get("video_codec") or "")
                movie.audio_codec = pm.get("audio_codec")
                movie.bitrate = pm.get("bitrate") or 0
                movie.last_scanned = datetime.now(timezone.utc)

                if movie.original_file_size is None:
                    movie.original_file_size = movie.file_size

                # TMDB enrichment (only if poster_path is missing)
                if not movie.poster_path and config.tmdb.api_key:
                    try:
                        tmdb_data = None
                        if movie.imdb_id:
                            tmdb_data = await tmdb.find_by_imdb(movie.imdb_id)
                        if not tmdb_data and movie.tmdb_id:
                            tmdb_data = await tmdb.get_movie(movie.tmdb_id)
                        if not tmdb_data:
                            tmdb_data = await tmdb.search_movie(movie.title, movie.year)

                        if tmdb_data:
                            movie.tmdb_id = tmdb_data.get("id") or movie.tmdb_id
                            movie.overview = tmdb_data.get("overview")
                            movie.poster_path = tmdb_data.get("poster_path")
                            movie.backdrop_path = tmdb_data.get("backdrop_path")
                            genres = tmdb_data.get("genres") or []
                            if genres and isinstance(genres[0], dict):
                                movie.genres = json.dumps([g["name"] for g in genres])
                    except Exception as te:
                        logger.warning(f"TMDB lookup failed for {movie.title}: {te}")

                await db.commit()

                await emit_event("scan:progress", {
                    "movie_id": movie.id,
                    "title": movie.title,
                    "current": i + 1,
                    "total": total,
                })

            except Exception as e:
                logger.error(f"Error scanning {pm.get('title', '?')}: {e}")
                await db.rollback()

    await emit_event("scan:completed", {"total_movies": total})
    logger.info(f"Scan completed: {total} movies processed")
    return total
