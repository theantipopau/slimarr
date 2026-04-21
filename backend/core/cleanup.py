"""
Duplicate File Cleaner.

Scans the Plex library for movies with multiple files (duplicates/versions),
evaluates which one is the "best" (smallest size for its resolution/codec,
or highest resolution if different), and deletes the inferior files.
"""
from __future__ import annotations

import os
import shutil
from loguru import logger

from backend.config import get_config
from backend.core.parser import get_codec_rank, get_resolution_rank


def _part_score(p: dict) -> tuple:
    """Rank a media part: higher resolution > better codec > smaller size."""
    res_rank = get_resolution_rank(p["resolution"])
    codec_rank = get_codec_rank(p["codec"])
    return (res_rank, codec_rank, -p["size"])

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

            # Gather all physical parts belonging to this movie
            movie_parts = []
            for media in plex_movie.media:
                for part in media.parts:
                    if part.file and os.path.exists(part.file):
                        movie_parts.append({
                            "file": part.file,
                            "size": part.size or os.path.getsize(part.file),
                            "resolution": str(media.videoResolution or ""),
                            "codec": str(media.videoCodec or ""),
                        })

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
                        os.makedirs(config.files.recycling_bin, exist_ok=True)
                        # Use a unique name to avoid collisions between movies
                        base = os.path.basename(file_path)
                        recycle_dest = os.path.join(config.files.recycling_bin, base)
                        if os.path.exists(recycle_dest):
                            name, ext = os.path.splitext(base)
                            recycle_dest = os.path.join(
                                config.files.recycling_bin,
                                f"{name}_{plex_movie.ratingKey}{ext}",
                            )
                        shutil.move(file_path, recycle_dest)
                        logger.info(
                            f"Recycled inferior duplicate: {file_path} → {recycle_dest} "
                            f"(Res: {inf['resolution']}, Size: {file_size / 1024**2:.0f} MB)"
                        )
                    else:
                        os.remove(file_path)
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