import unittest
from types import SimpleNamespace

from backend.scheduler.scheduler import _time_after_window_end


class TimeAfterWindowEndTests(unittest.TestCase):
    def _config(self, end_time: str) -> SimpleNamespace:
        return SimpleNamespace(schedule=SimpleNamespace(end_time=end_time))

    def test_offset_after_default_window_end(self):
        # Default nightly window is 01:00 -> 07:00; recycle_cleanup and
        # orphan_scanner used to be hardcoded to 03:00/04:00, landing in the
        # middle of it for virtually every installation.
        self.assertEqual((7, 15), _time_after_window_end(self._config("07:00"), offset_minutes=15))
        self.assertEqual((7, 30), _time_after_window_end(self._config("07:00"), offset_minutes=30))

    def test_offset_wraps_past_midnight(self):
        self.assertEqual((0, 10), _time_after_window_end(self._config("23:55"), offset_minutes=15))

    def test_offset_wraps_past_hour_boundary(self):
        self.assertEqual((5, 5), _time_after_window_end(self._config("04:50"), offset_minutes=15))

    def test_falls_back_to_default_end_time_on_malformed_input(self):
        self.assertEqual((7, 15), _time_after_window_end(self._config("not-a-time"), offset_minutes=15))


if __name__ == "__main__":
    unittest.main()
