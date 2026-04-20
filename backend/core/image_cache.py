"""Image cache — mirrors Radarr's MediaCover pattern.
Supports both TMDB path fragments and full remote URLs (e.g. from Radarr).
Images are cached to data/MediaCover/{movie_id}/
"""
from __future__ import annotations

import os

import aiofiles
import httpx

from backend.integrations.tmdb import TMDBClient

CACHE_DIR = "data/MediaCover"

_SIZE_MAP = {
    "poster": "w300",
    "poster-500": "w500",
    "fanart": "w1280",
}
_FILE_MAP = {
    "poster": "poster.jpg",
    "poster-500": "poster-500.jpg",
    "fanart": "fanart.jpg",
}


async def get_or_cache_image(movie_id: int, image_type: str, image_path: str) -> str:
    """
    Returns the local file path for a cached image.
    image_path can be a TMDB fragment (/abc.jpg) or a full URL (https://...).
    Downloads and caches if not already present.
    """
    if image_type not in _SIZE_MAP:
        raise ValueError(f"Unknown image type: {image_type}")

    movie_dir = os.path.join(CACHE_DIR, str(movie_id))
    os.makedirs(movie_dir, exist_ok=True)

    file_path = os.path.join(movie_dir, _FILE_MAP[image_type])

    if not os.path.exists(file_path):
        if image_path.startswith(("http://", "https://")):
            # Full URL (e.g. from Radarr) — download directly
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(image_path)
                resp.raise_for_status()
                image_bytes = resp.content
        else:
            # TMDB path fragment — build URL via TMDBClient
            client_tmdb = TMDBClient()
            image_bytes = await client_tmdb.download_image(image_path, _SIZE_MAP[image_type])

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)

    return file_path
