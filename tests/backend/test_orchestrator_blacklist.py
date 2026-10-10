import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core import orchestrator


def _result(title: str, score: float) -> dict:
    return {"id": hash(title) % 1000, "release_title": title, "decision": "accept", "score": score, "indexer_name": "idx"}


class BlacklistedReleaseSkippedTests(unittest.TestCase):
    def _run(self, results, blacklisted_titles):
        session = MagicMock()
        session.get = AsyncMock(return_value=SimpleNamespace(
            preferred_release_title=None, force_keep=False, slimarr_locked=False, quality_intent="space_saver",
        ))
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        def fake_reasons(keys):
            return {i: "retry_failed_release" for i, (title, _, _) in enumerate(keys) if title in blacklisted_titles}

        process = AsyncMock(return_value={"status": "queued"})
        with patch.object(orchestrator, "async_session", return_value=session_cm), \
             patch.object(orchestrator, "search_for_movie", AsyncMock(return_value=results)), \
             patch.object(orchestrator, "get_blacklist_reasons", AsyncMock(side_effect=fake_reasons)), \
             patch.object(orchestrator, "process_search_result_download", process), \
             patch("backend.config.get_config", return_value=SimpleNamespace(
                 automation=SimpleNamespace(dry_run=False, review_required=False), exclusions=None)), \
             patch.object(orchestrator, "is_movie_excluded", return_value=(False, None)):
            summary = asyncio.run(orchestrator.process_single_movie(1))
        return summary, process

    def test_top_scored_blacklisted_release_is_not_grabbed_again(self):
        results = [
            _result("Movie.2025.MULTi.VFF.2160p-GRP", 90.0),   # best score, but failed before
            _result("Movie.2025.1080p.WEB-DL-GRP", 70.0),
        ]
        summary, process = self._run(results, {"Movie.2025.MULTi.VFF.2160p-GRP"})
        self.assertEqual("queued", summary["status"])
        chosen_id = process.await_args.args[0]
        self.assertEqual(results[1]["id"], chosen_id)

    def test_no_candidates_left_when_all_are_blacklisted(self):
        results = [_result("Only.2025.1080p-GRP", 80.0)]
        summary, process = self._run(results, {"Only.2025.1080p-GRP"})
        self.assertEqual("no_candidates", summary["status"])
        process.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
