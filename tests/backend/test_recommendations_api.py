import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.api import recommendations as api
from backend.database import (
    Base,
    Movie,
    Recommendation,
    RecommendationCandidate,
    RecommendationFeedback,
    RecommendationReason,
    StreamingAvailability,
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

    async def test_provider_id_filter_is_applied_before_pagination(self):
        # Regression: provider_id used to be filtered in Python *after*
        # offset()/limit() had already run and after `total` was computed
        # from an unfiltered count query - a page could come back empty (or
        # missing matches split across pages) while `total` still reported
        # the unfiltered count. Filtering at the SQL level fixes both.
        matching_id = await self._seed(tmdb_id=1)
        await self._seed(tmdb_id=2)  # no availability row - must never match

        async with self.maker() as db:
            matching_rec = (await db.execute(select(Recommendation).where(Recommendation.id == matching_id))).scalar_one()
            db.add(StreamingAvailability(
                candidate_id=matching_rec.candidate_id,
                region="US", provider_id=8, provider_name="Netflix", availability_type="flatrate",
                checked_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            ))
            await db.commit()

        result = await api.list_recommendations(provider_id=8, user="tester")

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["id"], matching_id)

    async def test_provider_id_filter_excludes_everything_when_no_match(self):
        await self._seed(tmdb_id=1)
        result = await api.list_recommendations(provider_id=999, user="tester")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["recommendations"], [])

    async def test_already_in_plex_is_correct_per_row_after_batching(self):
        # Regression guard for the N+1 -> batched rewrite of the Plex-
        # ownership check: each row must still get its own correct answer,
        # not e.g. every row incorrectly matching the first query's result.
        owned_by_tmdb = await self._seed(tmdb_id=100, imdb_id=None)
        owned_by_imdb = await self._seed(tmdb_id=200, imdb_id="tt9999999")
        not_owned = await self._seed(tmdb_id=300, imdb_id="tt1111111")

        async with self.maker() as db:
            db.add(Movie(plex_rating_key="1", title="A", tmdb_id=100, status="pending"))
            db.add(Movie(plex_rating_key="2", title="B", tmdb_id=999, imdb_id="tt9999999", status="pending"))
            await db.commit()

        result = await api.list_recommendations(state="", user="tester")
        by_id = {r["id"]: r["already_in_plex"] for r in result["recommendations"]}

        self.assertTrue(by_id[owned_by_tmdb])
        self.assertTrue(by_id[owned_by_imdb])
        self.assertFalse(by_id[not_owned])

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

    async def test_radarr_options_requires_radarr_configured(self):
        from backend.utils.responses import APIException

        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=False, url="", api_key=""))
        with patch("backend.config.get_config", return_value=cfg):
            with self.assertRaises(APIException):
                await api.radarr_handoff_options(user="tester")

    async def test_radarr_options_returns_folders_and_profiles(self):
        # RadarrClient binds get_config via `from backend.config import
        # get_config` at radarr.py's own module scope, so its __init__ reads
        # backend.integrations.radarr.get_config, not backend.config.get_config
        # - both must be patched for a RadarrClient constructed inside the
        # route to see this test's config rather than whatever real config
        # (or another test's leaked mock) radarr.py resolved at import time.
        cfg = SimpleNamespace(radarr=SimpleNamespace(enabled=True, url="http://radarr", api_key="key", tls_verify=True))
        with (
            patch("backend.config.get_config", return_value=cfg),
            patch("backend.integrations.radarr.get_config", return_value=cfg),
            patch(
                "backend.integrations.radarr.RadarrClient.get_root_folders",
                AsyncMock(return_value=[{"path": "/movies"}, {"path": ""}]),
            ),
            patch(
                "backend.integrations.radarr.RadarrClient.get_quality_profiles",
                AsyncMock(return_value=[{"id": 4, "name": "HD-1080p"}]),
            ),
        ):
            result = await api.radarr_handoff_options(user="tester")

        self.assertEqual(result["root_folders"], [{"path": "/movies"}])
        self.assertEqual(result["quality_profiles"], [{"id": 4, "name": "HD-1080p"}])

    async def test_sonarr_options_requires_sonarr_configured(self):
        from backend.utils.responses import APIException

        cfg = SimpleNamespace(sonarr=SimpleNamespace(enabled=False, url="", api_key=""))
        with patch("backend.config.get_config", return_value=cfg):
            with self.assertRaises(APIException):
                await api.sonarr_handoff_options(user="tester")

    async def test_sonarr_options_returns_folders_and_profiles(self):
        cfg = SimpleNamespace(sonarr=SimpleNamespace(enabled=True, url="http://sonarr", api_key="key", tls_verify=True))
        with (
            patch("backend.config.get_config", return_value=cfg),
            patch("backend.integrations.sonarr.get_config", return_value=cfg),
            patch(
                "backend.integrations.sonarr.SonarrClient.get_root_folders",
                AsyncMock(return_value=[{"path": "/tv"}]),
            ),
            patch(
                "backend.integrations.sonarr.SonarrClient.get_quality_profiles",
                AsyncMock(return_value=[{"id": 1, "name": "HD-720p"}]),
            ),
        ):
            result = await api.sonarr_handoff_options(user="tester")

        self.assertEqual(result["root_folders"], [{"path": "/tv"}])
        self.assertEqual(result["quality_profiles"], [{"id": 1, "name": "HD-720p"}])

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
            "backend.integrations.radarr.get_config", return_value=cfg
        ), patch(
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
            "backend.integrations.radarr.get_config", return_value=cfg
        ), patch(
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
