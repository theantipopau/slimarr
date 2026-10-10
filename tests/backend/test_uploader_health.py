import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.downloader import get_uploader_health_scores
from backend.database import Base, UploaderStats


class UploaderHealthBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "uploader_health.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.maker() as db:
            db.add(UploaderStats(uploader="good-group", health_score=0.9))
            db.add(UploaderStats(uploader="bad-group", health_score=0.1))
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_batch_returns_scores_for_known_uploaders(self):
        with patch("backend.core.downloader.async_session", self.maker):
            scores = await get_uploader_health_scores(["good-group", "bad-group"])

        self.assertEqual(scores, {"good-group": 0.9, "bad-group": 0.1})

    async def test_batch_omits_unknown_uploaders(self):
        with patch("backend.core.downloader.async_session", self.maker):
            scores = await get_uploader_health_scores(["good-group", "never-seen-group"])

        self.assertEqual(scores, {"good-group": 0.9})
        self.assertNotIn("never-seen-group", scores)

    async def test_empty_input_short_circuits_without_a_query(self):
        with patch("backend.core.downloader.async_session", self.maker):
            scores = await get_uploader_health_scores([])

        self.assertEqual(scores, {})

    async def test_blank_entries_are_ignored(self):
        with patch("backend.core.downloader.async_session", self.maker):
            scores = await get_uploader_health_scores(["", "good-group", ""])

        self.assertEqual(scores, {"good-group": 0.9})


class CompareReleasePrecomputedUploaderHealthTests(unittest.TestCase):
    def _compare(self, **overrides):
        from backend.config import SlimarrConfig
        from backend.core.comparer import compare_release

        kwargs = dict(
            local_size=2_000_000_000,
            local_resolution="1080p",
            local_codec="h264",
            candidate_size=1_100_000_000,
            candidate_title="Movie.Title.2022.1080p.WEB-DL.x265-GRP",
            movie_title="Movie Title",
            movie_year=2022,
        )
        kwargs.update(overrides)
        with patch("backend.core.comparer.get_config", return_value=SlimarrConfig()):
            return compare_release(**kwargs)

    def test_precomputed_score_is_used(self):
        high = self._compare(uploader_health_score=0.95)
        low = self._compare(uploader_health_score=0.05)
        self.assertEqual(high.decision, "accept")
        self.assertNotEqual(high.score, low.score)

    def test_missing_score_is_neutral(self):
        self.assertEqual(self._compare().score, self._compare(uploader_health_score=0.5).score)


if __name__ == "__main__":
    unittest.main()
