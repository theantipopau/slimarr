import unittest
from unittest.mock import patch

import httpx

from backend.integrations.radarr import RadarrClient
from backend.integrations.sonarr import SonarrClient


class RadarrConfig:
    def __init__(self):
        self.url = "http://radarr.local:7878"
        self.api_key = "radarr-key"
        self.tls_verify = True


class SonarrConfig:
    def __init__(self):
        self.url = "http://sonarr.local:8989"
        self.api_key = "sonarr-key"
        self.tls_verify = True


class RadarrHandoffTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.radarr.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.radarr = RadarrConfig()
        self.client = RadarrClient()

    async def test_add_movie_sends_the_expected_body(self):
        captured = {}

        async def fake_post(self_client, url, json=None, headers=None):
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(201, json={"id": 42, "title": "Toy Story 2"}, request=httpx.Request("POST", url))

        with patch.object(httpx.AsyncClient, "post", fake_post):
            result = await self.client.add_movie(
                tmdb_id=863, title="Toy Story 2", year=1999,
                root_folder_path="/movies", quality_profile_id=4,
                monitored=True, search_now=True,
            )

        self.assertEqual(result["id"], 42)
        self.assertEqual(captured["json"]["tmdbId"], 863)
        self.assertEqual(captured["json"]["qualityProfileId"], 4)
        self.assertEqual(captured["json"]["rootFolderPath"], "/movies")
        self.assertTrue(captured["json"]["monitored"])
        self.assertTrue(captured["json"]["addOptions"]["searchForMovie"])
        self.assertEqual(captured["headers"]["X-Api-Key"], "radarr-key")

    async def test_get_quality_profiles_and_root_folders(self):
        async def fake_get(self_client, url, params=None, headers=None):
            if "qualityprofile" in url:
                return httpx.Response(200, json=[{"id": 4, "name": "HD-1080p"}], request=httpx.Request("GET", url))
            return httpx.Response(200, json=[{"id": 1, "path": "/movies"}], request=httpx.Request("GET", url))

        with patch.object(httpx.AsyncClient, "get", fake_get):
            profiles = await self.client.get_quality_profiles()
            folders = await self.client.get_root_folders()

        self.assertEqual(profiles[0]["name"], "HD-1080p")
        self.assertEqual(folders[0]["path"], "/movies")


class SonarrHandoffTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("backend.integrations.sonarr.get_config")
        mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_get_config.return_value.sonarr = SonarrConfig()
        self.client = SonarrClient()

    async def test_add_series_sends_the_expected_body(self):
        captured = {}

        async def fake_post(self_client, url, json=None, headers=None):
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(201, json={"id": 7}, request=httpx.Request("POST", url))

        with patch.object(httpx.AsyncClient, "post", fake_post):
            result = await self.client.add_series(
                tvdb_id=100, title="Some Show", root_folder_path="/tv",
                quality_profile_id=1, monitored=False, search_now=False,
            )

        self.assertEqual(result["id"], 7)
        self.assertEqual(captured["json"]["tvdbId"], 100)
        self.assertFalse(captured["json"]["monitored"])
        self.assertFalse(captured["json"]["addOptions"]["searchForMissingEpisodes"])
        self.assertEqual(captured["headers"]["X-Api-Key"], "sonarr-key")


if __name__ == "__main__":
    unittest.main()
