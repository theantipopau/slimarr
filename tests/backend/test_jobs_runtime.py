import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core import jobs
from backend.core.jobs import (
    cancel_job,
    enqueue_job,
    get_persistent_job,
    list_persistent_jobs,
    recover_stale_jobs,
)
from backend.database import Base, JobEvent, JobRecord


class JobRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "jobs.sqlite"
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        self.maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        for task in list(jobs._running_tasks.values()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        jobs._running_tasks.clear()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_enqueue_list_and_cancel_queued_job(self):
        with patch("backend.core.jobs.async_session", self.maker):
            queued = await enqueue_job("manual_scan", start=False)
            job_id = queued["job"]["id"]

            snapshot = await list_persistent_jobs(status="active")
            cancelled = await cancel_job(job_id)
            detail = await get_persistent_job(job_id)

        self.assertTrue(queued["started"])
        self.assertEqual([job_id], [job["id"] for job in snapshot["jobs"]])
        self.assertEqual("cancelled", cancelled["status"])
        self.assertIsNotNone(detail)
        self.assertEqual("cancelled", detail["status"])
        self.assertIn("cancel_requested", [event["event"] for event in detail["events"]])

    async def test_recover_stale_jobs_marks_running_as_recovery_required(self):
        async with self.maker() as session:
            session.add(
                JobRecord(
                    id="job-running",
                    kind="manual_scan",
                    status="running",
                    payload="{}",
                )
            )
            await session.commit()

        with patch("backend.core.jobs.async_session", self.maker):
            recovered = await recover_stale_jobs()
            detail = await get_persistent_job("job-running")

        self.assertEqual(1, recovered)
        self.assertIsNotNone(detail)
        self.assertEqual("recovery_required", detail["status"])
        self.assertEqual("Process restarted while job was active", detail["error_message"])

    async def test_get_persistent_job_caps_events_to_the_most_recent(self):
        from datetime import datetime, timedelta, timezone

        async with self.maker() as session:
            session.add(JobRecord(id="job-many-events", kind="manual_scan", status="completed", payload="{}"))
            base = datetime.now(timezone.utc)
            for i in range(250):
                session.add(
                    JobEvent(
                        job_id="job-many-events",
                        event=f"event-{i}",
                        created_at=base + timedelta(seconds=i),
                    )
                )
            await session.commit()

        with patch("backend.core.jobs.async_session", self.maker):
            detail = await get_persistent_job("job-many-events")

        events = detail["events"]
        self.assertEqual(200, len(events))
        # The most recent 200 (event-50 .. event-249), in chronological order.
        self.assertEqual("event-50", events[0]["event"])
        self.assertEqual("event-249", events[-1]["event"])
        indices = [int(e["event"].split("-")[1]) for e in events]
        self.assertEqual(sorted(indices), indices)

    async def test_failed_job_records_failure_event(self):
        with patch("backend.core.jobs.async_session", self.maker):
            result = await enqueue_job("unsupported_kind", start=True)
            job_id = result["job"]["id"]
            for _ in range(20):
                detail = await get_persistent_job(job_id)
                if detail and detail["status"] == "failed":
                    break
                await asyncio.sleep(0.05)

            async with self.maker() as session:
                events = (
                    await session.execute(
                        select(JobEvent).where(JobEvent.job_id == job_id)
                    )
                ).scalars().all()

        self.assertIsNotNone(detail)
        self.assertEqual("failed", detail["status"])
        self.assertIn("Unsupported job kind", detail["error_message"])
        self.assertIn("failed", [event.event for event in events])


if __name__ == "__main__":
    unittest.main()
