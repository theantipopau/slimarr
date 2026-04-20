"""Prowlarr unified indexer proxy client."""
from __future__ import annotations

import httpx

from backend.config import get_config


class ProwlarrClient:
    def __init__(self) -> None:
        config = get_config()
        self.url = config.prowlarr.url.rstrip("/")
        self.api_key = config.prowlarr.api_key

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key}

    async def get_indexers(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.url}/api/v1/indexer", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def search(self, query: str = "", imdb_id: str = "",
                     categories: list[int] | None = None) -> list[dict]:
        params: dict = {"type": "movie"}
        if query:
            params["query"] = query
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.url}/api/v1/search",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            results = resp.json()

        return [
            {
                "indexer_name": r.get("indexer", "Prowlarr"),
                "release_title": r.get("title", ""),
                "nzb_url": r.get("downloadUrl") or r.get("guid", ""),
                "size": r.get("size", 0),
                "imdb_id": str(r.get("imdbId", "")),
                "pub_date": r.get("publishDate", ""),
                "grabs": r.get("grabs", 0),
            }
            for r in results
        ]

    async def test_connection(self) -> dict:
        try:
            indexers = await self.get_indexers()
            return {
                "success": True,
                "indexer_count": len(indexers),
                "indexers": [i.get("name") for i in indexers],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
