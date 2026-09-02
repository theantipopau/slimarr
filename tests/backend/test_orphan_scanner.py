import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.orphan_scanner import auto_cleanup_old_orphans
from backend.core.storage import StorageOperationResult
from backend.database import Base, OrphanedDownload


def _old_orphan(**overrides) -> OrphanedDownload:
    base = dict(
        downloader_name="sabnzbd",
        downloader_job_id="job-1",
        release_name="Some Movie",
        storage_path="/downloads/some-movie",
        found_at=datetime.now(timezone.utc) - timedelta(days=30),
        cleanup_scheduled=False,
    )
    base.update(overrides)
    return OrphanedDownload(**base)


def _result(status: str) -> StorageOperationResult:
    return StorageOperationResult(
        operation="remove",
        purpose="old_orphan_auto_cleanup",
        source_path="/downloads/some-movie",
        target_path=None,
        source_classification="local",
        target_classification=None,
        status=status,
        bytes_estimated=0,
        messages=[],
    )


class AutoCleanupOldOrphansTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "orphans.sqlite"
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

    async def test_successful_removal_deletes_the_tracking_row(self):
        async with self.maker() as db:
            db.add(_old_orphan())
            await db.commit()

        with patch("backend.core.orphan_scanner.async_session", self.maker), patch(
            "backend.core.orphan_scanner.get_config"
        ), patch(
            "backend.core.orphan_scanner.remove_path", return_value=_result("completed")
        ):
            deleted = await auto_cleanup_old_orphans(days_old=7)

        self.assertEqual(deleted, 1)
        async with self.maker() as db:
            remaining = (await db.execute(select(OrphanedDownload))).scalars().all()
        self.assertEqual(remaining, [])

    async def test_failed_removal_keeps_the_row_and_marks_it_for_retry(self):
        """Regression test: auto_cleanup_old_orphans used to delete its tracking
        row unconditionally, even when remove_path() raised — silently losing
        Slimarr's only record that a file might still be on disk. It must now
        keep the row (marked cleanup_scheduled) so the file isn't forgotten."""
        async with self.maker() as db:
            db.add(_old_orphan())
            await db.commit()

        with patch("backend.core.orphan_scanner.async_session", self.maker), patch(
            "backend.core.orphan_scanner.get_config"
        ), patch(
            "backend.core.orphan_scanner.remove_path",
            side_effect=PermissionError("file is locked"),
        ):
            deleted = await auto_cleanup_old_orphans(days_old=7)

        self.assertEqual(deleted, 0)
        async with self.maker() as db:
            remaining = (await db.execute(select(OrphanedDownload))).scalars().all()
        self.assertEqual(len(remaining), 1)
        self.assertTrue(remaining[0].cleanup_scheduled)
        self.assertIsNotNone(remaining[0].cleanup_at)

    async def test_failed_status_without_exception_also_keeps_the_row(self):
        async with self.maker() as db:
            db.add(_old_orphan())
            await db.commit()

        with patch("backend.core.orphan_scanner.async_session", self.maker), patch(
            "backend.core.orphan_scanner.get_config"
        ), patch(
            "backend.core.orphan_scanner.remove_path", return_value=_result("failed")
        ):
            deleted = await auto_cleanup_old_orphans(days_old=7)

        self.assertEqual(deleted, 0)
        async with self.maker() as db:
            remaining = (await db.execute(select(OrphanedDownload))).scalars().all()
        self.assertEqual(len(remaining), 1)
        self.assertTrue(remaining[0].cleanup_scheduled)

    async def test_orphan_with_no_storage_path_is_deleted_without_calling_remove_path(self):
        async with self.maker() as db:
            db.add(_old_orphan(storage_path=None))
            await db.commit()

        with patch("backend.core.orphan_scanner.async_session", self.maker), patch(
            "backend.core.orphan_scanner.get_config"
        ), patch("backend.core.orphan_scanner.remove_path") as mock_remove:
            deleted = await auto_cleanup_old_orphans(days_old=7)

        mock_remove.assert_not_called()
        self.assertEqual(deleted, 1)


if __name__ == "__main__":
    unittest.main()
