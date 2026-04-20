"""TMDB image proxy — serves cached images, no auth required."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.core.image_cache import get_or_cache_image
from backend.database import Movie, async_session
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
        raise HTTPException(status_code=404, detail="Movie not found")

    tmdb_path_map = {
        "poster": movie.poster_path,
        "poster-500": movie.poster_path,
        "fanart": movie.backdrop_path,
    }

    if image_type not in tmdb_path_map:
        raise HTTPException(status_code=400, detail=f"Unknown image type: {image_type}")

    tmdb_path = tmdb_path_map[image_type]
    if not tmdb_path:
        raise HTTPException(status_code=404, detail="No image available")

    try:
        file_path = await get_or_cache_image(movie_id, image_type, tmdb_path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {e}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Cached image not found")

    return FileResponse(file_path, media_type="image/jpeg")
