import unittest
from unittest.mock import patch

import httpx

from backend.integrations.tmdb import TMDBClient


class TMDBConfig:
    def __init__(self):
        self.api_key = "tmdb-key"
        self.language = "en-US"


class TMDBClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.tmdb.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.tmdb = TMDBConfig()
        self.client = TMDBClient()

    async def test_search_movie_returns_first_result(self):
        async def fake_get(self_client, url, params=None, timeout=None):
            return httpx.Response(
                200, json={"results": [{"id": 1, "title": "The Matrix"}]}, request=httpx.Request("GET", url)
            )

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.search_movie("The Matrix", 1999)

        self.assertEqual(result["title"], "The Matrix")

    async def test_search_movie_returns_none_when_no_results(self):
        async def fake_get(self_client, url, params=None, timeout=None):
            return httpx.Response(200, json={"results": []}, request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.search_movie("Nonexistent Movie")

        self.assertIsNone(result)

    async def test_get_movie_returns_parsed_json(self):
        async def fake_get(self_client, url, params=None, timeout=None):
            return httpx.Response(200, json={"id": 603, "title": "The Matrix"}, request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.get_movie(603)

        self.assertEqual(result["id"], 603)

    async def test_find_by_imdb_returns_first_movie_result(self):
        async def fake_get(self_client, url, params=None, timeout=None):
            return httpx.Response(
                200, json={"movie_results": [{"id": 603}]}, request=httpx.Request("GET", url)
            )

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.find_by_imdb("tt0133093")

        self.assertEqual(result["id"], 603)

    async def test_download_image_returns_raw_bytes(self):
        async def fake_get(self_client, url, timeout=None):
            return httpx.Response(200, content=b"fake-jpeg-bytes", request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            content = await self.client.download_image("/poster.jpg")

        self.assertEqual(content, b"fake-jpeg-bytes")

    async def test_test_connection_reports_failure_without_raising(self):
        async def fake_get(self_client, url, params=None, timeout=None):
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.test_connection()

        self.assertFalse(result["success"])
        self.assertIn("connection refused", result["error"])


if __name__ == "__main__":
    unittest.main()
