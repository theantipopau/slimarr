import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import (
    Base,
    Recommendation,
    RecommendationCandidate,
    RecommendationFeedback,
    RecommendationReason,
    StreamingAvailability,
)


def _candidate(**overrides) -> RecommendationCandidate:
    base = dict(media_type="movie", title="The Little Mermaid II", tmdb_id=12345)
    base.update(overrides)
    return RecommendationCandidate(**base)


class RecommendationSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "recs.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_duplicate_candidate_same_media_type_and_tmdb_id_is_rejected(self):
        async with self.maker() as db:
            db.add(_candidate())
            await db.commit()

        async with self.maker() as db:
            db.add(_candidate())
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_same_tmdb_id_different_media_type_is_allowed(self):
        """A movie and a TV show can legitimately share a TMDB ID space
        collision is avoided by media_type being part of the unique key."""
        async with self.maker() as db:
            db.add(_candidate(media_type="movie"))
            db.add(_candidate(media_type="tv"))
            await db.commit()

            rows = (await db.execute(select(RecommendationCandidate))).scalars().all()
        self.assertEqual(len(rows), 2)

    async def test_duplicate_recommendation_same_candidate_and_category_is_rejected(self):
        async with self.maker() as db:
            candidate = _candidate()
            db.add(candidate)
            await db.flush()
            db.add(Recommendation(candidate_id=candidate.id, category="sequel_prequel", score=50.0))
            await db.commit()

        async with self.maker() as db:
            candidate = (await db.execute(select(RecommendationCandidate))).scalars().first()
            db.add(Recommendation(candidate_id=candidate.id, category="sequel_prequel", score=10.0))
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_same_candidate_different_category_is_allowed(self):
        async with self.maker() as db:
            candidate = _candidate()
            db.add(candidate)
            await db.flush()
            db.add(Recommendation(candidate_id=candidate.id, category="sequel_prequel", score=50.0))
            db.add(Recommendation(candidate_id=candidate.id, category="collection_completion", score=60.0))
            await db.commit()

            rows = (await db.execute(select(Recommendation))).scalars().all()
        self.assertEqual(len(rows), 2)

    async def test_duplicate_streaming_availability_row_is_rejected(self):
        from datetime import datetime, timedelta, timezone

        async with self.maker() as db:
            candidate = _candidate()
            db.add(candidate)
            await db.flush()
            expires = datetime.now(timezone.utc) + timedelta(days=1)
            db.add(
                StreamingAvailability(
                    candidate_id=candidate.id,
                    region="AU",
                    provider_id=8,
                    provider_name="Netflix",
                    availability_type="flatrate",
                    expires_at=expires,
                )
            )
            await db.commit()

        async with self.maker() as db:
            candidate = (await db.execute(select(RecommendationCandidate))).scalars().first()
            db.add(
                StreamingAvailability(
                    candidate_id=candidate.id,
                    region="AU",
                    provider_id=8,
                    provider_name="Netflix",
                    availability_type="flatrate",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            )
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_deleting_a_candidate_cascades_to_recommendations_and_availability(self):
        """Verifies SQLAlchemy's ORM-level cascade=all,delete-orphan (which
        issues explicit child DELETEs when session.delete() is called on a
        loaded parent). This does NOT require or exercise a DB-level
        ON DELETE CASCADE — the production engine does not enable
        PRAGMA foreign_keys, so any future bulk/Core-level delete of
        recommendation_candidates (bypassing the ORM) must delete child rows
        explicitly rather than relying on this test's guarantee."""
        from datetime import datetime, timedelta, timezone

        async with self.maker() as db:
            candidate = _candidate()
            db.add(candidate)
            await db.flush()
            rec = Recommendation(candidate_id=candidate.id, category="sequel_prequel", score=50.0)
            db.add(rec)
            db.add(
                StreamingAvailability(
                    candidate_id=candidate.id,
                    region="AU",
                    provider_id=8,
                    provider_name="Netflix",
                    availability_type="flatrate",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            )
            await db.flush()
            db.add(RecommendationReason(recommendation_id=rec.id, reason_code="direct_sequel", explanation="x"))
            db.add(RecommendationFeedback(recommendation_id=rec.id, action="shown"))
            await db.commit()

        async with self.maker() as db:
            candidate = (await db.execute(select(RecommendationCandidate))).scalars().first()
            await db.delete(candidate)
            await db.commit()

        async with self.maker() as db:
            self.assertEqual((await db.execute(select(Recommendation))).scalars().all(), [])
            self.assertEqual((await db.execute(select(StreamingAvailability))).scalars().all(), [])
            self.assertEqual((await db.execute(select(RecommendationReason))).scalars().all(), [])
            self.assertEqual((await db.execute(select(RecommendationFeedback))).scalars().all(), [])


if __name__ == "__main__":
    unittest.main()
