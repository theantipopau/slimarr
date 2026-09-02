"""
Duplicate File Cleaner.

Scans the Plex library for movies with multiple files (duplicates/versions),
evaluates which one is the "best" (smallest size for its resolution/codec,
or highest resolution if different), and deletes the inferior files.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any
from loguru import logger

from backend.config import get_config
from backend.core.parser import get_codec_rank, get_resolution_rank
from backend.core.storage import move_path, preflight_storage_path, remove_path


def _part_score(p: dict) -> tuple:
    """Rank a media part: higher resolution > better codec > smaller size."""
    res_rank = get_resolution_rank(p["resolution"])
    codec_rank = get_codec_rank(p["codec"])
    return (res_rank, codec_rank, -p["size"])


def _duplicate_confidence(best_part: dict[str, Any], inferior: dict[str, Any]) -> str:
    """Estimate how confidently an inferior copy can be removed."""
    best_res = get_resolution_rank(str(best_part.get("resolution") or ""))
    inf_res = get_resolution_rank(str(inferior.get("resolution") or ""))
    best_codec = get_codec_rank(str(best_part.get("codec") or ""))
    inf_codec = get_codec_rank(str(inferior.get("codec") or ""))

    # High confidence when quality is clearly lower.
    if inf_res < best_res or (inf_res == best_res and inf_codec < best_codec):
        return "high"
    # Medium confidence when quality appears equal and file is larger.
    if inf_res == best_res and inf_codec == best_codec:
        return "medium"
    return "low"


def _collect_movie_parts(plex_movie) -> list[dict[str, Any]]:
    """Collect physical media parts for a Plex movie item."""
    movie_parts: list[dict[str, Any]] = []
    for media in plex_movie.media:
        for part in media.parts:
            if part.file and os.path.exists(part.file):
                movie_parts.append(
                    {
                        "file": part.file,
                        "size": part.size or os.path.getsize(part.file),
                        "resolution": str(media.videoResolution or ""),
                        "codec": str(media.videoCodec or ""),
                    }
                )
    return movie_parts


async def preview_duplicate_cleanup(max_movies_per_section: int = 500) -> dict[str, Any]:
    """Scan duplicates without deleting anything and return safe cleanup estimates."""
    from backend.integrations.plex import PlexClient

    config = get_config()
    if not config.plex.url or not config.plex.token:
        return {
            "status": "unavailable",
            "reason": "Plex not configured",
            "movies_scanned": 0,
            "duplicates_found": 0,
            "estimated_reclaimable_bytes": 0,
            "confidence": {"high": 0, "medium": 0, "low": 0},
            "sample": [],
        }

    plex = PlexClient()
    try:
        server = plex._get_server()
    except Exception as e:
        logger.error(f"Plex connection failed during duplicate preview: {e}")
        return {
            "status": "error",
            "reason": str(e),
            "movies_scanned": 0,
            "duplicates_found": 0,
            "estimated_reclaimable_bytes": 0,
            "confidence": {"high": 0, "medium": 0, "low": 0},
            "sample": [],
        }

    sections = plex.library_sections or [s.title for s in server.library.sections() if s.type == "movie"]
    summary: dict[str, Any] = {
        "status": "ok",
        "movies_scanned": 0,
        "duplicates_found": 0,
        "estimated_reclaimable_bytes": 0,
        "confidence": {"high": 0, "medium": 0, "low": 0},
        "sample": [],
        "truncated": False,
    }

    for section_name in sections:
        try:
            section = server.library.section(section_name)
        except Exception as e:
            logger.warning(f"Could not load section {section_name} for duplicate preview: {e}")
            continue

        for index, plex_movie in enumerate(section.all()):
            if index >= max_movies_per_section:
                summary["truncated"] = True
                break

            summary["movies_scanned"] += 1
            movie_parts = await asyncio.to_thread(_collect_movie_parts, plex_movie)
            if len(movie_parts) <= 1:
                continue

            sorted_parts = sorted(movie_parts, key=_part_score, reverse=True)
            best_part = sorted_parts[0]
            inferiors = sorted_parts[1:]

            reclaimable = 0
            confidence_bucket = "high"
            for inf in inferiors:
                reclaimable += int(inf.get("size") or 0)
                conf = _duplicate_confidence(best_part, inf)
                summary["confidence"][conf] += 1
                if conf == "low":
                    confidence_bucket = "low"
                elif conf == "medium" and confidence_bucket != "low":
                    confidence_bucket = "medium"

            summary["duplicates_found"] += 1
            summary["estimated_reclaimable_bytes"] += reclaimable

            if len(summary["sample"]) < 12:
                summary["sample"].append(
                    {
                        "title": plex_movie.title,
                        "best_file": best_part["file"],
                        "duplicate_count": len(inferiors),
                        "estimated_reclaimable_bytes": reclaimable,
                        "confidence": confidence_bucket,
                    }
                )

    return summary

async def scan_and_clean_duplicates() -> dict:
    """
    Finds movies with multiple media/parts in Plex, identifies the best version,
    and optionally moves the inferiors to the recycling bin or deletes them.
    Returns a summary of actions taken.
    """
    from backend.integrations.plex import PlexClient
    config = get_config()

    if not config.plex.url or not config.plex.token:
        logger.warning("Plex not configured — skipping duplicate scan")
        return {"movies_scanned": 0, "duplicates_found": 0, "files_removed": 0, "bytes_reclaimed": 0, "errors": 0}

    plex = PlexClient()
    try:
        server = plex._get_server()
    except Exception as e:
        logger.error(f"Plex connection failed during duplicate scan: {e}")
        return {"movies_scanned": 0, "duplicates_found": 0, "files_removed": 0, "bytes_reclaimed": 0, "errors": 1}

    sections = plex.library_sections or [
        s.title for s in server.library.sections() if s.type == "movie"
    ]

    summary = {
        "movies_scanned": 0,
        "duplicates_found": 0,
        "files_removed": 0,
        "bytes_reclaimed": 0,
        "errors": 0
    }

    for section_name in sections:
        try:
            section = server.library.section(section_name)
        except Exception as e:
            logger.warning(f"Could not load section {section_name}: {e}")
            continue

        section_files_removed = 0
        for plex_movie in section.all():
            summary["movies_scanned"] += 1

            movie_parts = await asyncio.to_thread(_collect_movie_parts, plex_movie)

            if len(movie_parts) <= 1:
                continue

            summary["duplicates_found"] += 1

            # Best = highest resolution, then best codec, then smallest size
            sorted_parts = sorted(movie_parts, key=_part_score, reverse=True)
            best_part = sorted_parts[0]
            inferiors = sorted_parts[1:]

            logger.info(
                f"Duplicate found for '{plex_movie.title}': keeping "
                f"{best_part['file']} "
                f"(Res: {best_part['resolution']}, Codec: {best_part['codec']}, "
                f"Size: {best_part['size'] / 1024**2:.0f} MB)"
            )

            for inf in inferiors:
                try:
                    file_path = inf["file"]
                    file_size = inf["size"]

                    if config.files.recycling_bin:
                        # Use a unique name to avoid collisions between movies
                        base = os.path.basename(file_path)
                        recycle_dest = os.path.join(config.files.recycling_bin, base)
                        if await asyncio.to_thread(os.path.exists, recycle_dest):
                            name, ext = os.path.splitext(base)
                            recycle_dest = os.path.join(
                                config.files.recycling_bin,
                                f"{name}_{plex_movie.ratingKey}{ext}",
                            )
                        # Classify/preflight the recycling bin destination before
                        # touching it (matches the pattern already used for the
                        # main nightly replacement recycle in replacer.py) - a
                        # recycling bin misconfigured onto an unreachable or full
                        # NAS share fails fast with a clear reason. Configuring a
                        # recycling bin is an explicit request to never permanently
                        # delete, so a blocked destination must skip this file
                        # (retried on the next scan) rather than fall back to a
                        # delete - that would silently destroy data exactly when
                        # the safety net the user asked for is unavailable.
                        recycle_preflight = await asyncio.to_thread(
                            preflight_storage_path,
                            recycle_dest,
                            config,
                            required_bytes=file_size,
                            purpose="duplicate_cleanup_recycle",
                        )
                        if recycle_preflight.status == "block":
                            logger.warning(
                                "Recycling bin preflight blocked move for {}; skipping (will retry next scan): {}",
                                file_path,
                                "; ".join(recycle_preflight.messages),
                            )
                            continue

                        await asyncio.to_thread(
                            os.makedirs, config.files.recycling_bin, exist_ok=True
                        )
                        await move_path(
                            file_path,
                            recycle_dest,
                            config,
                            purpose="duplicate_cleanup_recycle",
                            required_bytes=file_size,
                        )
                        logger.info(
                            f"Recycled inferior duplicate: {file_path} → {recycle_dest} "
                            f"(Res: {inf['resolution']}, Size: {file_size / 1024**2:.0f} MB)"
                        )
                    else:
                        await remove_path(file_path, config, purpose="duplicate_cleanup_delete")
                        logger.info(
                            f"Deleted inferior duplicate: {file_path} "
                            f"(Res: {inf['resolution']}, Size: {file_size / 1024**2:.0f} MB)"
                        )

                    summary["files_removed"] += 1
                    section_files_removed += 1
                    summary["bytes_reclaimed"] += file_size
                except Exception as e:
                    logger.error(f"Failed to remove duplicate file {inf['file']}: {e}")
                    summary["errors"] += 1

        # Only refresh this section if we actually removed files from it
        if section_files_removed > 0:
            server.library.section(section_name).update()

    return summary
