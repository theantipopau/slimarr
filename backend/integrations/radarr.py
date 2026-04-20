"""Radarr API v3 client (optional integration)."""
from __future__ import annotations

import httpx

from backend.config import get_config


class RadarrClient:
    def __init__(self) -> None:
        config = get_config()
        self.url = config.radarr.url.rstrip("/")
        self.api_key = config.radarr.api_key

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key}

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.url}/api/v3{endpoint}",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_movies(self) -> list[dict]:
        return await self._get("/movie")  # type: ignore[return-value]

    async def test_connection(self) -> dict:
        try:
            status = await self._get("/system/status")
            movies = await self._get("/movie")
            return {
                "success": True,
                "version": status.get("version", "unknown"),  # type: ignore[union-attr]
                "movie_count": len(movies),  # type: ignore[arg-type]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
