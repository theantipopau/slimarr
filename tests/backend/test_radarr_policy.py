import unittest
from unittest.mock import AsyncMock, patch

from backend.config import SlimarrConfig
from backend.integrations.radarr import RadarrClient


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
