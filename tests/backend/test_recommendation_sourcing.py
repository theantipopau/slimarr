import unittest
from unittest.mock import AsyncMock

from backend.core.recommendations.correlation import CorrelationSnapshot
from backend.core.recommendations.sourcing import source_candidates_for_owned_movie
from backend.integrations.tmdb import TMDBError


def _tmdb_client(get_movie_full_return=None, get_movie_full_side_effect=None, get_collection_return=None):
    client = AsyncMock()
    if get_movie_full_side_effect is not None:
        client.get_movie_full = AsyncMock(side_effect=get_movie_full_side_effect)
    else:
        client.get_movie_full = AsyncMock(return_value=get_movie_full_return or {})
    client.get_collection = AsyncMock(return_value=get_collection_return or {"parts": []})
    return client


class CollectionCompletionSourcingTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_collection_members_are_returned(self):
        detail = {
            "belongs_to_collection": {"id": 10, "name": "Toy Story Collection"},
        }
        collection = {
            "id": 10,
            "name": "Toy Story Collection",
            "parts": [
                {"id": 1, "title": "Toy Story", "release_date": "1995-11-22"},
                {"id": 2, "title": "Toy Story 2", "release_date": "1999-11-24"},
                {"id": 3, "title": "Toy Story 3", "release_date": "2010-06-18"},
            ],
        }
        tmdb = _tmdb_client(get_movie_full_return=detail, get_collection_return=collection)
        snapshot = CorrelationSnapshot(plex_tmdb_ids=frozenset({1}))  # only Toy Story 1 owned

        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Toy Story", movie_year=1995, tmdb_id=1,
            tmdb=tmdb, snapshot=snapshot,
        )

        missing_ids = {c.tmdb_id for c in candidates if c.category == "collection_completion"}
        self.assertEqual(missing_ids, {2, 3})

    async def test_owned_movie_itself_is_excluded_from_its_own_collection_results(self):
        detail = {"belongs_to_collection": {"id": 10, "name": "X"}}
        collection = {"parts": [{"id": 1, "title": "Seed"}, {"id": 2, "title": "Sequel"}]}
        tmdb = _tmdb_client(get_movie_full_return=detail, get_collection_return=collection)
        snapshot = CorrelationSnapshot()

        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Seed", movie_year=2000, tmdb_id=1, tmdb=tmdb, snapshot=snapshot,
        )
        self.assertNotIn(1, {c.tmdb_id for c in candidates})

    async def test_collection_owned_and_total_counts_are_correct(self):
        detail = {"belongs_to_collection": {"id": 10, "name": "X"}}
        collection = {
            "parts": [
                {"id": 1, "title": "A"}, {"id": 2, "title": "B"},
                {"id": 3, "title": "C"}, {"id": 4, "title": "D"},
            ],
        }
        tmdb = _tmdb_client(get_movie_full_return=detail, get_collection_return=collection)
        snapshot = CorrelationSnapshot(plex_tmdb_ids=frozenset({1, 2}))

        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="A", movie_year=2000, tmdb_id=1, tmdb=tmdb, snapshot=snapshot,
        )
        self.assertEqual(len(candidates), 2)  # 3 and 4 are missing
        for c in candidates:
            self.assertEqual(c.collection_owned_count, 2)
            self.assertEqual(c.collection_total_count, 4)

    async def test_sequel_and_prequel_direction_is_tagged_from_release_year(self):
        detail = {"belongs_to_collection": {"id": 10, "name": "X"}}
        collection = {
            "parts": [
                {"id": 1, "title": "Seed", "release_date": "2000-01-01"},
                {"id": 2, "title": "Earlier", "release_date": "1990-01-01"},
                {"id": 3, "title": "Later", "release_date": "2010-01-01"},
            ],
        }
        tmdb = _tmdb_client(get_movie_full_return=detail, get_collection_return=collection)
        snapshot = CorrelationSnapshot()

        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Seed", movie_year=2000, tmdb_id=1, tmdb=tmdb, snapshot=snapshot,
        )
        by_id = {c.tmdb_id: c for c in candidates}
        self.assertTrue(by_id[2].is_prequel)
        self.assertFalse(by_id[2].is_sequel)
        self.assertTrue(by_id[3].is_sequel)
        self.assertFalse(by_id[3].is_prequel)

    async def test_no_collection_produces_no_collection_completion_candidates(self):
        tmdb = _tmdb_client(get_movie_full_return={"belongs_to_collection": None})
        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Standalone", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(),
        )
        self.assertEqual(candidates, [])

    async def test_collection_cache_is_reused_across_calls_for_the_same_collection(self):
        detail = {"belongs_to_collection": {"id": 10, "name": "X"}}
        collection = {"parts": [{"id": 1}, {"id": 2}]}
        tmdb = _tmdb_client(get_movie_full_return=detail, get_collection_return=collection)
        cache: dict[int, dict] = {}

        await source_candidates_for_owned_movie(
            movie_id=1, movie_title="A", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(), collection_cache=cache,
        )
        await source_candidates_for_owned_movie(
            movie_id=2, movie_title="B", movie_year=2000, tmdb_id=2,
            tmdb=tmdb, snapshot=CorrelationSnapshot(), collection_cache=cache,
        )

        tmdb.get_collection.assert_awaited_once()  # second call hit the cache

    async def test_tmdb_failure_on_seed_lookup_returns_empty_list_not_an_exception(self):
        tmdb = _tmdb_client(get_movie_full_side_effect=TMDBError("boom"))
        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="A", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(),
        )
        self.assertEqual(candidates, [])


