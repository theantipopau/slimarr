"""TMDB API client."""
from __future__ import annotations

from typing import Optional

import httpx

from backend.config import get_config

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


class TMDBClient:
    def __init__(self) -> None:
        config = get_config()
        self.api_key = config.tmdb.api_key
        self.language = config.tmdb.language

    def _params(self, extra: dict | None = None) -> dict:
        p = {"api_key": self.api_key, "language": self.language}
        if extra:
            p.update(extra)
        return p

    async def search_movie(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        params = self._params({"query": title})
        if year:
            params["year"] = year
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{TMDB_BASE}/search/movie", params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0] if results else None

    async def get_movie(self, tmdb_id: int) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{TMDB_BASE}/movie/{tmdb_id}", params=self._params())
            resp.raise_for_status()
            return resp.json()

    async def find_by_imdb(self, imdb_id: str) -> Optional[dict]:
        params = {"api_key": self.api_key, "external_source": "imdb_id"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{TMDB_BASE}/find/{imdb_id}", params=params)
            resp.raise_for_status()
            results = resp.json().get("movie_results", [])
            return results[0] if results else None

    async def download_image(self, path: str, size: str = "w300") -> bytes:
        url = f"{TMDB_IMAGE_BASE}/{size}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def test_connection(self) -> dict:
        try:
            result = await self.search_movie("The Matrix", 1999)
            return {"success": True, "test_title": result.get("title") if result else "no results"}
        except Exception as e:
            return {"success": False, "error": str(e)}
