"""Sonarr API client — used for unmonitoring series before TV show deletion."""
from __future__ import annotations

import httpx
from loguru import logger
from backend.config import get_config


class SonarrClient:
    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        config = get_config()
        self.url = (url or config.sonarr.url).rstrip("/")
        self.api_key = api_key or config.sonarr.api_key
        self.tls_verify = config.sonarr.tls_verify

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    def _http(self) -> httpx.AsyncClient:
        """TLS verification is configurable via sonarr.tls_verify."""
        return httpx.AsyncClient(timeout=15.0, verify=self.tls_verify)

    async def get_all_series(self) -> list[dict]:
        async with self._http() as client:
            resp = await client.get(f"{self.url}/api/v3/series", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def unmonitor_series_by_title(self, title: str) -> bool:
        """
        Find a series in Sonarr by title (fuzzy match) and set monitored=False.
        Returns True if a match was found and updated, False if not found.
        """
        series_list = await self.get_all_series()

        # Try exact match first, then case-insensitive, then prefix
        target = title.lower().strip()
        match = None
        for s in series_list:
            if s.get("title", "").lower().strip() == target:
                match = s
                break
        if match is None:
            for s in series_list:
                if s.get("title", "").lower().strip().startswith(target[:15]):
                    match = s
                    break

        if match is None:
            return False

        series_id = match["id"]
        match["monitored"] = False
        # Also unmonitor all seasons
        for season in match.get("seasons", []):
            season["monitored"] = False

        async with self._http() as client:
            resp = await client.put(
                f"{self.url}/api/v3/series/{series_id}",
                json=match,
                headers=self._headers(),
            )
            resp.raise_for_status()

        logger.info(f"Sonarr: unmonitored series '{match['title']}' (id={series_id})")
        return True

    async def test_connection(self) -> dict:
        try:
            async with self._http() as client:
                resp = await client.get(
                    f"{self.url}/api/v3/system/status",
                    headers=self._headers(),
                )
                resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "version": data.get("version", ""),
                "app_name": data.get("appName", "Sonarr"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
