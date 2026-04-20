"""
TMDB image cache — mirrors Radarr's MediaCover pattern.
Images are cached to data/MediaCover/{movie_id}/
"""
from __future__ import annotations

import os

import aiofiles

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


async def get_or_cache_image(movie_id: int, image_type: str, tmdb_path: str) -> str:
    """
    Returns the local file path for a cached TMDB image.
    Downloads and caches if not already present.
    """
    if image_type not in _SIZE_MAP:
        raise ValueError(f"Unknown image type: {image_type}")

    movie_dir = os.path.join(CACHE_DIR, str(movie_id))
    os.makedirs(movie_dir, exist_ok=True)

    file_path = os.path.join(movie_dir, _FILE_MAP[image_type])

    if not os.path.exists(file_path):
        client = TMDBClient()
        image_bytes = await client.download_image(tmdb_path, _SIZE_MAP[image_type])
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)

    return file_path
