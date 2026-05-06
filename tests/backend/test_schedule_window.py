import unittest
from datetime import datetime

from backend.config import SlimarrConfig
from backend.core.schedule_window import is_within_schedule_window


class ScheduleWindowTests(unittest.TestCase):
    def _cfg(self) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.schedule.timezone = "UTC"
        cfg.schedule.start_time = "23:00"
        cfg.schedule.end_time = "05:00"
        cfg.schedule.days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        return cfg

    def test_allows_time_inside_overnight_window(self) -> None:
        cfg = self._cfg()
        now = datetime(2026, 5, 6, 23, 30)
        self.assertTrue(is_within_schedule_window(cfg, now=now))

    def test_allows_time_after_midnight_in_same_window(self) -> None:
        cfg = self._cfg()
        now = datetime(2026, 5, 7, 4, 15)
        self.assertTrue(is_within_schedule_window(cfg, now=now))

    def test_rejects_time_outside_window(self) -> None:
        cfg = self._cfg()
        now = datetime(2026, 5, 7, 9, 0)
        self.assertFalse(is_within_schedule_window(cfg, now=now))


if __name__ == "__main__":
    unittest.main()
