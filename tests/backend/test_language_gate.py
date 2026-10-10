import unittest
from unittest.mock import patch

from backend.config import SlimarrConfig
from backend.core.comparer import compare_release
from backend.core.parser import parse_release_title


class LanguageGateTests(unittest.TestCase):
    def _compare(self, title: str):
        cfg = SlimarrConfig()
        with patch("backend.core.comparer.get_config", return_value=cfg):
            return compare_release(
                local_size=8_000_000_000,
                local_resolution="1080p",
                local_codec="h264",
                candidate_size=2_000_000_000,
                candidate_title=title,
                movie_title="The Running Man",
                movie_year=2025,
            )

    def test_french_version_tags_are_detected(self) -> None:
        for title in ("The.Running.Man.2025.MULTi.VFF.2160p", "Dark.Matter.S02E10.MULTi.VFi.1080p", "The.Rip.2026.MULTi.VF2.AD.2160p"):
            self.assertIn("french", parse_release_title(title).languages, title)

    def test_multi_release_with_french_dub_and_no_english_is_rejected(self) -> None:
        result = self._compare("The.Running.Man.2025.MULTi.VFF.2160p.BluRay.x265-GRP")
        self.assertEqual("reject", result.decision)
        self.assertIn("English audio required", result.reject_reason or "")

    def test_multi_release_with_english_track_is_not_blocked_by_language(self) -> None:
        result = self._compare("The.Running.Man.2025.MULTi.VFF.ENG.2160p.BluRay.x265-GRP")
        self.assertNotIn("English audio required", result.reject_reason or "")

    def test_ambiguous_multi_release_is_not_blocked_by_language(self) -> None:
        result = self._compare("The.Running.Man.2025.MULTi.2160p.BluRay.x265-GRP")
        self.assertNotIn("English audio required", result.reject_reason or "")


if __name__ == "__main__":
    unittest.main()
