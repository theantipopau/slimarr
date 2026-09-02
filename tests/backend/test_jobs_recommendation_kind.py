import unittest
from unittest.mock import AsyncMock, patch

from backend.core.jobs import _execute_job_kind


class RecommendationRefreshJobKindTests(unittest.IsolatedAsyncioTestCase):
    async def test_recommendation_refresh_kind_dispatches_to_the_engine(self):
        mock_refresh = AsyncMock(return_value={"status": "ok", "created": 3})
        with patch(
            "backend.core.recommendations.engine.run_recommendation_refresh", mock_refresh
        ):
            result = await _execute_job_kind("recommendation_refresh", {})

        mock_refresh.assert_awaited_once_with(max_movies=200)
        self.assertEqual(result, {"status": "ok", "created": 3})

    async def test_recommendation_refresh_kind_passes_through_max_movies_payload(self):
        mock_refresh = AsyncMock(return_value={"status": "ok"})
        with patch(
            "backend.core.recommendations.engine.run_recommendation_refresh", mock_refresh
        ):
            await _execute_job_kind("recommendation_refresh", {"max_movies": 50})

        mock_refresh.assert_awaited_once_with(max_movies=50)

    async def test_unsupported_kind_raises_value_error(self):
        with self.assertRaises(ValueError):
            await _execute_job_kind("not_a_real_kind", {})


if __name__ == "__main__":
    unittest.main()
