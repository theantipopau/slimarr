import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.core.recommendations import engine


class AvailabilityRefreshGateTests(unittest.TestCase):
    def test_nothing_happens_when_recommendations_are_disabled(self):
        cfg = SimpleNamespace(recommendations=SimpleNamespace(enabled=False, region="AU"))
        with patch("backend.config.get_config", return_value=cfg), \
             patch.object(engine, "async_session", side_effect=AssertionError("must not query the database")):
            self.assertEqual(0, asyncio.run(engine.refresh_stale_availability()))

    def test_nothing_happens_without_a_region(self):
        cfg = SimpleNamespace(recommendations=SimpleNamespace(enabled=True, region=""))
        with patch("backend.config.get_config", return_value=cfg), \
             patch.object(engine, "async_session", side_effect=AssertionError("must not query the database")):
            self.assertEqual(0, asyncio.run(engine.refresh_stale_availability()))


if __name__ == "__main__":
    unittest.main()
