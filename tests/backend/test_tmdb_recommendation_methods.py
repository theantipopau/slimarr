import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.integrations.tmdb import TMDBClient, TMDBError


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TMDBClientConfig:
    def __init__(self):
        self.api_key = "test-key"
        self.language = "en-US"


class TMDBRecommendationMethodsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.tmdb.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.tmdb = TMDBClientConfig()
        self.client = TMDBClient()

    async def test_get_movie_full_requests_append_to_response(self):
        captured_requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json={"id": 862, "title": "Toy Story"})

        with patch(
            "backend.integrations.tmdb._shared_client",
            return_value=_client_with_handler(handler),
        ):
            result = await self.client.get_movie_full(862)

        self.assertEqual(result["title"], "Toy Story")
        self.assertEqual(len(captured_requests), 1)
        query = captured_requests[0].url.params
        self.assertEqual(
            query["append_to_response"], "belongs_to_collection,credits,recommendations,similar"
        )
        self.assertIn("/movie/862", str(captured_requests[0].url))

    async def test_get_collection_returns_parsed_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": 10194, "name": "Toy Story Collection", "parts": []})

        with patch("backend.integrations.tmdb._shared_client", return_value=_client_with_handler(handler)):
            result = await self.client.get_collection(10194)

        self.assertEqual(result["name"], "Toy Story Collection")

    async def test_get_watch_providers_uses_tv_path_for_tv_media_type(self):
        captured_requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json={"results": {}})

        with patch("backend.integrations.tmdb._shared_client", return_value=_client_with_handler(handler)):
            await self.client.get_watch_providers(1399, media_type="tv")

        self.assertIn("/tv/1399/watch/providers", str(captured_requests[0].url))

    async def test_permanent_4xx_is_not_retried(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404, json={"status_message": "not found"})

        with patch("backend.integrations.tmdb._shared_client", return_value=_client_with_handler(handler)):
            with self.assertRaises(TMDBError) as ctx:
                await self.client.get_movie_full(999999)

        self.assertEqual(call_count, 1)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_transient_429_is_retried_and_eventually_succeeds(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"id": 862})

        with patch("backend.integrations.tmdb._shared_client", return_value=_client_with_handler(handler)), patch(
            "backend.integrations.tmdb.asyncio.sleep", AsyncMock()
        ):
            result = await self.client.get_movie_full(862)

        self.assertEqual(call_count, 3)
        self.assertEqual(result["id"], 862)

    async def test_transient_5xx_exhausting_all_attempts_raises_typed_error(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(503)

        with patch("backend.integrations.tmdb._shared_client", return_value=_client_with_handler(handler)), patch(
            "backend.integrations.tmdb.asyncio.sleep", AsyncMock()
        ):
            with self.assertRaises(TMDBError):
                await self.client.get_movie_full(862)

        self.assertEqual(call_count, 3)  # default attempts=3, all exhausted

    async def test_falls_back_to_a_private_client_when_shared_client_unavailable(self):
        """_shared_client() returns None outside the FastAPI lifespan (tests,
        scripts) — the method must still work, just without pooling."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": 862})

        with patch("backend.integrations.tmdb._shared_client", return_value=None), patch(
            "httpx.AsyncClient", return_value=_client_with_handler(handler)
        ):
            result = await self.client.get_movie_full(862)

        self.assertEqual(result["id"], 862)


if __name__ == "__main__":
    unittest.main()
