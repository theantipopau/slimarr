"""Radarr API v3 client (optional integration)."""
from __future__ import annotations

import httpx

from backend.config import get_config


class RadarrClient:
    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        config = get_config()
        self.url = (url or config.radarr.url).rstrip("/")
        self.api_key = api_key or config.radarr.api_key
        self.tls_verify = config.radarr.tls_verify

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key}

    def _http(self) -> httpx.AsyncClient:
        """Return an httpx client. TLS verification is configurable via radarr.tls_verify."""
        return httpx.AsyncClient(timeout=15.0, verify=self.tls_verify)

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        async with self._http() as client:
            resp = await client.get(
                f"{self.url}/api/v3{endpoint}",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, endpoint: str, body: dict) -> dict:
        async with self._http() as client:
            resp = await client.post(
                f"{self.url}/api/v3{endpoint}",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

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
        async with self._http() as client:
            resp = await client.put(
                f"{self.url}/api/v3/movie/{radarr_id}",
                json=movie_payload,
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def rescan_by_imdb(self, imdb_id: str) -> bool:
        """Find movie in Radarr by IMDb ID and trigger a rescan. Returns True if found."""
        try:
            movie = await self.find_movie_by_imdb(imdb_id)
            if movie:
                await self.rescan_movie(movie["id"])
                return True
        except Exception:
            pass
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
        except Exception:
            pass
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
