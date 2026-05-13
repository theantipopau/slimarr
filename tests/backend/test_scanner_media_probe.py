import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.core.scanner import _run_scan


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self):
        self.added = []
        self._commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _Result(None)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self._commits += 1


class _SessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        session = _FakeSession()
        self.sessions.append(session)
        return session


class ScannerMediaProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_scanner_applies_probe_values_when_plex_metadata_missing(self):
        cfg = SimpleNamespace(
            plex=SimpleNamespace(url="http://plex", token="token", library_sections=[]),
            tmdb=SimpleNamespace(api_key=""),
            radarr=SimpleNamespace(enabled=False),
        )
        plex_movies = [
            {
                "plex_rating_key": "abc123",
                "title": "Probe Movie",
                "year": 2024,
                "imdb_id": "tt1234567",
                "tmdb_id": None,
                "file_path": "F:/media/Probe.Movie.2024.mkv",
                "file_size": 1_000_000_000,
                "resolution": "",
                "video_codec": "",
                "audio_codec": "",
                "bitrate": 0,
            }
        ]

        session_factory = _SessionFactory()
        probe_result = {
            "resolution": "1080p",
            "video_codec": "h265",
            "audio_codec": "eac3",
            "bitrate_kbps": 3200,
        }

        with patch("backend.config.get_config", return_value=cfg), patch(
            "backend.core.scanner.async_session", session_factory
        ), patch("backend.core.scanner.emit_event", AsyncMock()), patch(
            "backend.core.scanner.asyncio.to_thread", AsyncMock(return_value=probe_result)
        ) as to_thread, patch(
            "backend.integrations.plex.PlexClient.get_all_movies", return_value=plex_movies
        ), patch(
            "backend.integrations.tmdb.TMDBClient"
        ):
            processed = await _run_scan()

        self.assertEqual(1, processed)
        to_thread.assert_awaited_once()

        # The write session is the second one per movie.
        written = session_factory.sessions[1].added[0]
        self.assertEqual("1080p", written.resolution)
        self.assertEqual("h265", written.video_codec)
        self.assertEqual("eac3", written.audio_codec)
        self.assertEqual(3200, written.bitrate)


if __name__ == "__main__":
    unittest.main()