class RelatedTitleSourcingTests(unittest.IsolatedAsyncioTestCase):
    async def test_recommendations_and_similar_are_both_sourced_and_deduped(self):
        detail = {
            "recommendations": {"results": [{"id": 5, "title": "Rec A"}, {"id": 6, "title": "Rec B"}]},
            "similar": {"results": [{"id": 6, "title": "Rec B (dup)"}, {"id": 7, "title": "Sim A"}]},
        }
        tmdb = _tmdb_client(get_movie_full_return=detail)
        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Seed", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(),
        )
        ids = {c.tmdb_id for c in candidates}
        self.assertEqual(ids, {5, 6, 7})  # 6 deduped, not doubled

    async def test_related_titles_already_in_plex_are_excluded(self):
        detail = {"recommendations": {"results": [{"id": 5, "title": "Owned already"}]}}
        tmdb = _tmdb_client(get_movie_full_return=detail)
        snapshot = CorrelationSnapshot(plex_tmdb_ids=frozenset({5}))
        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Seed", movie_year=2000, tmdb_id=1, tmdb=tmdb, snapshot=snapshot,
        )
        self.assertEqual(candidates, [])

    async def test_related_titles_are_capped_at_max_related_per_bucket(self):
        results = [{"id": i, "title": f"Movie {i}"} for i in range(1, 11)]
        detail = {"recommendations": {"results": results}}
        tmdb = _tmdb_client(get_movie_full_return=detail)
        candidates = await source_candidates_for_owned_movie(
            movie_id=1, movie_title="Seed", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(), max_related=3,
        )
        self.assertEqual(len(candidates), 3)

    async def test_related_title_reason_hint_names_the_source_movie(self):
        detail = {"recommendations": {"results": [{"id": 5, "title": "Rec"}]}}
        tmdb = _tmdb_client(get_movie_full_return=detail)
        candidates = await source_candidates_for_owned_movie(
            movie_id=42, movie_title="The Source Movie", movie_year=2000, tmdb_id=1,
            tmdb=tmdb, snapshot=CorrelationSnapshot(),
        )
        self.assertEqual(candidates[0].related_to_title, "The Source Movie")
        self.assertEqual(candidates[0].related_to_movie_id, 42)


if __name__ == "__main__":
    unittest.main()
