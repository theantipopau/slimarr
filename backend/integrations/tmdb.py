"""TMDB API client."""
from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from loguru import logger

from backend.config import get_config
from backend.integrations.shared_http import get_shared_client


class TMDBError(RuntimeError):
    """Typed error for TMDB request failures, distinct from a bare Exception
    so callers (the recommendation engine) can decide whether a failure
    should abort a whole refresh job or just skip one candidate."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def _shared_client() -> httpx.AsyncClient | None:
    """Thin per-module wrapper around the shared reuse-or-private decision
    (backend.integrations.shared_http) - kept as a real function here (not
    just an alias) so existing tests can still patch it per-module. TMDB has
    no user-configurable TLS setting, so unlike Radarr/Sonarr there's no
    correctness reason to ever prefer a private client here - see
    docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md finding A5."""
    return get_shared_client()


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

    @asynccontextmanager
    async def _client(self, timeout: float = 15.0):
        client = _shared_client()
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=timeout)
        try:
            yield client
        finally:
            if owns_client:
                await client.aclose()

    async def search_movie(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        params = self._params({"query": title})
        if year:
            params["year"] = year
        async with self._client() as client:
            resp = await client.get(f"{TMDB_BASE}/search/movie", params=params, timeout=15.0)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0] if results else None

    async def get_movie(self, tmdb_id: int) -> dict:
        async with self._client() as client:
            resp = await client.get(f"{TMDB_BASE}/movie/{tmdb_id}", params=self._params(), timeout=15.0)
            resp.raise_for_status()
            return resp.json()

    async def find_by_imdb(self, imdb_id: str) -> Optional[dict]:
        params = {"api_key": self.api_key, "external_source": "imdb_id"}
        async with self._client() as client:
            resp = await client.get(f"{TMDB_BASE}/find/{imdb_id}", params=params, timeout=15.0)
            resp.raise_for_status()
            results = resp.json().get("movie_results", [])
            return results[0] if results else None

    async def download_image(self, path: str, size: str = "w300") -> bytes:
        url = f"{TMDB_IMAGE_BASE}/{size}{path}"
        async with self._client(timeout=20.0) as client:
            resp = await client.get(url, timeout=20.0)
            resp.raise_for_status()
            return resp.content

    async def test_connection(self) -> dict:
        try:
            result = await self.search_movie("The Matrix", 1999)
            return {"success": True, "test_title": result.get("title") if result else "no results"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Recommendation-engine methods ────────────────────────────────────
    # These use the shared pooled client (see _shared_client above) and a
    # small retry-with-jitter policy for transient failures (429/5xx) — the
    # recommendation engine calls these once per candidate per refresh, an
    # order of magnitude more traffic than the per-movie-scan enrichment
    # methods above, so both pooling and backoff actually matter here.

    async def _get_with_retry(
        self, path: str, params: dict, *, attempts: int = 3, timeout: float = 15.0
    ) -> dict:
        async with self._client(timeout=timeout) as client:
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    resp = await client.get(f"{TMDB_BASE}{path}", params=params, timeout=timeout)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        delay = self._retry_delay(resp.headers.get("Retry-After"), attempt)
                        if attempt < attempts:
                            logger.debug(
                                "TMDB {} returned {}; retrying in {:.1f}s (attempt {}/{})",
                                path, resp.status_code, delay, attempt, attempts,
                            )
                            await asyncio.sleep(delay)
                            continue
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    # 4xx other than 429 is a permanent failure (bad ID, bad key) —
                    # never retry those, only transient 429/5xx handled above.
                    if status is not None and status < 500 and status != 429:
                        raise TMDBError(f"TMDB request failed: HTTP {status}", status_code=status) from exc
                    last_error = exc
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_error = exc
                    if attempt < attempts:
                        delay = min(2.0 ** attempt, 10.0) + random.uniform(0, 0.5)
                        await asyncio.sleep(delay)
            raise TMDBError(f"TMDB request failed after {attempts} attempts: {last_error}") from last_error

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        """Retry-After is usually delay-seconds, but RFC 7231 also allows an
        HTTP-date string - float() on that raises ValueError, which must
        never escape as a bare exception here (defeats the whole point of
        TMDBError's narrow, callers-can-catch-it contract). Falls back to
        exponential backoff for anything that isn't a plain number."""
        if retry_after:
            try:
                return float(retry_after) + random.uniform(0, 0.5)
            except ValueError:
                pass
        return min(2.0 ** attempt, 10.0) + random.uniform(0, 0.5)

    async def get_movie_full(self, tmdb_id: int) -> dict:
        """Movie details plus collection/credits/recommendations/similar in
        one call via TMDB's append_to_response — avoids four separate
        round-trips per candidate."""
        return await self._get_with_retry(
            f"/movie/{tmdb_id}",
            self._params({"append_to_response": "belongs_to_collection,credits,recommendations,similar"}),
        )

    async def get_collection(self, collection_id: int) -> dict:
        return await self._get_with_retry(f"/collection/{collection_id}", self._params())

    async def get_external_ids(self, tmdb_id: int, media_type: str = "movie") -> dict:
        """IMDb/TVDB IDs for a title TMDB returned from a collection/
        recommendations/similar listing (those payloads don't include external
        IDs) — needed to correlate a sourced candidate against Radarr/Sonarr,
        which key on IMDb ID rather than TMDB ID."""
        media_type = "tv" if media_type == "tv" else "movie"
        return await self._get_with_retry(f"/{media_type}/{tmdb_id}/external_ids", self._params())

    async def get_genre_map(self, media_type: str = "movie") -> dict[int, str]:
        """TMDB genre id -> name, for resolving the genre_ids TMDB embeds in
        collection/recommendations/similar list items (those payloads never
        include genre names directly). This list is small (~19 entries) and
        essentially static, so callers fetch it once per refresh run rather
        than per candidate."""
        media_type = "tv" if media_type == "tv" else "movie"
        data = await self._get_with_retry(f"/genre/{media_type}/list", self._params())
        return {g["id"]: g["name"] for g in data.get("genres", []) if g.get("id") is not None}

    async def get_watch_providers(self, tmdb_id: int, media_type: str = "movie") -> dict:
        """Returns TMDB's region-keyed watch/providers payload. Callers pick
        the region key themselves — this method makes no assumption about
        which region the caller wants (see docs/RECOMMENDATION_ARCHITECTURE.md:
        streaming availability requires an explicit configured region, never
        a silently-assumed default)."""
        media_type = "tv" if media_type == "tv" else "movie"
        return await self._get_with_retry(
            f"/{media_type}/{tmdb_id}/watch/providers",
            {"api_key": self.api_key},
        )
