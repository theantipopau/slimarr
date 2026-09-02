import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import images as api
from backend.database import Base, Movie
from backend.utils.responses import APIException


class ImagesAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "images.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        patcher = patch("backend.api.images.async_session", self.maker)
        patcher.start()
        self.addCleanup(patcher.stop)

        async with self.maker() as db:
            movie = Movie(
                plex_rating_key="1",
                title="Some Movie",
                tmdb_id=1,
                poster_path="/poster.jpg",
                status="pending",
            )
            db.add(movie)
            await db.commit()
            await db.refresh(movie)
            self.movie_id = movie.id

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_image_fetch_failure_does_not_leak_exception_detail_to_client(self):
        sensitive = "C:/Users/matt/AppData/Local/Slimarr/cache/poster.jpg permission denied"
        with patch(
            "backend.api.images.get_or_cache_image",
            AsyncMock(side_effect=OSError(sensitive)),
        ):
            with self.assertRaises(APIException) as ctx:
                await api.get_image(self.movie_id, "poster")

        exc = ctx.exception
        self.assertEqual(500, exc.status_code)
        self.assertNotIn(sensitive, exc.message)
        self.assertNotIn("C:/Users", exc.message)
