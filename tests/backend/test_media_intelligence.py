import unittest
from unittest.mock import patch

from backend.config import SlimarrConfig
from backend.core.comparer import compare_release
from backend.core.media_health import score_release_health
from backend.core.parser import parse_release_title


class MediaIntelligenceTests(unittest.TestCase):
    def _cfg(self) -> SlimarrConfig:
        cfg = SlimarrConfig()
        cfg.comparison.minimum_file_size_mb = 300
        cfg.comparison.min_savings_percent = 10.0
        cfg.comparison.minimum_confidence_score = 35.0
        cfg.comparison.max_candidate_age_days = 3650
        cfg.comparison.require_year_match = True
        cfg.comparison.preferred_language = "english"
        cfg.comparison.avoid_dolby_vision = True
        cfg.comparison.allow_dolby_vision_with_hdr_fallback = False
        cfg.comparison.require_english_audio = True
        cfg.comparison.reject_hardcoded_subs = True
        return cfg

    def test_parser_detects_dolby_vision_hdr_fallback_and_language_risks(self) -> None:
        parsed = parse_release_title(
            "Movie.Title.2024.1080p.WEB-DL.DV.HDR10.MULTi.DUAL-AUDIO.KORSUB.x265-GRP"
        )

        self.assertTrue(parsed.has_dolby_vision)
        self.assertTrue(parsed.has_hdr_fallback)
        self.assertEqual("dolby vision + hdr10", parsed.hdr)
        self.assertTrue(parsed.is_multi_audio)
        self.assertTrue(parsed.is_dual_audio)
        self.assertTrue(parsed.has_hardcoded_subs)
        self.assertIn("multi", parsed.languages)
        self.assertIn("korsub", parsed.subtitle_markers)

    def test_dolby_vision_only_is_rejected_by_default(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=4_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_000_000_000,
                candidate_title="Movie.Title.2024.1080p.WEB-DL.DV.x265-English-GRP",
                movie_title="Movie Title",
                movie_year=2024,
            )

        self.assertEqual("reject", result.decision)
        self.assertIn("Dolby Vision", result.reject_reason or "")

    def test_dolby_vision_with_hdr_fallback_can_be_allowed(self) -> None:
        cfg = self._cfg()
        cfg.comparison.allow_dolby_vision_with_hdr_fallback = True

        with patch("backend.core.comparer.get_config", return_value=cfg):
            result = compare_release(
                local_size=4_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_000_000_000,
                candidate_title="Movie.Title.2024.1080p.WEB-DL.DV.HDR10.x265-English-GRP",
                movie_title="Movie Title",
                movie_year=2024,
                indexer_reliability=0.9,
            )

        self.assertEqual("accept", result.decision)

    def test_hardcoded_subtitles_are_rejected_by_default(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=4_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_000_000_000,
                candidate_title="Movie.Title.2024.1080p.WEB-DL.KORSUB.x265-English-GRP",
                movie_title="Movie Title",
                movie_year=2024,
            )

        self.assertEqual("reject", result.decision)
        self.assertIn("Hardcoded subtitle", result.reject_reason or "")

    def test_explicit_non_english_audio_is_rejected_when_english_required(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=4_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_000_000_000,
                candidate_title="Movie.Title.2024.1080p.WEB-DL.ITA.x265-GRP",
                movie_title="Movie Title",
                movie_year=2024,
            )

        self.assertEqual("reject", result.decision)
        self.assertIn("English audio required", result.reject_reason or "")

    def test_low_quality_candidate_sources_are_rejected(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=4_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=1_500_000_000,
                candidate_title="Movie.Title.2024.1080p.HDCAM.x265-English-GRP",
                movie_title="Movie Title",
                movie_year=2024,
            )

        self.assertEqual("reject", result.decision)
        self.assertEqual("candidate_is_low_quality", result.reject_reason)

    def test_low_quality_local_copy_can_accept_larger_quality_upgrade(self) -> None:
        with patch("backend.core.comparer.get_config", return_value=self._cfg()):
            result = compare_release(
                local_size=1_200_000_000,
                local_resolution="720p",
                local_codec="h264",
                local_bitrate=900,
                local_source_type="webrip",
                candidate_size=2_200_000_000,
                candidate_title="Movie.Title.2024.1080p.WEB-DL.x265-English-GRP",
                movie_title="Movie Title",
                movie_year=2024,
                indexer_reliability=0.9,
            )

        self.assertEqual("accept", result.decision)
        self.assertIn("existing_copy_is_low_quality", result.notes)
        self.assertIn("candidate_improves_resolution", result.notes)

    def test_media_health_marks_tiny_1080p_candidate_as_risky(self) -> None:
        health = score_release_health("Movie.Title.2024.1080p.WEB-DL.x265-English-GRP", 450 * 1_048_576)

        self.assertIn("candidate_is_suspiciously_small", health.reasons)
        self.assertIn(health.rating, {"Risky", "Reject"})


if __name__ == "__main__":
    unittest.main()
