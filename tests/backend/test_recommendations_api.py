import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import recommendations as api
from backend.database import (
    Base,
    Recommendation,
    RecommendationCandidate,
    RecommendationFeedback,
    RecommendationReason,
)


class RecommendationsAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        for target in (
            "backend.api.recommendations.async_session",
            "backend.core.recommendations.engine.async_session",
        ):
            patcher = patch(target, self.maker)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _seed(self, *, state="active", score=50.0, media_type="movie", tmdb_id=1, category="collection_completion", imdb_id=None) -> int:
        async with self.maker() as db:
            candidate = RecommendationCandidate(
                media_type=media_type, tmdb_id=tmdb_id, title="Some Movie", year=2000, imdb_id=imdb_id,
            )
            db.add(candidate)
            await db.flush()
            rec = Recommendation(candidate_id=candidate.id, category=category, score=score, state=state)
            db.add(rec)
            await db.flush()
            db.add(RecommendationReason(recommendation_id=rec.id, reason_code="missing_collection_member", explanation="x"))
            await db.commit()
            return rec.id

    async def test_list_defaults_to_active_state_only(self):
        await self._seed(state="active")
        await self._seed(state="dismissed", tmdb_id=2)

        result = await api.list_recommendations(user="tester")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["recommendations"][0]["state"], "active")

    async def test_list_with_empty_state_filter_returns_everything(self):
        await self._seed(state="active")
        await self._seed(state="dismissed", tmdb_id=2)

        result = await api.list_recommendations(user="tester", state="")
        self.assertEqual(result["total"], 2)

    async def test_list_includes_reasons_in_the_serialized_output(self):
        await self._seed()
        result = await api.list_recommendations(user="tester")
        self.assertEqual(result["recommendations"][0]["reasons"][0]["reason_code"], "missing_collection_member")

    async def test_dismiss_sets_state_and_records_feedback(self):
        rec_id = await self._seed()
        result = await api.dismiss_recommendation(rec_id, user="tester")
        self.assertEqual(result["state"], "dismissed")

        async with self.maker() as db:
            from sqlalchemy import select
            events = (await db.execute(select(RecommendationFeedback))).scalars().all()
        self.assertEqual(events[0].action, "dismissed")

    async def test_dismissing_an_unknown_recommendation_raises_not_found(self):
        from backend.utils.responses import APIException

        with self.assertRaises(APIException) as ctx:
            await api.dismiss_recommendation(999999, user="tester")
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_watchlist_and_mark_owned_transitions(self):
        rec_id = await self._seed()
        result = await api.watchlist_recommendation(rec_id, user="tester")
        self.assertEqual(result["state"], "watchlisted")

        rec_id2 = await self._seed(tmdb_id=5)
        result2 = await api.mark_owned_recommendation(rec_id2, user="tester")
        self.assertEqual(result2["state"], "already_available")

    async def test_capabilities_reports_seerr_as_unavailable_by_design(self):
        cfg = SimpleNamespace(
            radarr=SimpleNamespace(enabled=True, url="http://radarr", api_key="key"),
            sonarr=SimpleNamespace(enabled=False, url="", api_key=""),
        )
        with patch("backend.config.get_config", return_value=cfg):
            result = await api.get_capabilities(user="tester")

        self.assertTrue(result["radarr"]["available"])
        self.assertFalse(result["sonarr"]["available"])
        self.assertFalse(result["seerr"]["available"])
        self.assertIsNotNone(result["seerr"]["reason"])

    async def test_send_to_radarr_requires_radarr_configured(self):
        from backend.api.models import SendToRadarrRequest
        from backend.utils.responses import APIException

        rec_id = await self._seed()
        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=False, url="", api_key=""))
        with patch("backend.config.get_config", return_value=cfg):
            with self.assertRaises(APIException) as ctx:
                await api.send_to_radarr(
                    rec_id,
                    SendToRadarrRequest(root_folder_path="/movies", quality_profile_id=1),
                    user="tester",
                )
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_send_to_radarr_rejects_already_managed_titles(self):
        from backend.api.models import SendToRadarrRequest
        from backend.utils.responses import APIException

        rec_id = await self._seed(imdb_id="tt0114709")
        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=True, url="http://radarr", api_key="key", tls_verify=True))
        with patch("backend.config.get_config", return_value=cfg), patch(
            "backend.integrations.radarr.RadarrClient.find_movie_by_imdb",
            AsyncMock(return_value={"id": 1, "title": "Some Movie"}),
        ):
            with self.assertRaises(APIException) as ctx:
                await api.send_to_radarr(
                    rec_id,
                    SendToRadarrRequest(root_folder_path="/movies", quality_profile_id=1),
                    user="tester",
                )
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_send_to_radarr_success_marks_recommendation_actioned(self):
        from backend.api.models import SendToRadarrRequest

        rec_id = await self._seed()
        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=True, url="http://radarr", api_key="key", tls_verify=True))
        with patch("backend.config.get_config", return_value=cfg), patch(
            "backend.integrations.radarr.RadarrClient.find_movie_by_imdb", AsyncMock(return_value=None)
        ), patch(
            "backend.integrations.radarr.RadarrClient.add_movie", AsyncMock(return_value={"id": 42})
        ):
            result = await api.send_to_radarr(
                rec_id,
                SendToRadarrRequest(root_folder_path="/movies", quality_profile_id=1),
                user="tester",
            )
        self.assertEqual(result["state"], "actioned")

    async def test_send_to_radarr_rejects_tv_candidates(self):
        from backend.api.models import SendToRadarrRequest
        from backend.utils.responses import APIException

        rec_id = await self._seed(media_type="tv")
        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=True, url="http://radarr", api_key="key", tls_verify=True))
        with patch("backend.config.get_config", return_value=cfg):
            with self.assertRaises(APIException):
                await api.send_to_radarr(
                    rec_id,
                    SendToRadarrRequest(root_folder_path="/movies", quality_profile_id=1),
                    user="tester",
                )


if __name__ == "__main__":
    unittest.main()
