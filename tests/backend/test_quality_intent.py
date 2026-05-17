import unittest
from unittest.mock import patch

from backend.config import SlimarrConfig
from backend.core.comparer import compare_release


class QualityIntentCompareTests(unittest.TestCase):
    def _cfg(self) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.comparison.minimum_file_size_mb = 500
        cfg.comparison.min_savings_percent = 10.0
        cfg.comparison.minimum_confidence_score = 35.0
        cfg.comparison.max_candidate_age_days = 3650
        cfg.comparison.allow_resolution_downgrade = False
        cfg.comparison.require_year_match = True
        return cfg

    def test_locked_intent_rejects_all_replacements(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_100_000_000,
                candidate_title="Movie.Title.2022.1080p.WEB-DL.x265-GRP",
                movie_title="Movie Title",
                movie_year=2022,
                quality_intent="locked",
            )

        self.assertEqual(result.decision, "reject")
        self.assertIn("force-kept", result.reject_reason or "")

    def test_balanced_can_allow_modest_size_increase(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_120_000_000,
                candidate_title="Movie.Title.2022.1080p.WEB-DL.x265-GRP",
                movie_title="Movie Title",
                movie_year=2022,
                local_source_type="webrip",
                quality_intent="balanced",
                allow_larger_replacements=True,
            )

        self.assertEqual(result.decision, "accept")

    def test_resolution_floor_override_is_enforced(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_300_000_000,
                candidate_title="Movie.Title.2022.720p.WEB-DL.x265-GRP",
                movie_title="Movie Title",
                movie_year=2022,
                quality_intent="premium",
                allow_larger_replacements=True,
                quality_profile_overrides={"resolution_floor": "1080p"},
            )

        self.assertEqual(result.decision, "reject")
        self.assertTrue(
            (
                "resolution floor" in (result.reject_reason or "").lower()
                or "resolution downgrade" in (result.reject_reason or "").lower()
            )
        )

    def test_rejected_policy_decisions_include_quality_intent_note(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_100_000_000,
                candidate_title="Movie.Title.2022.1080p.WEB-DL.x265-GRP",
                movie_title="Movie Title",
                movie_year=2022,
                force_keep=True,
            )

        self.assertEqual(result.decision, "reject")
        self.assertIn("quality_intent=space_saver", result.notes)

    def test_bad_numeric_override_falls_back_to_policy_default(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=2_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_120_000_000,
                candidate_title="Movie.Title.2022.1080p.WEB-DL.x265-GRP",
                movie_title="Movie Title",
                movie_year=2022,
                local_source_type="webrip",
                quality_intent="balanced",
                allow_larger_replacements=True,
                quality_profile_overrides={"max_size_increase_pct": "not-a-number"},
            )

        self.assertEqual(result.decision, "accept")


if __name__ == "__main__":
    unittest.main()
