import unittest
from unittest.mock import patch

import httpx

from backend.integrations.sonarr import SonarrClient, _shared_client


class SharedClientSelectionTests(unittest.TestCase):
    def test_tls_verify_false_never_uses_the_shared_client(self):
        # The shared client is always built with verify=True - reusing it for
        # an instance configured with tls_verify=False would silently ignore
        # that setting (e.g. a self-signed cert on a homelab NAS setup).
        self.assertIsNone(_shared_client(False))

    def test_tls_verify_true_falls_back_gracefully_outside_the_app_lifespan(self):
        # get_http_client() raises RuntimeError until FastAPI's lifespan has
        # started it (as in this unit test) - must degrade to None, not raise.
        self.assertIsNone(_shared_client(True))


class SonarrConfig:
    def __init__(self):
        self.url = "http://sonarr.local:8989"
        self.api_key = "sonarr-key"
        self.tls_verify = True


class SonarrClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.sonarr.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.sonarr = SonarrConfig()
        self.client = SonarrClient()

    async def test_get_all_series_returns_parsed_json(self):
        async def fake_get(self_client, url, headers=None, params=None):
            return httpx.Response(200, json=[{"id": 1, "title": "Some Show"}], request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            series = await self.client.get_all_series()

        self.assertEqual(series[0]["title"], "Some Show")

    async def test_unmonitor_series_by_title_exact_match_updates_series_and_seasons(self):
        captured = {}

        async def fake_get(self_client, url, headers=None, params=None):
            return httpx.Response(
                200,
                json=[{"id": 5, "title": "Some Show", "seasons": [{"seasonNumber": 1, "monitored": True}]}],
                request=httpx.Request("GET", url),
            )

        async def fake_put(self_client, url, json=None, headers=None):
            captured["json"] = json
            return httpx.Response(200, json=json, request=httpx.Request("PUT", url))

        with (
            patch.object(httpx.AsyncClient, "get", fake_get),
            patch.object(httpx.AsyncClient, "put", fake_put),
        ):
            found = await self.client.unmonitor_series_by_title("Some Show")

        self.assertTrue(found)
        self.assertFalse(captured["json"]["monitored"])
        self.assertFalse(captured["json"]["seasons"][0]["monitored"])

    async def test_unmonitor_series_by_title_no_match_returns_false(self):
        async def fake_get(self_client, url, headers=None, params=None):
            return httpx.Response(200, json=[{"id": 5, "title": "Other Show"}], request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            found = await self.client.unmonitor_series_by_title("Nonexistent Show")

        self.assertFalse(found)

    async def test_test_connection_reports_version(self):
        async def fake_get(self_client, url, headers=None, params=None):
            return httpx.Response(
                200, json={"version": "4.0.0", "appName": "Sonarr"}, request=httpx.Request("GET", url)
            )

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.test_connection()

        self.assertTrue(result["success"])
        self.assertEqual(result["version"], "4.0.0")

    async def test_test_connection_reports_failure_without_raising(self):
        async def fake_get(self_client, url, headers=None, params=None):
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await self.client.test_connection()

        self.assertFalse(result["success"])
        self.assertIn("connection refused", result["error"])


if __name__ == "__main__":
    unittest.main()
