import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.storage import (
    classify_storage_path,
    configured_nas_prefixes,
    is_nas_path,
    move_path,
    nas_policy_snapshot,
    normalize_path,
    path_matches_prefix,
    persisted_storage_operation_snapshot,
    preflight_storage_path,
    recent_storage_failures,
    remove_path,
    reset_storage_operation_telemetry,
    restore_nas_cooldown_state,
    storage_operation_metrics,
    storage_operation_snapshot,
)
from backend.database import Base, StorageOperationLog, StoragePathHealth
import backend.core.storage as storage


class StoragePathTests(unittest.TestCase):
    def test_normalize_path_handles_windows_and_case(self):
        self.assertEqual("z:/movies/title", normalize_path("Z:\\Movies\\Title\\"))

    def test_normalize_path_collapses_embedded_traversal_segments(self):
        self.assertEqual(
            normalize_path("/mnt/nas/movies"),
            normalize_path("/mnt/local/../nas/movies"),
        )
        self.assertEqual("z:/movies2", normalize_path("Z:/Movies/../Movies2"))

    def test_normalize_path_preserves_unc_double_slash_prefix(self):
        self.assertTrue(normalize_path("//nas/share/A/file.mkv").startswith("//"))

    def test_normalize_path_case_folding_is_platform_dependent(self):
        with patch("backend.core.storage.os.name", "nt"):
            self.assertEqual("z:/movies/title", normalize_path("Z:/Movies/Title"))
        with patch("backend.core.storage.os.name", "posix"):
            self.assertEqual("/mnt/NAS/Movies", normalize_path("/mnt/NAS/Movies"))

    def test_classify_storage_path_traversal_cannot_evade_nas_classification(self):
        cfg = SimpleNamespace(
            files=SimpleNamespace(nas_path_prefixes=["/mnt/nas"], recycling_bin="")
        )
        self.assertEqual(
            "nas",
            classify_storage_path("/mnt/local/../nas/movies/file.mkv", cfg).classification,
        )

    def test_path_matches_prefix_respects_path_boundaries(self):
        prefixes = ["Z:/Movies"]
        self.assertTrue(path_matches_prefix("Z:/Movies/Film/file.mkv", prefixes))
        self.assertTrue(path_matches_prefix("Z:/Movies", prefixes))
        self.assertFalse(path_matches_prefix("Z:/Movies-Backup/file.mkv", prefixes))

    def test_is_nas_path_accepts_config_or_prefixes(self):
        cfg = SimpleNamespace(files=SimpleNamespace(nas_path_prefixes=["/mnt/nas/movies"]))
        self.assertTrue(is_nas_path("/mnt/nas/movies/A/file.mkv", cfg))
        self.assertTrue(is_nas_path("/mnt/nas/movies/A/file.mkv", ["/mnt/nas"]))
        self.assertFalse(is_nas_path("/mnt/local/movies/A/file.mkv", cfg))

    def test_classify_storage_path_marks_nas_recycling_network_and_local(self):
        cfg = SimpleNamespace(
            files=SimpleNamespace(
                nas_path_prefixes=["Z:/Movies"],
                recycling_bin="D:/SlimarrRecycle",
            )
        )

        self.assertEqual("nas", classify_storage_path("Z:/Movies/A/file.mkv", cfg).classification)
        self.assertEqual(
            "recycling",
            classify_storage_path("D:/SlimarrRecycle/A/file.mkv", cfg).classification,
        )
        self.assertEqual("network", classify_storage_path("//nas/share/A/file.mkv", cfg).classification)
        self.assertEqual("local", classify_storage_path("C:/Temp/file.mkv", cfg).classification)

    def test_configured_nas_prefixes_filters_empty_values(self):
        cfg = SimpleNamespace(files=SimpleNamespace(nas_path_prefixes=["", " Z:/Movies ", None]))
        self.assertEqual(["Z:/Movies"], configured_nas_prefixes(cfg))

    def test_preflight_blocks_empty_path(self):
        cfg = SimpleNamespace(files=SimpleNamespace(nas_path_prefixes=[]))
        result = preflight_storage_path("", cfg)
        self.assertEqual("block", result.status)
        self.assertIn("Path is empty", result.messages)

    def test_preflight_reports_existing_local_path(self):
        cfg = SimpleNamespace(files=SimpleNamespace(nas_path_prefixes=[]))
        result = preflight_storage_path(__file__, cfg, purpose="test_file")
        self.assertEqual("ok", result.status)
        self.assertEqual("local", result.classification)
        self.assertTrue(result.exists)
        self.assertTrue(result.parent_exists)


class StorageOperationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_storage_operation_telemetry()

    def _config(self):
        return SimpleNamespace(files=SimpleNamespace(nas_path_prefixes=[], recycling_bin=""))

    async def test_move_path_moves_file_and_reports_classifications(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            target = Path(temp_dir) / "target.mkv"
            source.write_bytes(b"movie")

            result = await move_path(str(source), str(target), self._config(), purpose="test_move")

            self.assertEqual("completed", result.status)
            self.assertEqual("move", result.operation)
            self.assertEqual("local", result.source_classification)
            self.assertEqual("local", result.target_classification)
            self.assertFalse(source.exists())
            self.assertEqual(b"movie", target.read_bytes())
            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("move:completed"))
            self.assertEqual(5, metrics.get("move:bytes_estimated"))

    async def test_move_measures_source_only_once(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            target = Path(temp_dir) / "target.mkv"
            source.write_bytes(b"movie")

            with patch(
                "backend.core.storage._estimated_path_bytes",
                wraps=storage._estimated_path_bytes,
            ) as estimate:
                await move_path(str(source), str(target), self._config(), purpose="test_measure_once")

            self.assertEqual(1, estimate.call_count)

    async def test_cross_device_nas_move_uses_chunked_copy(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            nas_dir = Path(temp_dir) / "nas"
            target = nas_dir / "target.mkv"
            nas_dir.mkdir()
            source.write_bytes(b"movie")
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                    nas_max_transfer_mbps=0,
                    nas_copy_chunk_mb=1,
                )
            )

            with (
                patch("backend.core.storage._same_storage_device", return_value=False),
                patch(
                    "backend.core.storage._persisted_nas_usage_24h",
                    AsyncMock(return_value=(0, 0)),
                ),
            ):
                result = await move_path(
                    str(source),
                    str(target),
                    cfg,
                    purpose="place_replacement",
                )

            self.assertFalse(source.exists())
            self.assertEqual(b"movie", target.read_bytes())
            self.assertIn(
                "Cross-device NAS copy uses chunked transfer without a rate limit",
                result.messages,
            )

    async def test_copy_throttled_reports_false_when_source_removal_fails(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            target = Path(temp_dir) / "target.mkv"
            source.write_bytes(b"movie")
            cfg = SimpleNamespace(files=SimpleNamespace(nas_copy_chunk_mb=1, nas_max_transfer_mbps=0))

            real_remove = os.remove

            def fake_remove(path, *args, **kwargs):
                if str(path) == str(source):
                    raise OSError("permission denied")
                return real_remove(path, *args, **kwargs)

            with patch("backend.core.storage.os.remove", side_effect=fake_remove):
                removed = storage._copy_file_throttled(str(source), str(target), cfg)

            self.assertFalse(removed)
            self.assertTrue(target.exists())
            self.assertEqual(b"movie", target.read_bytes())
            self.assertTrue(source.exists(), "source must be left in place, not silently lost")

    async def test_move_reports_completed_with_warning_when_source_cleanup_fails(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            nas_dir = Path(temp_dir) / "nas"
            target = nas_dir / "target.mkv"
            nas_dir.mkdir()
            source.write_bytes(b"movie")
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                    nas_max_transfer_mbps=0,
                    nas_copy_chunk_mb=1,
                )
            )

            real_remove = os.remove

            def fake_remove(path, *args, **kwargs):
                if str(path) == str(source):
                    raise OSError("permission denied")
                return real_remove(path, *args, **kwargs)

            with (
                patch("backend.core.storage._same_storage_device", return_value=False),
                patch(
                    "backend.core.storage._persisted_nas_usage_24h",
                    AsyncMock(return_value=(0, 0)),
                ),
                patch("backend.core.storage.os.remove", side_effect=fake_remove),
            ):
                result = await move_path(str(source), str(target), cfg, purpose="place_replacement")

            # The copy genuinely succeeded - this must be reported as completed
            # (with a warning), never as a failed move that could trigger a
            # caller to redo the whole copy on top of an already-good target.
            self.assertEqual("completed", result.status)
            self.assertTrue(target.exists())
            self.assertEqual(b"movie", target.read_bytes())
            self.assertTrue(source.exists())
            self.assertTrue(
                any("could not be removed" in message for message in result.messages),
                result.messages,
            )

    async def test_remove_path_deletes_file(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "old.mkv"
            target.write_bytes(b"old")

            result = await remove_path(str(target), self._config(), purpose="test_remove")

            self.assertEqual("completed", result.status)
            self.assertEqual("remove", result.operation)
            self.assertFalse(target.exists())
            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("remove:completed"))
            self.assertEqual(3, metrics.get("remove:bytes_estimated"))

    async def test_remove_path_skips_missing_file(self):
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.mkv"

            result = await remove_path(str(missing), self._config(), purpose="test_remove_missing")

            self.assertEqual("skipped", result.status)
            self.assertIn("Path does not exist; remove skipped", result.messages)
            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("remove:skipped"))

    async def test_remove_path_recursively_deletes_directory(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "download"
            folder.mkdir()
            (folder / "movie.mkv").write_bytes(b"video")

            result = await remove_path(
                str(folder),
                self._config(),
                purpose="test_recursive_remove",
                recursive=True,
            )

            self.assertEqual("completed", result.status)
            self.assertFalse(folder.exists())

    async def test_remove_reuses_known_size_without_tree_scan(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "download"
            folder.mkdir()
            (folder / "movie.mkv").write_bytes(b"video")

            with patch("backend.core.storage._estimated_path_bytes") as estimate:
                result = await remove_path(
                    str(folder),
                    self._config(),
                    purpose="test_known_remove_size",
                    recursive=True,
                    estimated_bytes=5,
                )

            self.assertEqual(5, result.bytes_estimated)
            estimate.assert_not_called()

    async def test_storage_snapshot_redacts_paths(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "old.mkv"
            target.write_bytes(b"old")

            await remove_path(str(target), self._config(), purpose="test_snapshot")

            snapshot = storage_operation_snapshot(redact_paths=True)
            self.assertEqual(1, snapshot["history_size"])
            recent = snapshot["recent"][0]
            self.assertEqual("remove", recent["operation"])
            self.assertNotEqual(str(target), recent["source_path"])
            self.assertTrue(str(recent["source_path"]).endswith("old.mkv"))

    async def test_failed_storage_operation_is_recorded(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "download"
            folder.mkdir()

            with self.assertRaises(IsADirectoryError):
                await remove_path(str(folder), self._config(), purpose="test_failed_nonrecursive")

            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("remove:failed"))
            snapshot = storage_operation_snapshot()
            self.assertEqual("failed", snapshot["recent"][0]["status"])
            self.assertIn("non-recursive", snapshot["recent"][0]["error"])

    async def test_recent_storage_failures_are_time_bounded(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "download"
            folder.mkdir()

            with self.assertRaises(IsADirectoryError):
                await remove_path(str(folder), self._config(), purpose="test_stale_failure")

            self.assertEqual(1, len(recent_storage_failures(seconds=60)))

            import backend.core.storage as storage

            storage._operation_history[0]["completed_at"] = "2000-01-01T00:00:00+00:00"
            snapshot = storage_operation_snapshot()

            self.assertEqual(0, len(recent_storage_failures(seconds=60)))
            self.assertEqual(0, len(snapshot["recent_failures"]))
            self.assertEqual(1, snapshot["history_size"])

    async def test_nas_write_budget_blocks_move(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            nas_dir = Path(temp_dir) / "nas"
            target = nas_dir / "target.mkv"
            source.write_bytes(b"movie")
            nas_dir.mkdir()
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0.000000001,
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                )
            )

            with (
                patch("backend.core.storage._same_storage_device", return_value=False),
                patch(
                    "backend.core.storage._persisted_nas_usage_24h",
                    AsyncMock(return_value=(0, 0)),
                ),
                self.assertRaises(OSError),
            ):
                await move_path(str(source), str(target), cfg, purpose="place_replacement")

            self.assertTrue(source.exists())
            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("move:failed"))
            self.assertEqual(1, metrics.get("nas:write_budget_blocked"))

    async def test_same_device_rename_is_not_charged_against_the_nas_write_budget(self):
        # Regression for a same-directory rename (backup_existing_target's
        # "<file>.slimarr-old" step) being billed at full file size even
        # though a same-device os.rename() moves zero bytes - this could
        # exhaust the whole daily write budget on phantom writes alone and
        # fail every genuine replacement behind it (reported as a GitHub
        # issue against a real production instance).
        with TemporaryDirectory() as temp_dir:
            nas_dir = Path(temp_dir) / "nas"
            nas_dir.mkdir()
            source = nas_dir / "movie.mkv"
            target = nas_dir / "movie.mkv.slimarr-old"
            source.write_bytes(b"x" * 1000)
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0.000000001,  # ~1 byte - any charged write blocks
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                )
            )

            with patch(
                "backend.core.storage._persisted_nas_usage_24h",
                AsyncMock(return_value=(0, 0)),
            ):
                # source and target are both real paths under the same temp
                # dir, so _same_storage_device() returns its real (True)
                # answer here rather than being mocked - this exercises the
                # actual fix, not just a mocked stand-in for it.
                result = await move_path(str(source), str(target), cfg, purpose="backup_existing_target")

            self.assertEqual("completed", result.status)
            self.assertEqual(0, storage_operation_metrics().get("nas:write_budget_blocked", 0))

    async def test_nas_replacement_budget_counts_recent_replacements(self):
        with TemporaryDirectory() as temp_dir:
            nas_dir = Path(temp_dir) / "nas"
            nas_dir.mkdir()
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=1,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                )
            )

            first_source = Path(temp_dir) / "first.mkv"
            second_source = Path(temp_dir) / "second.mkv"
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")

            with (
                patch("backend.core.storage._same_storage_device", return_value=False),
                patch(
                    "backend.core.storage._persisted_nas_usage_24h",
                    AsyncMock(return_value=(0, 0)),
                ),
            ):
                await move_path(str(first_source), str(nas_dir / "first.mkv"), cfg, purpose="place_replacement")
                with self.assertRaises(OSError):
                    await move_path(str(second_source), str(nas_dir / "second.mkv"), cfg, purpose="place_replacement")

            policy = nas_policy_snapshot()
            self.assertEqual(1, policy["replacements_24h"])
            self.assertEqual(1, storage_operation_metrics().get("nas:replacement_budget_blocked"))

    async def test_nas_replacement_budget_survives_process_memory_reset(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{db_path}",
                connect_args={"check_same_thread": False},
            )
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            nas_dir = Path(temp_dir) / "nas"
            nas_dir.mkdir()
            source = Path(temp_dir) / "source.mkv"
            source.write_bytes(b"second")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            async with maker() as session:
                session.add(
                    StorageOperationLog(
                        operation_type="move",
                        purpose="place_replacement",
                        source_path=str(Path(temp_dir) / "old-source.mkv"),
                        target_path=str(nas_dir / "old-target.mkv"),
                        source_classification="local",
                        target_classification="nas",
                        estimated_bytes=5,
                        actual_bytes=5,
                        status="completed",
                        started_at=now,
                        completed_at=now,
                        created_at=now,
                    )
                )
                await session.commit()

            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=1,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=0,
                )
            )

            try:
                reset_storage_operation_telemetry()
                with (
                    patch("backend.database.async_session", maker),
                    patch("backend.core.storage._same_storage_device", return_value=False),
                ):
                    with self.assertRaises(OSError):
                        await move_path(
                            str(source),
                            str(nas_dir / "new-target.mkv"),
                            cfg,
                            purpose="place_replacement",
                        )
                self.assertTrue(source.exists())
                self.assertEqual(
                    1,
                    storage_operation_metrics().get("nas:replacement_budget_blocked"),
                )
            finally:
                await engine.dispose()

    async def test_nas_failure_starts_cooldown(self):
        with TemporaryDirectory() as temp_dir:
            nas_dir = Path(temp_dir) / "nas"
            folder = nas_dir / "folder"
            later = nas_dir / "later.mkv"
            folder.mkdir(parents=True)
            later.write_bytes(b"later")
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=1,
                )
            )

            with self.assertRaises(IsADirectoryError):
                await remove_path(str(folder), cfg, purpose="nas_delete_failure")
            with self.assertRaises(OSError):
                await remove_path(str(later), cfg, purpose="nas_delete_during_cooldown")

            policy = nas_policy_snapshot()
            self.assertTrue(policy["cooldown_active"])
            self.assertGreater(policy["cooldown_remaining_seconds"], 0)
            metrics = storage_operation_metrics()
            self.assertEqual(1, metrics.get("nas:cooldowns_started"))
            self.assertEqual(1, metrics.get("nas:cooldown_blocked"))

    async def test_storage_operation_is_persisted_when_db_available(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            source = Path(temp_dir) / "source.mkv"
            target = Path(temp_dir) / "target.mkv"
            source.write_bytes(b"persisted")

            try:
                with patch("backend.database.async_session", maker):
                    await move_path(str(source), str(target), self._config(), purpose="test_persist_move")
                    async with maker() as session:
                        rows = (
                            await session.execute(
                                select(StorageOperationLog).where(
                                    StorageOperationLog.purpose == "test_persist_move"
                                )
                            )
                        ).scalars().all()
                    persisted = await persisted_storage_operation_snapshot(limit=5)

                self.assertEqual(1, len(rows))
                self.assertEqual("completed", rows[0].status)
                self.assertEqual("move", rows[0].operation_type)
                self.assertTrue(persisted["available"])
                self.assertGreaterEqual(persisted["history_size"], 1)
                self.assertEqual("test_persist_move", persisted["recent"][0]["purpose"])
            finally:
                await engine.dispose()

    async def test_nas_path_health_is_persisted_for_failed_nas_operation(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            nas_dir = Path(temp_dir) / "nas"
            folder = nas_dir / "folder"
            folder.mkdir(parents=True)
            cfg = SimpleNamespace(
                files=SimpleNamespace(
                    nas_path_prefixes=[str(nas_dir)],
                    recycling_bin="",
                    nas_max_write_gb_per_day=0,
                    nas_max_replacements_per_day=0,
                    nas_max_concurrent_operations=1,
                    nas_failure_cooldown_minutes=1,
                )
            )

            try:
                with patch("backend.database.async_session", maker):
                    with self.assertRaises(IsADirectoryError):
                        await remove_path(str(folder), cfg, purpose="test_persist_nas_failure")
                    async with maker() as session:
                        health_rows = (
                            await session.execute(select(StoragePathHealth))
                        ).scalars().all()

                self.assertEqual(1, len(health_rows))
                self.assertEqual(str(folder), health_rows[0].path_prefix)
                self.assertEqual("nas", health_rows[0].classification)
                self.assertEqual(1, health_rows[0].failure_count)
                self.assertIsNotNone(health_rows[0].last_failure_at)
                self.assertIsNotNone(health_rows[0].cooldown_until)
            finally:
                await engine.dispose()

    async def test_restore_nas_cooldown_state_rearms_an_active_persisted_cooldown(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
            async with maker() as session:
                session.add(
                    StoragePathHealth(
                        path_prefix="/mnt/nas/movies",
                        classification="nas",
                        cooldown_until=future,
                        last_error_message="disk full",
                    )
                )
                await session.commit()

            try:
                with patch("backend.database.async_session", maker):
                    await restore_nas_cooldown_state()

                snapshot = nas_policy_snapshot()
                self.assertTrue(snapshot["cooldown_active"])
                self.assertGreater(snapshot["cooldown_remaining_seconds"], 0)
                self.assertLessEqual(snapshot["cooldown_remaining_seconds"], 300)
                self.assertEqual("/mnt/nas/movies", snapshot["last_failure"]["path"])
            finally:
                reset_storage_operation_telemetry()
                await engine.dispose()

    async def test_restore_nas_cooldown_state_ignores_an_expired_cooldown(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
            async with maker() as session:
                session.add(
                    StoragePathHealth(path_prefix="/mnt/nas/movies", classification="nas", cooldown_until=past)
                )
                await session.commit()

            try:
                with patch("backend.database.async_session", maker):
                    await restore_nas_cooldown_state()

                self.assertFalse(nas_policy_snapshot()["cooldown_active"])
            finally:
                reset_storage_operation_telemetry()
                await engine.dispose()

    async def test_restore_nas_cooldown_state_is_a_noop_with_no_health_rows(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "storage.sqlite"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False})
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            try:
                with patch("backend.database.async_session", maker):
                    await restore_nas_cooldown_state()

                self.assertFalse(nas_policy_snapshot()["cooldown_active"])
            finally:
                reset_storage_operation_telemetry()
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
