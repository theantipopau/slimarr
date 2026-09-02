import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.recommendations.correlation import CorrelationSnapshot
from backend.core.recommendations.engine import _apply_retention, record_feedback, run_recommendation_refresh
from backend.database import (
    Base,
    Movie,
    Recommendation,
    RecommendationCandidate,
    RecommendationFeedback,
    RecommendationReason,
)


def _rec_config(**overrides):
    base = dict(
        enabled=True,
        region="",
        subscribed_providers=[],
        enabled_categories=["collection_completion", "related_title"],
        media_types=["movie"],
        minimum_score=10.0,
        languages=[],
        genres_include=[],
        genres_exclude=[],
        excluded_keywords=[],
        use_plex_watch_history=False,
        refresh_interval_hours=24,
        max_recommendations_retained=500,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _owned_movie(**overrides) -> Movie:
    base = dict(
        plex_rating_key="key-1", title="Toy Story", year=1995, tmdb_id=1, imdb_id="tt0114709",
        status="improved", total_savings=0, times_replaced=0, slimarr_locked=0, force_keep=0,
        allow_larger_replacements=0, quality_intent="space_saver",
    )
    base.update(overrides)
    return Movie(**base)


class RecommendationEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "engine.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.get_config_patcher = patch("backend.config.get_config")
        mock_get_config = self.get_config_patcher.start()
        self.rec_config = _rec_config()
        mock_get_config.return_value = SimpleNamespace(
            recommendations=self.rec_config,
            radarr=SimpleNamespace(enabled=False, url="", api_key=""),
            sonarr=SimpleNamespace(enabled=False, url="", api_key=""),
        )

        self.async_session_patcher = patch("backend.core.recommendations.engine.async_session", self.maker)
        self.async_session_patcher.start()
        self.correlation_session_patcher = patch(
            "backend.core.recommendations.correlation.async_session", self.maker
        )
        self.correlation_session_patcher.start()

    async def asyncTearDown(self):
        self.get_config_patcher.stop()
        self.async_session_patcher.stop()
        self.correlation_session_patcher.stop()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _seed_movie(self, **overrides) -> Movie:
        async with self.maker() as db:
            movie = _owned_movie(**overrides)
            db.add(movie)
            await db.commit()
            await db.refresh(movie)
        return movie

    def _mock_tmdb(self, movie_detail=None, collection=None, external_ids=None):
        client = AsyncMock()
        client.get_movie_full = AsyncMock(return_value=movie_detail or {})
        client.get_collection = AsyncMock(return_value=collection or {"parts": []})
        client.get_external_ids = AsyncMock(return_value=external_ids or {})
        client.get_watch_providers = AsyncMock(return_value={"results": {}})
        return client

    async def test_disabled_config_short_circuits_without_touching_tmdb(self):
        self.rec_config.enabled = False
        with patch("backend.integrations.tmdb.TMDBClient") as mock_cls:
            summary = await run_recommendation_refresh()
        self.assertEqual(summary["status"], "disabled")
        mock_cls.assert_not_called()

    async def test_missing_collection_member_is_persisted_as_active_with_reasons(self):
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "Toy Story Collection"}},
            collection={"parts": [
                {"id": 1, "title": "Toy Story"},
                {"id": 863, "title": "Toy Story 2", "release_date": "1999-11-24"},
            ]},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["created"], 1)
        async with self.maker() as db:
            candidate = (await db.execute(select(RecommendationCandidate))).scalars().first()
            self.assertEqual(candidate.tmdb_id, 863)
            rec = (await db.execute(select(Recommendation))).scalars().first()
            self.assertEqual(rec.state, "active")
            self.assertGreater(rec.score, 0)
            reasons = (await db.execute(select(RecommendationReason))).scalars().all()
            self.assertTrue(any(r.reason_code == "missing_collection_member" for r in reasons))

    async def test_running_refresh_twice_does_not_create_duplicate_rows(self):
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "Toy Story Collection"}},
            collection={"parts": [{"id": 1}, {"id": 863, "title": "Toy Story 2"}]},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            await run_recommendation_refresh()
            second_summary = await run_recommendation_refresh()

        self.assertEqual(second_summary["created"], 0)
        self.assertEqual(second_summary["updated"], 1)
        async with self.maker() as db:
            all_candidates = (await db.execute(select(RecommendationCandidate))).scalars().all()
            all_recs = (await db.execute(select(Recommendation))).scalars().all()
        self.assertEqual(len(all_candidates), 1)
        self.assertEqual(len(all_recs), 1)

    async def test_dismissed_recommendation_is_never_resurrected_by_a_later_refresh(self):
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "X"}},
            collection={"parts": [{"id": 1}, {"id": 863, "title": "Toy Story 2"}]},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            await run_recommendation_refresh()

        async with self.maker() as db:
            rec = (await db.execute(select(Recommendation))).scalars().first()
            rec.state = "dismissed"
            await db.commit()

        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["skipped_protected"], 1)
        async with self.maker() as db:
            rec = (await db.execute(select(Recommendation))).scalars().first()
            self.assertEqual(rec.state, "dismissed")

    async def test_already_owned_collection_members_never_get_a_recommendation_row(self):
        await self._seed_movie(tmdb_id=1)
        await self._seed_movie(plex_rating_key="key-2", title="Toy Story 2", tmdb_id=863, imdb_id="tt0120363")
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "X"}},
            collection={"parts": [{"id": 1}, {"id": 863}]},  # both owned
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["candidates_sourced"], 0)
        async with self.maker() as db:
            self.assertEqual((await db.execute(select(Recommendation))).scalars().all(), [])

    async def test_already_managed_in_radarr_is_persisted_as_already_managed_not_active(self):
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "X"}},
            collection={"parts": [{"id": 1}, {"id": 863, "title": "Toy Story 2"}]},
            external_ids={"imdb_id": "tt0120363"},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb), patch(
            "backend.core.recommendations.correlation._radarr_owned_imdb_ids",
            AsyncMock(return_value=frozenset({"tt0120363"})),
        ):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["skipped_excluded"], 1)
        async with self.maker() as db:
            rec = (await db.execute(select(Recommendation))).scalars().first()
            self.assertEqual(rec.state, "already_managed")

    async def test_candidates_below_minimum_score_are_not_persisted(self):
        self.rec_config.minimum_score = 999.0  # nothing can clear this
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "X"}},
            collection={"parts": [{"id": 1}, {"id": 863, "title": "Toy Story 2"}]},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["created"], 0)
        async with self.maker() as db:
            self.assertEqual((await db.execute(select(Recommendation))).scalars().all(), [])

    async def test_fetched_imdb_id_is_persisted_onto_the_candidate_row(self):
        """Regression test: get_external_ids() was fetched during refresh to
        correlate against Radarr, but the resulting imdb_id was never written
        onto RecommendationCandidate — meaning send-to-radarr's "already
        managed" check and the API's imdb_id field would silently never
        work in production despite the lookup having succeeded."""
        await self._seed_movie()
        tmdb = self._mock_tmdb(
            movie_detail={"belongs_to_collection": {"id": 10, "name": "X"}},
            collection={"parts": [{"id": 1}, {"id": 863, "title": "Toy Story 2"}]},
            external_ids={"imdb_id": "tt0120363"},
        )
        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            await run_recommendation_refresh()

        async with self.maker() as db:
            candidate = (await db.execute(select(RecommendationCandidate))).scalars().first()
        self.assertEqual(candidate.imdb_id, "tt0120363")

    async def test_no_owned_movies_with_tmdb_id_produces_an_empty_but_successful_run(self):
        summary = await run_recommendation_refresh()
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["movies_scanned"], 0)

    async def test_sourcing_failure_for_one_movie_does_not_abort_the_whole_refresh(self):
        await self._seed_movie(plex_rating_key="key-1", tmdb_id=1)
        await self._seed_movie(plex_rating_key="key-2", title="Movie B", tmdb_id=2, imdb_id="tt002")

        call_count = 0

        async def flaky_get_movie_full(tmdb_id):
            nonlocal call_count
            call_count += 1
            if tmdb_id == 1:
                raise RuntimeError("network blip")
            return {"belongs_to_collection": {"id": 10, "name": "X"}}

        tmdb = self._mock_tmdb(collection={"parts": [{"id": 2}, {"id": 999, "title": "Missing"}]})
        tmdb.get_movie_full = AsyncMock(side_effect=flaky_get_movie_full)

        with patch("backend.core.recommendations.engine.TMDBClient", return_value=tmdb):
            summary = await run_recommendation_refresh()

        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["created"], 1)  # movie B's sourcing still succeeded


class RetentionAndFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "retention.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.patcher = patch("backend.core.recommendations.engine.async_session", self.maker)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _seed_recommendation(self, tmdb_id: int, score: float, state: str = "active") -> int:
        async with self.maker() as db:
            candidate = RecommendationCandidate(media_type="movie", tmdb_id=tmdb_id, title=f"Movie {tmdb_id}")
            db.add(candidate)
            await db.flush()
            rec = Recommendation(candidate_id=candidate.id, category="related_title", score=score, state=state)
            db.add(rec)
            await db.commit()
            return rec.id

    async def test_retention_expires_lowest_scored_active_recommendations_beyond_the_cap(self):
        await self._seed_recommendation(1, score=90.0)
        await self._seed_recommendation(2, score=50.0)
        await self._seed_recommendation(3, score=10.0)  # should be expired, lowest score

        await _apply_retention(max_retained=2)

        async with self.maker() as db:
            all_recs = (await db.execute(select(Recommendation))).scalars().all()
        by_score = {r.score: r.state for r in all_recs}
        self.assertEqual(by_score[90.0], "active")
        self.assertEqual(by_score[50.0], "active")
        self.assertEqual(by_score[10.0], "expired")

    async def test_retention_never_touches_protected_states(self):
        await self._seed_recommendation(1, score=90.0, state="active")
        await self._seed_recommendation(2, score=5.0, state="dismissed")
        await self._seed_recommendation(3, score=1.0, state="watchlisted")

        await _apply_retention(max_retained=0)  # would expire everything active

        async with self.maker() as db:
            states = {r.score: r.state for r in (await db.execute(select(Recommendation))).scalars().all()}
        self.assertEqual(states[5.0], "dismissed")
        self.assertEqual(states[1.0], "watchlisted")
        self.assertEqual(states[90.0], "expired")  # only the active one is touched

    async def test_retention_is_a_no_op_when_under_the_cap(self):
        await self._seed_recommendation(1, score=90.0)
        await _apply_retention(max_retained=500)
        async with self.maker() as db:
            rec = (await db.execute(select(Recommendation))).scalars().first()
        self.assertEqual(rec.state, "active")

    async def test_record_feedback_appends_an_event_and_returns_true(self):
        rec_id = await self._seed_recommendation(1, score=50.0)
        ok = await record_feedback(rec_id, "dismissed", {"reason": "not interested"})
        self.assertTrue(ok)
        async with self.maker() as db:
            events = (await db.execute(select(RecommendationFeedback))).scalars().all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "dismissed")
        self.assertIn("not interested", events[0].detail)

    async def test_record_feedback_returns_false_for_unknown_recommendation(self):
        ok = await record_feedback(999999, "shown")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
