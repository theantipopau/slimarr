"""TMDB image proxy — serves cached images, no auth required."""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.core.image_cache import get_or_cache_image
from backend.database import Movie, async_session
from backend.utils.responses import not_found, validation_error, internal_error, get_correlation_id
from sqlalchemy import select

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{movie_id}/{image_type}")
async def get_image(movie_id: int, image_type: str):
    """
    Serve a cached movie image. Downloads from TMDB on cache miss.
    image_type: poster | poster-500 | fanart
    """
    async with async_session() as db:
        result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = result.scalar_one_or_none()

    if not movie:
        raise not_found("Movie", correlation_id=get_correlation_id())

    tmdb_path_map = {
        "poster": movie.poster_path,
        "poster-500": movie.poster_path,
        "fanart": movie.backdrop_path,
    }

    if image_type not in tmdb_path_map:
        raise validation_error(
            f"Unknown image type: {image_type}",
            correlation_id=get_correlation_id(),
        )

    tmdb_path = tmdb_path_map[image_type]
    if not tmdb_path:
        raise not_found("Image", correlation_id=get_correlation_id())

    try:
        file_path = await get_or_cache_image(movie_id, image_type, tmdb_path)
    except Exception as e:
        raise internal_error(
            f"Image fetch failed: {e}",
            correlation_id=get_correlation_id(),
        )

    if not os.path.exists(file_path):
        raise not_found("Cached image", correlation_id=get_correlation_id())

    return FileResponse(file_path, media_type="image/jpeg")
