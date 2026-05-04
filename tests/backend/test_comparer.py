import unittest
from unittest.mock import patch

from backend.config import SlimarrConfig
from backend.core.comparer import compare_release


class CompareReleaseTests(unittest.TestCase):
    def _cfg(self) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.comparison.minimum_file_size_mb = 500
        cfg.comparison.min_savings_percent = 10.0
        cfg.comparison.minimum_confidence_score = 40.0
        cfg.comparison.max_candidate_age_days = 3650
        cfg.comparison.allow_resolution_downgrade = False
        cfg.comparison.require_year_match = True
        return cfg

    def test_rejects_when_candidate_is_larger(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=1_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_100_000_000,
                candidate_title="Movie.Title.2022.1080p.WEB-DL.x264-GRP",
                movie_title="Movie Title",
                movie_year=2022,
            )

        self.assertEqual(result.decision, "reject")
        self.assertIn("not smaller", result.reject_reason or "")

    def test_rejects_low_title_match_confidence(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_200_000_000,
                candidate_title="Completely.Different.Film.2022.1080p.WEB-DL.x265-GRP",
                movie_title="The Matrix",
                movie_year=2022,
            )

        self.assertEqual(result.decision, "reject")
        self.assertIn("Title match confidence too low", result.reject_reason or "")

    def test_accepts_valid_smaller_release_with_confidence_breakdown(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_400_000_000,
                candidate_title="The.Matrix.2022.1080p.WEB-DL.x265-English-GRP",
                candidate_age_days=30,
                movie_title="The Matrix",
                movie_year=2022,
                indexer_reliability=0.9,
            )

        self.assertEqual(result.decision, "accept")
        self.assertGreater(result.score, 0.0)
        self.assertGreater(result.confidence_score, 0.0)
        self.assertIsInstance(result.confidence_breakdown, dict)
        self.assertIn("match_certainty", result.confidence_breakdown or {})


if __name__ == "__main__":
    unittest.main()
