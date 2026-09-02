"""
Library scanner — reads Plex, enriches with TMDB metadata, stores in database.
"""
from __future__ import annotations

import json
import asyncio
import os
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.parser import normalize_codec, normalize_resolution, parse_release_title
from backend.core.media_probe import probe_media_file
from backend.core.search_diagnostics import redact_text
from backend.core.storage import path_matches_prefix
from backend.database import Movie, async_session
from backend.realtime.events import emit_event


_scan_running = False
_scan_lock = asyncio.Lock()

# A movie whose TMDB lookup never resolves (e.g. a delisted/mismatched
# tmdb_id) has no poster forever, so `needs_poster` stays true and the scanner
# retries the same failing lookup on every single scan indefinitely. Skip
# retrying for a while after a failure instead of hitting TMDB again next scan.
_TMDB_ENRICHMENT_RETRY_COOLDOWN = timedelta(hours=24)
_tmdb_enrichment_failed_until: dict[str, datetime] = {}


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
    if _scan_lock.locked():
        logger.warning("Scan already in progress — skipping")
        return 0

    async with _scan_lock:
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
        # get_all_movies() is a synchronous plexapi call that walks every
        # section/movie/part over HTTP; run it off the event loop so a large
        # library or a slow Plex server doesn't stall the whole app (API
        # requests, the scheduler, WS events) for the whole scan.
        plex_movies = await asyncio.to_thread(plex.get_all_movies)
    except Exception as e:
        logger.error("Plex connection failed during scan: {}", redact_text(str(e)))
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
                # Capture existing probe data so we can skip re-probing NAS files
                existing_bitrate = existing.bitrate if existing else None
                existing_video_codec = existing.video_codec if existing else None
                existing_audio_codec = existing.audio_codec if existing else None
                existing_resolution = existing.resolution if existing else None
                existing_file_size = existing.file_size if existing else None

            if needs_poster:
                rating_key = pm["plex_rating_key"]
                retry_after = _tmdb_enrichment_failed_until.get(rating_key)
                skip_tmdb = bool(retry_after and retry_after > datetime.now(timezone.utc))

                if config.tmdb.api_key and not skip_tmdb:
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
                            _tmdb_enrichment_failed_until.pop(rating_key, None)
                        else:
                            _tmdb_enrichment_failed_until[rating_key] = (
                                datetime.now(timezone.utc) + _TMDB_ENRICHMENT_RETRY_COOLDOWN
                            )
                    except Exception as te:
                        logger.warning(
                            "TMDB lookup failed for {}: {}",
                            pm["title"],
                            redact_text(str(te)),
                        )
                        _tmdb_enrichment_failed_until[rating_key] = (
                            datetime.now(timezone.utc) + _TMDB_ENRICHMENT_RETRY_COOLDOWN
                        )

                if not poster_path and config.radarr.enabled and (pm.get("imdb_id") or existing_imdb):
                    try:
                        from backend.integrations.radarr import RadarrClient
                        imgs = await RadarrClient().get_movie_images(pm.get("imdb_id") or existing_imdb)
                        if imgs:
                            poster_path = imgs.get("poster_url")
                            backdrop_path = backdrop_path or imgs.get("fanart_url")
                    except Exception as re:
                        logger.warning(
                            "Radarr image fallback failed for {}: {}",
                            pm["title"],
                            redact_text(str(re)),
                        )

        except Exception as e:
            logger.warning(
                "Enrichment fetch failed for {}: {}",
                pm.get("title", "?"),
                redact_text(str(e)),
            )

        # Short-lived DB write per movie
        try:
            probe: dict[str, object] = {}
            file_path = pm.get("file_path")
            files_config = getattr(config, "files", None)
            # Fallback must match FilesConfig.enable_media_probe's actual default
            # (False) — a mismatched fallback here previously masked a real bug
            # elsewhere (replace_file skipping its post-replacement probe).
            enable_media_probe = bool(getattr(files_config, "enable_media_probe", False))
            nas_prefixes: list[str] = list(getattr(files_config, "nas_path_prefixes", None) or [])

            # Determine whether a probe is actually needed:
            # 1. Probe is enabled globally.
            # 2. Neither Plex nor the existing DB record have complete metadata.
            #    (Plex rarely returns bitrate, so we check the DB to avoid re-probing
            #     every scan for files that have already been characterised.)
            file_size_changed_for_probe = bool(
                existing_file_size
                and pm.get("file_size")
                and pm.get("file_size") != existing_file_size
            )
            db_has_full_probe = bool(
                existing_bitrate
                and existing_video_codec
                and existing_audio_codec
                and existing_resolution
                and not file_size_changed_for_probe
            )
            plex_has_full_probe = bool(
                pm.get("bitrate")
                and pm.get("video_codec")
                and pm.get("resolution")
                and pm.get("audio_codec")
            )
            should_probe = bool(
                enable_media_probe
                and file_path
                and not db_has_full_probe
                and not plex_has_full_probe
            )

            # Never probe files that live on a network path unless
            # files.nas_probe_enabled is explicitly set to true.
            # pymediainfo reads raw bytes off the network share which causes
            # unnecessary SMB/NFS traffic and can stall NAS storage on busy arrays.
            # Two cases are detected:
            #  a) Path matches a configured nas_path_prefixes entry (handles mapped
            #     drives like Z:\ and Linux mounts like /mnt/nas).
            #  b) Path is a UNC path (starts with \\ or //) — always network,
            #     regardless of whether nas_path_prefixes is configured.
            nas_probe_allowed = bool(getattr(files_config, "nas_probe_enabled", False))
            if should_probe and not nas_probe_allowed and file_path:
                fp_str = str(file_path)
                fp_norm = fp_str.replace("\\", "/")
                is_unc = fp_norm.startswith("//")
                is_nas_prefix = bool(nas_prefixes and path_matches_prefix(fp_str, nas_prefixes))
                if is_unc or is_nas_prefix:
                    logger.debug("Skipping media probe for network path: {}", file_path)
                    should_probe = False
            if should_probe:
                probe_timeout = float(getattr(files_config, "media_probe_timeout_seconds", 30))
                try:
                    probe = await asyncio.wait_for(
                        asyncio.to_thread(probe_media_file, str(file_path)),
                        timeout=probe_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "media_probe timed out after {}s for {} — skipping probe",
                        probe_timeout,
                        file_path,
                    )
                    probe = {}

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
                if pm.get("added_at"):
                    try:
                        parsed_added_at = datetime.fromisoformat(str(pm["added_at"]))
                        if parsed_added_at.tzinfo is not None:
                            parsed_added_at = parsed_added_at.astimezone(timezone.utc).replace(tzinfo=None)
                        movie.added_at = parsed_added_at
                    except ValueError:
                        pass
                new_file_size = pm.get("file_size") or 0

                # Plex reports file size from a cheap filesystem stat, so it's
                # always current — but it only re-analyzes the actual media
                # streams (resolution/codec/bitrate) on a deep scan, which a
                # plain library refresh doesn't guarantee. If the size changed
                # since our last scan (e.g. replace_file() just swapped the
                # file), Plex's stream fields may still describe the old file.
                # Trust whatever replace_file() already probed and wrote to
                # the DB in that case instead of letting stale Plex data
                # overwrite it and re-trigger a replacement loop.
                file_changed = bool(
                    existing_file_size and new_file_size and new_file_size != existing_file_size
                )
                stale_plex_stream_data = file_changed and not probe

                movie.file_size = new_file_size
                if stale_plex_stream_data and existing_resolution:
                    movie.resolution = existing_resolution
                else:
                    movie.resolution = normalize_resolution(pm.get("resolution") or probe.get("resolution") or "")
                if stale_plex_stream_data and existing_video_codec:
                    movie.video_codec = existing_video_codec
                else:
                    movie.video_codec = normalize_codec(pm.get("video_codec") or probe.get("video_codec") or "")
                if stale_plex_stream_data and existing_audio_codec:
                    movie.audio_codec = existing_audio_codec
                else:
                    movie.audio_codec = pm.get("audio_codec") or probe.get("audio_codec")
                if stale_plex_stream_data and existing_bitrate:
                    movie.bitrate = existing_bitrate
                else:
                    movie.bitrate = pm.get("bitrate") or probe.get("bitrate_kbps") or 0

                # A completed replacement already sets source_type from the actual
                # release title (more reliable than a filename guess) — only fill
                # it in here for movies Slimarr has never replaced yet, and only
                # when the filename itself carries a recognizable release tag
                # (a plain Plex-renamed "Movie (2022).mkv" won't match, which is
                # fine — it just leaves source_type unset rather than guessing).
                if not movie.source_type and movie.file_path:
                    filename_parsed = parse_release_title(os.path.basename(str(movie.file_path)))
                    if filename_parsed.source:
                        movie.source_type = filename_parsed.source

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
            logger.error("Error saving {}: {}", pm.get("title", "?"), redact_text(str(e)))

    await emit_event("scan:completed", {"total_movies": total})
    logger.info(f"Scan completed: {total} movies processed")
    return total

