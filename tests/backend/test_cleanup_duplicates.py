import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.core.cleanup import scan_and_clean_duplicates


class FakePart:
    def __init__(self, file: str, size: int):
        self.file = file
        self.size = size


class FakeMedia:
    def __init__(self, part: FakePart, resolution: str, codec: str):
        self.parts = [part]
        self.videoResolution = resolution
        self.videoCodec = codec


class FakeMovie:
    def __init__(self, title: str, rating_key: int, media: list[FakeMedia]):
        self.title = title
        self.ratingKey = rating_key
        self.media = media


class FakeSection:
    def __init__(self, movies: list[FakeMovie]):
        self._movies = movies
        self.type = "movie"
        self.title = "Movies"

    def all(self):
        return self._movies

    def update(self):
        pass


class FakeLibrary:
    def __init__(self, section: FakeSection):
        self._section = section

    def sections(self):
        return [self._section]

    def section(self, name):
        return self._section


class FakeServer:
    def __init__(self, section: FakeSection):
        self.library = FakeLibrary(section)


class FakePlexClient:
    def __init__(self, server: FakeServer):
        self._server = server
        self.library_sections = ["Movies"]

    def _get_server(self):
        return self._server


class DuplicateCleanupTests(unittest.IsolatedAsyncioTestCase):
    def _config(self, recycling_bin: str = "") -> SimpleNamespace:
        return SimpleNamespace(
            plex=SimpleNamespace(url="http://plex.local", token="tok"),
            files=SimpleNamespace(
                recycling_bin=recycling_bin,
                nas_path_prefixes=[],
                nas_max_write_gb_per_day=0,
                nas_max_replacements_per_day=0,
                nas_max_concurrent_operations=1,
                nas_failure_cooldown_minutes=0,
            ),
        )

    async def test_deletes_inferior_duplicate_when_no_recycling_bin_configured(self):
        with TemporaryDirectory() as temp_dir:
            best = Path(temp_dir) / "movie.1080p.mkv"
            inferior = Path(temp_dir) / "movie.720p.mkv"
            best.write_bytes(b"x" * 100)
            inferior.write_bytes(b"x" * 50)

            movie = FakeMovie(
                "Some Movie",
                1,
                [
                    FakeMedia(FakePart(str(best), 100), "1080", "h265"),
                    FakeMedia(FakePart(str(inferior), 50), "720", "h264"),
                ],
            )
            server = FakeServer(FakeSection([movie]))

            with (
                patch("backend.core.cleanup.get_config", return_value=self._config()),
                patch("backend.integrations.plex.PlexClient", return_value=FakePlexClient(server)),
            ):
                summary = await scan_and_clean_duplicates()

            self.assertEqual(1, summary["duplicates_found"])
            self.assertEqual(1, summary["files_removed"])
            self.assertEqual(0, summary["errors"])
            self.assertTrue(best.exists())
            self.assertFalse(inferior.exists())

    async def test_recycles_inferior_duplicate_when_recycling_bin_configured(self):
        with TemporaryDirectory() as temp_dir:
            best = Path(temp_dir) / "movie.1080p.mkv"
            inferior = Path(temp_dir) / "movie.720p.mkv"
            recycle_dir = Path(temp_dir) / "recycle"
            best.write_bytes(b"x" * 100)
            inferior.write_bytes(b"x" * 50)

            movie = FakeMovie(
                "Some Movie",
                2,
                [
                    FakeMedia(FakePart(str(best), 100), "1080", "h265"),
                    FakeMedia(FakePart(str(inferior), 50), "720", "h264"),
                ],
            )
            server = FakeServer(FakeSection([movie]))

            with (
                patch("backend.core.cleanup.get_config", return_value=self._config(str(recycle_dir))),
                patch("backend.integrations.plex.PlexClient", return_value=FakePlexClient(server)),
            ):
                summary = await scan_and_clean_duplicates()

            self.assertEqual(1, summary["files_removed"])
            self.assertEqual(0, summary["errors"])
            self.assertFalse(inferior.exists())
            self.assertTrue((recycle_dir / "movie.720p.mkv").exists())

    async def test_skips_deletion_when_recycling_bin_preflight_is_blocked(self):
        # An unreachable/full recycling-bin share fails preflight. Configuring
        # a recycling bin is an explicit request to never permanently delete,
        # so this must skip the file (retried on the next scan) rather than
        # fall back to a delete - that would destroy data exactly when the
        # safety net the user asked for is unavailable. The preflight result
        # is mocked directly (rather than relying on an "obviously invalid"
        # real path) because what counts as an inaccessible path is
        # platform-specific - a Windows drive letter that can't exist is a
        # perfectly normal, creatable relative path on Linux CI.
        with TemporaryDirectory() as temp_dir:
            best = Path(temp_dir) / "movie.1080p.mkv"
            inferior = Path(temp_dir) / "movie.720p.mkv"
            best.write_bytes(b"x" * 100)
            inferior.write_bytes(b"x" * 50)

            unreachable_bin = str(Path(temp_dir) / "unreachable_recycle")

            movie = FakeMovie(
                "Some Movie",
                3,
                [
                    FakeMedia(FakePart(str(best), 100), "1080", "h265"),
                    FakeMedia(FakePart(str(inferior), 50), "720", "h264"),
                ],
            )
            server = FakeServer(FakeSection([movie]))
            blocked_preflight = SimpleNamespace(status="block", messages=["NAS share unreachable"])

            with (
                patch("backend.core.cleanup.get_config", return_value=self._config(unreachable_bin)),
                patch("backend.integrations.plex.PlexClient", return_value=FakePlexClient(server)),
                patch("backend.core.cleanup.preflight_storage_path", Mock(return_value=blocked_preflight)),
            ):
                summary = await scan_and_clean_duplicates()

            self.assertEqual(0, summary["files_removed"])
            self.assertEqual(0, summary["errors"])
            self.assertTrue(best.exists())
            self.assertTrue(inferior.exists())


if __name__ == "__main__":
    unittest.main()
