import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.config import SlimarrConfig
from backend.core.replacer import _run_radarr_post_replace


class ReplacerRadarrBridgeTests(unittest.IsolatedAsyncioTestCase):
    def _cfg(self, action: str) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.radarr.enabled = True
        cfg.radarr.url = "http://radarr.local"
        cfg.radarr.api_key = "key"
        cfg.radarr.post_replace_action = action
        return cfg

    async def test_bridge_skips_when_action_none(self) -> None:
        movie = SimpleNamespace(title="The Matrix", imdb_id="tt0133093")
        config = self._cfg("none")

        with patch("backend.integrations.radarr.RadarrClient") as radarr_cls:
            await _run_radarr_post_replace(movie, config)

        radarr_cls.assert_not_called()

    async def test_bridge_dispatches_action_when_enabled(self) -> None:
        movie = SimpleNamespace(title="The Matrix", imdb_id="tt0133093")
        config = self._cfg("rescan_unmonitor")
        radarr_instance = AsyncMock()
        radarr_instance.post_replace_action = AsyncMock(return_value=True)

        with patch("backend.integrations.radarr.RadarrClient", return_value=radarr_instance):
            await _run_radarr_post_replace(movie, config)

        radarr_instance.post_replace_action.assert_awaited_once_with("tt0133093", "rescan_unmonitor")


if __name__ == "__main__":
    unittest.main()
