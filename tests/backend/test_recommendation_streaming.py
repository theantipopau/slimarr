import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from backend.core.recommendations.streaming import fetch_availability, is_stale
from backend.integrations.tmdb import TMDBError


def _tmdb(return_value=None, side_effect=None):
    client = AsyncMock()
    if side_effect is not None:
        client.get_watch_providers = AsyncMock(side_effect=side_effect)
    else:
        client.get_watch_providers = AsyncMock(return_value=return_value or {"results": {}})
    return client


class FetchAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_region_never_calls_tmdb_and_returns_empty(self):
        tmdb = _tmdb()
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="")
        self.assertEqual(result, [])
        tmdb.get_watch_providers.assert_not_awaited()

    async def test_region_with_no_listed_providers_returns_empty(self):
        tmdb = _tmdb(return_value={"results": {"AU": {}}})
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        self.assertEqual(result, [])

    async def test_region_not_present_at_all_returns_empty(self):
        tmdb = _tmdb(return_value={"results": {"US": {"flatrate": [{"provider_id": 8, "provider_name": "Netflix"}]}}})
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        self.assertEqual(result, [])

    async def test_flatrate_entries_are_parsed_with_attribution_url(self):
        tmdb = _tmdb(return_value={
            "results": {"AU": {"flatrate": [
                {"provider_id": 8, "provider_name": "Netflix", "display_priority": 1},
            ]}},
        })
        result = await fetch_availability(tmdb=tmdb, tmdb_id=862, media_type="movie", region="au")
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry.provider_name, "Netflix")
        self.assertEqual(entry.availability_type, "flatrate")
        self.assertEqual(entry.region, "AU")  # normalized to uppercase
        self.assertIn("themoviedb.org", entry.source_url)
        self.assertIn("862", entry.source_url)

    async def test_multiple_availability_types_all_parsed(self):
        tmdb = _tmdb(return_value={
            "results": {"AU": {
                "flatrate": [{"provider_id": 8, "provider_name": "Netflix"}],
                "rent": [{"provider_id": 2, "provider_name": "Apple TV"}],
                "buy": [{"provider_id": 2, "provider_name": "Apple TV"}],
            }},
        })
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        types = {e.availability_type for e in result}
        self.assertEqual(types, {"flatrate", "rent", "buy"})

    async def test_entries_missing_provider_id_or_name_are_skipped(self):
        tmdb = _tmdb(return_value={
            "results": {"AU": {"flatrate": [{"provider_id": None, "provider_name": "Broken"}]}},
        })
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        self.assertEqual(result, [])

    async def test_unrecognized_availability_type_is_ignored(self):
        tmdb = _tmdb(return_value={
            "results": {"AU": {"link": "https://example.com"}},  # TMDB includes a "link" key, not an availability list
        })
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        self.assertEqual(result, [])

    async def test_tmdb_error_degrades_to_empty_list_not_an_exception(self):
        tmdb = _tmdb(side_effect=TMDBError("rate limited"))
        result = await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="movie", region="AU")
        self.assertEqual(result, [])

    async def test_tv_media_type_is_passed_through_to_the_client(self):
        tmdb = _tmdb(return_value={"results": {}})
        await fetch_availability(tmdb=tmdb, tmdb_id=1, media_type="tv", region="AU")
        tmdb.get_watch_providers.assert_awaited_once_with(1, media_type="tv")


class StalenessTests(unittest.TestCase):
    def test_fresh_checked_at_is_not_stale(self):
        self.assertFalse(is_stale(datetime.now(timezone.utc) - timedelta(hours=1)))

    def test_old_checked_at_is_stale(self):
        self.assertTrue(is_stale(datetime.now(timezone.utc) - timedelta(hours=25)))

    def test_naive_datetime_is_treated_as_utc(self):
        # Movie/candidate timestamps are stored naive-UTC elsewhere in this
        # codebase (see backend/database.py) — is_stale must handle that.
        naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertFalse(is_stale(naive_now - timedelta(hours=1)))
        self.assertTrue(is_stale(naive_now - timedelta(hours=25)))


if __name__ == "__main__":
    unittest.main()
