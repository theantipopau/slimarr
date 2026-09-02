"""Radarr API v3 client (optional integration)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from loguru import logger

from backend.config import get_config
from backend.integrations.shared_http import get_shared_client


def _shared_client(tls_verify: bool) -> httpx.AsyncClient | None:
    """Thin per-module wrapper around the shared reuse-or-private decision
    (backend.integrations.shared_http) - kept as a real function here (not
    just an alias) so existing tests can still patch it per-module. See
    docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md (A5)."""
    return get_shared_client(tls_verify=tls_verify)


class RadarrClient:
    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        config = get_config()
        self.url = (url or config.radarr.url).rstrip("/")
        self.api_key = api_key or config.radarr.api_key
        self.tls_verify = config.radarr.tls_verify

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key}

    @asynccontextmanager
    async def _client(self):
        client = _shared_client(self.tls_verify)
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=15.0, verify=self.tls_verify)
        try:
            yield client
        finally:
            if owns_client:
                await client.aclose()

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        async with self._client() as client:
            resp = await client.get(
                f"{self.url}/api/v3{endpoint}",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, endpoint: str, body: dict) -> dict:
        async with self._client() as client:
            resp = await client.post(
                f"{self.url}/api/v3{endpoint}",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def _put(self, endpoint: str, body: dict) -> None:
        async with self._client() as client:
            resp = await client.put(
                f"{self.url}/api/v3{endpoint}",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def get_movies(self) -> list[dict]:
        return await self._get("/movie")  # type: ignore[return-value]

    async def find_movie_by_imdb(self, imdb_id: str) -> dict | None:
        """Return the Radarr movie record matching an IMDb ID, or None."""
        movies = await self.get_movies()
        for m in movies:  # type: ignore[union-attr]
            if m.get("imdbId") == imdb_id:
                return m
        return None

    async def get_movie_images(self, imdb_id: str) -> dict | None:
        """Return poster/fanart remote URLs from Radarr for a given IMDb ID."""
        try:
            movie = await self.find_movie_by_imdb(imdb_id)
            if not movie:
                return None
            images = movie.get("images", [])
            result: dict = {}
            for img in images:
                cover = img.get("coverType", "")
                url = img.get("remoteUrl") or img.get("url", "")
                if cover == "poster" and url:
                    result["poster_url"] = url
                elif cover == "fanart" and url:
                    result["fanart_url"] = url
            return result or None
        except Exception:
            return None

    async def rescan_movie(self, radarr_id: int) -> None:
        """Trigger Radarr to rescan a movie folder (so it picks up the new file)."""
        await self._post("/command", {"name": "RescanMovie", "movieId": radarr_id})

    async def unmonitor_movie(self, radarr_id: int, movie_payload: dict) -> None:
        """Set a movie to unmonitored in Radarr so it won't be re-upgraded."""
        movie_payload["monitored"] = False
        await self._put(f"/movie/{radarr_id}", movie_payload)

    async def rescan_by_imdb(self, imdb_id: str) -> bool:
        """Find movie in Radarr by IMDb ID and trigger a rescan. Returns True if found."""
        try:
            movie = await self.find_movie_by_imdb(imdb_id)
            if movie:
                await self.rescan_movie(movie["id"])
                return True
        except Exception as e:
            logger.warning("Radarr rescan_by_imdb failed for imdb_id={}: {}", imdb_id, e)
        return False

    async def post_replace_action(self, imdb_id: str, action: str) -> bool:
        """
        Perform the configured post-replace action for a movie.
        action: "rescan" | "rescan_unmonitor" | "none"
        Returns True if the movie was found in Radarr.
        """
        if action == "none":
            return False
        try:
            movie = await self.find_movie_by_imdb(imdb_id)
            if not movie:
                return False
            if action in ("rescan", "rescan_unmonitor"):
                await self.rescan_movie(movie["id"])
            if action == "rescan_unmonitor":
                await self.unmonitor_movie(movie["id"], dict(movie))
            return True
        except Exception as e:
            logger.warning(
                "Radarr post_replace_action({!r}) failed for imdb_id={}: {}", action, imdb_id, e
            )
        return False

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

    # ── Recommendation hand-off ──────────────────────────────────────────
    # These exist solely so a user can explicitly send a recommended movie to
    # Radarr — Slimarr never calls add_movie() on its own initiative. See
    # docs/RECOMMENDATION_INTEGRATIONS.md.

    async def get_quality_profiles(self) -> list[dict]:
        return await self._get("/qualityprofile")  # type: ignore[return-value]

    async def get_root_folders(self) -> list[dict]:
        return await self._get("/rootfolder")  # type: ignore[return-value]

    async def add_movie(
        self,
        *,
        tmdb_id: int,
        title: str,
        year: int | None,
        root_folder_path: str,
        quality_profile_id: int,
        monitored: bool = True,
        search_now: bool = False,
    ) -> dict:
        """Adds a new movie to Radarr. Requires explicit root folder + quality
        profile from the caller — Slimarr never guesses these (brief:
        'present root folder, quality profile and monitoring settings')."""
        body = {
            "tmdbId": tmdb_id,
            "title": title,
            "year": year,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "addOptions": {"searchForMovie": search_now},
        }
        return await self._post("/movie", body)
