import unittest
from unittest.mock import AsyncMock, patch

from backend.config import SlimarrConfig
from backend.integrations.radarr import RadarrClient, _shared_client


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


class RadarrPolicyTests(unittest.IsolatedAsyncioTestCase):
    def _cfg(self) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.radarr.enabled = True
        cfg.radarr.url = "http://radarr.local"
        cfg.radarr.api_key = "key"
        cfg.radarr.tls_verify = True
        return cfg

    async def test_action_none_does_not_call_radarr(self) -> None:
        with patch("backend.integrations.radarr.get_config", return_value=self._cfg()):
            client = RadarrClient()
            client.find_movie_by_imdb = AsyncMock()
            client.rescan_movie = AsyncMock()
            client.unmonitor_movie = AsyncMock()

            found = await client.post_replace_action("tt0133093", "none")

        self.assertFalse(found)
        client.find_movie_by_imdb.assert_not_called()
        client.rescan_movie.assert_not_called()
        client.unmonitor_movie.assert_not_called()

    async def test_rescan_unmonitor_calls_both_actions(self) -> None:
        with patch("backend.integrations.radarr.get_config", return_value=self._cfg()):
            client = RadarrClient()
            client.find_movie_by_imdb = AsyncMock(return_value={"id": 101, "title": "The Matrix"})
            client.rescan_movie = AsyncMock()
            client.unmonitor_movie = AsyncMock()

            found = await client.post_replace_action("tt0133093", "rescan_unmonitor")

        self.assertTrue(found)
        client.find_movie_by_imdb.assert_awaited_once_with("tt0133093")
        client.rescan_movie.assert_awaited_once_with(101)
        client.unmonitor_movie.assert_awaited_once()

    async def test_rescan_calls_only_rescan(self) -> None:
        with patch("backend.integrations.radarr.get_config", return_value=self._cfg()):
            client = RadarrClient()
            client.find_movie_by_imdb = AsyncMock(return_value={"id": 202, "title": "Interstellar"})
            client.rescan_movie = AsyncMock()
            client.unmonitor_movie = AsyncMock()

            found = await client.post_replace_action("tt0816692", "rescan")

        self.assertTrue(found)
        client.rescan_movie.assert_awaited_once_with(202)
        client.unmonitor_movie.assert_not_called()


if __name__ == "__main__":
    unittest.main()
