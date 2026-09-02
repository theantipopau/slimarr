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

        # Try an exact (case-insensitive) match first. Only fall back to a
        # 15-character prefix match if it's unambiguous — matching the wrong
        # series here means unmonitoring (and potentially deleting) the wrong
        # show, so an ambiguous prefix match fails loudly instead of guessing.
        target = title.lower().strip()
        match = None
        for s in series_list:
            if s.get("title", "").lower().strip() == target:
                match = s
                break

        if match is None:
            prefix_matches = [
                s for s in series_list
                if s.get("title", "").lower().strip().startswith(target[:15])
            ]
            if len(prefix_matches) == 1:
                match = prefix_matches[0]
                logger.warning(
                    "Sonarr: no exact title match for {!r}; using fuzzy prefix match to {!r} (id={})",
                    title,
                    match.get("title"),
                    match.get("id"),
                )
            elif len(prefix_matches) > 1:
                logger.warning(
                    "Sonarr: title {!r} has {} ambiguous prefix matches ({}) — refusing to guess",
                    title,
                    len(prefix_matches),
                    ", ".join(s.get("title", "?") for s in prefix_matches),
                )

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

    # ── Recommendation hand-off ──────────────────────────────────────────
    # Exists solely so a user can explicitly send a recommended series to
    # Sonarr — Slimarr never calls add_series() on its own initiative. See
    # docs/RECOMMENDATION_INTEGRATIONS.md.

    async def get_quality_profiles(self) -> list[dict]:
        async with self._http() as client:
            resp = await client.get(f"{self.url}/api/v3/qualityprofile", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get_root_folders(self) -> list[dict]:
        async with self._http() as client:
            resp = await client.get(f"{self.url}/api/v3/rootfolder", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def add_series(
        self,
        *,
        tvdb_id: int,
        title: str,
        root_folder_path: str,
        quality_profile_id: int,
        monitored: bool = True,
        search_now: bool = False,
    ) -> dict:
        """Adds a new series to Sonarr. Requires explicit root folder +
        quality profile from the caller (brief: 'present root folder, quality
        profile and monitoring settings')."""
        body = {
            "tvdbId": tvdb_id,
            "title": title,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "addOptions": {"searchForMissingEpisodes": search_now},
        }
        async with self._http() as client:
            resp = await client.post(f"{self.url}/api/v3/series", json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
