"""Deterministic candidate sourcing from TMDB — no AI, no guessing.

Two real, TMDB-backed relationship signals are sourced here:

- collection_completion: TMDB's own "belongs_to_collection" + /collection/{id}
  data is the authoritative source for franchise membership (Toy Story 1-4,
  the MCU phases, etc.) — this also covers the brief's "sequel/prequel"
  category for the overwhelming majority of real cases, since a franchise
  sequel is, in practice, almost always a fellow collection member. A
  release-date comparison against the owned seed movie tags which direction
  (sequel vs. prequel) the gap is in for the reason text.
- related_title: TMDB's own "recommendations" and "similar" fields for a
  movie, already fetched by TMDBClient.get_movie_full() in the same request
  as the collection data (via append_to_response) — no extra API call.

A standalone, non-collection sequel-detection heuristic (e.g. parsing "Part
2" out of a title) is deliberately NOT implemented — it would be far less
reliable than TMDB's own curated collection data and would risk fabricating
franchise relationships the brief explicitly prohibits guessing at.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from backend.core.recommendations.correlation import CorrelationSnapshot, is_in_plex
from backend.integrations.tmdb import TMDBClient, TMDBError


@dataclass(frozen=True)
class SourcedCandidate:
    media_type: str
    tmdb_id: int
    title: str
    year: int | None
    imdb_id: str | None
    poster_path: str | None
    backdrop_path: str | None
    overview: str | None
    popularity: float | None
    vote_average: float | None
    genres: tuple[str, ...]

    category: str  # "collection_completion" | "related_title"
    collection_name: str | None = None
    collection_owned_count: int = 0
    collection_total_count: int = 0
    is_sequel: bool = False
    is_prequel: bool = False
    related_to_title: str | None = None
    related_to_movie_id: int | None = None


def _year_from_release_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _resolve_genres(genre_ids: list | None, genre_map: dict[int, str]) -> tuple[str, ...]:
    """Collection/recommendations/similar list items only carry numeric
    genre_ids, never names - resolve via a genre map fetched once per
    refresh (see TMDBClient.get_genre_map). Falls back to an empty tuple if
    the map is empty (e.g. the genre-list fetch failed) rather than raising,
    since genre filtering is an optional signal, not a required one."""
    if not genre_ids or not genre_map:
        return ()
    return tuple(genre_map[gid] for gid in genre_ids if gid in genre_map)


async def source_candidates_for_owned_movie(
    *,
    movie_id: int,
    movie_title: str,
    movie_year: int | None,
    tmdb_id: int,
    tmdb: TMDBClient,
    snapshot: CorrelationSnapshot,
    collection_cache: dict[int, dict] | None = None,
    genre_map: dict[int, str] | None = None,
    max_related: int = 5,
) -> list[SourcedCandidate]:
    """One TMDB call for the seed movie (collection + recommendations +
    similar in one request), plus at most one more for the collection
    (memoized across the whole refresh run via collection_cache, since many
    owned movies can share the same franchise collection).
    """
    collection_cache = collection_cache if collection_cache is not None else {}
    genre_map = genre_map if genre_map is not None else {}
    candidates: list[SourcedCandidate] = []

    try:
        detail = await tmdb.get_movie_full(tmdb_id)
    except TMDBError as exc:
        logger.warning("Recommendation sourcing: TMDB lookup failed for movie_id={} tmdb_id={}: {}",
                        movie_id, tmdb_id, exc)
        return []

    belongs_to = detail.get("belongs_to_collection")
    if belongs_to and belongs_to.get("id"):
        collection_id = belongs_to["id"]
        collection = collection_cache.get(collection_id)
        if collection is None:
            try:
                collection = await tmdb.get_collection(collection_id)
                collection_cache[collection_id] = collection
            except TMDBError as exc:
                logger.warning("Recommendation sourcing: collection lookup failed for id={}: {}",
                                collection_id, exc)
                collection = {"parts": []}

        parts = collection.get("parts") or []
        total_count = len(parts)
        owned_count = sum(
            1 for p in parts if is_in_plex(snapshot, tmdb_id=p.get("id"), imdb_id=None)
        )
        for part in parts:
            part_tmdb_id = part.get("id")
            if not part_tmdb_id or part_tmdb_id == tmdb_id:
                continue
            if is_in_plex(snapshot, tmdb_id=part_tmdb_id, imdb_id=None):
                continue
            part_year = _year_from_release_date(part.get("release_date"))
            candidates.append(SourcedCandidate(
                media_type="movie",
                tmdb_id=part_tmdb_id,
                title=part.get("title") or "Unknown",
                year=part_year,
                imdb_id=None,  # collection parts don't include imdb_id; resolved later if needed
                poster_path=part.get("poster_path"),
                backdrop_path=part.get("backdrop_path"),
                overview=part.get("overview"),
                popularity=part.get("popularity"),
                vote_average=part.get("vote_average"),
                genres=_resolve_genres(part.get("genre_ids"), genre_map),
                category="collection_completion",
                collection_name=collection.get("name") or belongs_to.get("name"),
                collection_owned_count=owned_count,
                collection_total_count=total_count,
                is_sequel=bool(part_year and movie_year and part_year > movie_year),
                is_prequel=bool(part_year and movie_year and part_year < movie_year),
            ))

    related_seen: set[int] = set()
    for bucket in ("recommendations", "similar"):
        results = ((detail.get(bucket) or {}).get("results")) or []
        for item in results[:max_related]:
            related_tmdb_id = item.get("id")
            if not related_tmdb_id or related_tmdb_id in related_seen:
                continue
            if is_in_plex(snapshot, tmdb_id=related_tmdb_id, imdb_id=None):
                continue
            related_seen.add(related_tmdb_id)
            candidates.append(SourcedCandidate(
                media_type="movie",
                tmdb_id=related_tmdb_id,
                title=item.get("title") or "Unknown",
                year=_year_from_release_date(item.get("release_date")),
                imdb_id=None,
                poster_path=item.get("poster_path"),
                backdrop_path=item.get("backdrop_path"),
                overview=item.get("overview"),
                popularity=item.get("popularity"),
                vote_average=item.get("vote_average"),
                genres=_resolve_genres(item.get("genre_ids"), genre_map),
                category="related_title",
                related_to_title=movie_title,
                related_to_movie_id=movie_id,
            ))

    return candidates
