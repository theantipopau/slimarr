"""Regression tests for _remove_with_retry() in replacer.py.

Context: a real production log showed a post-replacement cleanup delete
(_remove the stale old-extension file after a container-format swap_) hit a
transient Windows file lock (WinError 32, e.g. Plex or an AV scanner briefly
holding the just-created file) and gave up permanently after a single
attempt, leaving the old copy on disk forever - by the time this cleanup
step runs, the movie/download rows have already moved to their final state,
so nothing else will ever retry it. _move_with_retry already handled this
class of error for the move-into-place step; _remove_with_retry is the
delete-side counterpart, added for the same reason.
"""
import unittest
from unittest.mock import AsyncMock, patch

from backend.core import replacer


class _FakeLockError(OSError):
    def __init__(self, winerror: int):
        super().__init__(f"[WinError {winerror}] The process cannot access the file")
        self.winerror = winerror


class RemoveWithRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_transient_lock_and_eventually_succeeds(self):
        calls = {"n": 0}

        async def flaky_remove(path, config, *, purpose):
            calls["n"] += 1
            if calls["n"] < 3:
                raise _FakeLockError(32)
            return None

        with patch.object(replacer, "remove_path", flaky_remove), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await replacer._remove_with_retry("C:/movie.mkv", config=object(), purpose="delete_old_extension_after_replacement")

        self.assertEqual(3, calls["n"])

    async def test_raises_after_exhausting_attempts_on_persistent_lock(self):
        calls = {"n": 0}

        async def always_locked(path, config, *, purpose):
            calls["n"] += 1
            raise _FakeLockError(32)

        with patch.object(replacer, "remove_path", always_locked), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            with self.assertRaises(OSError):
                await replacer._remove_with_retry("C:/movie.mkv", config=object(), purpose="delete_old_extension_after_replacement", attempts=4)

        self.assertEqual(4, calls["n"])

    async def test_non_transient_error_raises_immediately_without_retry(self):
        calls = {"n": 0}

        async def permission_denied(path, config, *, purpose):
            calls["n"] += 1
            raise FileNotFoundError("no such file")

        with patch.object(replacer, "remove_path", permission_denied), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            with self.assertRaises(FileNotFoundError):
                await replacer._remove_with_retry("C:/movie.mkv", config=object(), purpose="delete_old_extension_after_replacement")

        self.assertEqual(1, calls["n"])


if __name__ == "__main__":
    unittest.main()
