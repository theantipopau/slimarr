import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.recommendations.correlation import (
    build_correlation_snapshot,
    is_in_plex,
    is_managed_in_radarr,
    is_managed_in_sonarr,
)
from backend.database import Base, Movie


def _movie(**overrides) -> Movie:
    base = dict(
        plex_rating_key=f"key-{overrides.get('tmdb_id', 'x')}",
        title="Owned Movie",
        status="pending",
        total_savings=0,
        times_replaced=0,
        slimarr_locked=0,
        force_keep=0,
        allow_larger_replacements=0,
        quality_intent="space_saver",
    )
    base.update(overrides)
    return Movie(**base)


def _cfg(*, radarr_enabled=False, sonarr_enabled=False):
    return SimpleNamespace(
        radarr=SimpleNamespace(enabled=radarr_enabled, url="http://radarr", api_key="key"),
        sonarr=SimpleNamespace(enabled=sonarr_enabled, url="http://sonarr", api_key="key"),
    )


class CorrelationSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "correlation.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_plex_snapshot_only_includes_movies_with_a_tmdb_id(self):
        async with self.maker() as db:
            db.add(_movie(tmdb_id=1, imdb_id="tt001"))
            db.add(_movie(tmdb_id=None, imdb_id="tt002", plex_rating_key="key-none"))
            await db.commit()

        with patch("backend.core.recommendations.correlation.async_session", self.maker):
            snapshot = await build_correlation_snapshot(_cfg())

        self.assertEqual(snapshot.plex_tmdb_ids, frozenset({1}))
        self.assertEqual(snapshot.plex_imdb_ids, frozenset({"tt001"}))

    async def test_radarr_snapshot_is_empty_when_disabled(self):
        with patch("backend.core.recommendations.correlation.async_session", self.maker):
            snapshot = await build_correlation_snapshot(_cfg(radarr_enabled=False))
        self.assertEqual(snapshot.radarr_imdb_ids, frozenset())

    async def test_radarr_snapshot_fetched_once_when_enabled(self):
        mock_get_movies = AsyncMock(return_value=[
            {"imdbId": "tt100"}, {"imdbId": "tt200"}, {"title": "no imdb id"},
        ])
        with patch("backend.core.recommendations.correlation.async_session", self.maker), patch(
            "backend.integrations.radarr.RadarrClient.get_movies", mock_get_movies
        ):
            snapshot = await build_correlation_snapshot(_cfg(radarr_enabled=True))

        mock_get_movies.assert_awaited_once()
        self.assertEqual(snapshot.radarr_imdb_ids, frozenset({"tt100", "tt200"}))

    async def test_radarr_failure_degrades_to_empty_snapshot_instead_of_raising(self):
        with patch("backend.core.recommendations.correlation.async_session", self.maker), patch(
            "backend.integrations.radarr.RadarrClient.get_movies",
            AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            snapshot = await build_correlation_snapshot(_cfg(radarr_enabled=True))
        self.assertEqual(snapshot.radarr_imdb_ids, frozenset())

    async def test_sonarr_snapshot_normalizes_titles(self):
        mock_get_series = AsyncMock(return_value=[{"title": "  Some Show  "}, {"title": "Other Show"}])
        with patch("backend.core.recommendations.correlation.async_session", self.maker), patch(
            "backend.integrations.sonarr.SonarrClient.get_all_series", mock_get_series
        ):
            snapshot = await build_correlation_snapshot(_cfg(sonarr_enabled=True))
        self.assertEqual(snapshot.sonarr_titles, frozenset({"some show", "other show"}))


class CorrelationHelperTests(unittest.TestCase):
    def test_is_in_plex_matches_on_tmdb_id_or_imdb_id(self):
        from backend.core.recommendations.correlation import CorrelationSnapshot

        snapshot = CorrelationSnapshot(plex_tmdb_ids=frozenset({1}), plex_imdb_ids=frozenset({"tt1"}))
        self.assertTrue(is_in_plex(snapshot, tmdb_id=1, imdb_id=None))
        self.assertTrue(is_in_plex(snapshot, tmdb_id=None, imdb_id="tt1"))
        self.assertFalse(is_in_plex(snapshot, tmdb_id=2, imdb_id="tt2"))

    def test_is_managed_in_radarr(self):
        from backend.core.recommendations.correlation import CorrelationSnapshot

        snapshot = CorrelationSnapshot(radarr_imdb_ids=frozenset({"tt1"}))
        self.assertTrue(is_managed_in_radarr(snapshot, imdb_id="tt1"))
        self.assertFalse(is_managed_in_radarr(snapshot, imdb_id=None))

    def test_is_managed_in_sonarr_is_case_and_whitespace_insensitive(self):
        from backend.core.recommendations.correlation import CorrelationSnapshot

        snapshot = CorrelationSnapshot(sonarr_titles=frozenset({"some show"}))
        self.assertTrue(is_managed_in_sonarr(snapshot, title="  SOME SHOW  "))
        self.assertFalse(is_managed_in_sonarr(snapshot, title="a different show"))


if __name__ == "__main__":
    unittest.main()
