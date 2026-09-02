"""Recommendation refresh orchestration — sourcing → correlation → streaming →
scoring → persistence. This is the only module in the package that touches
the database; everything it calls into (scoring, sourcing, correlation,
streaming) is either pure or takes its dependencies as parameters, so this
module is the one place that needs integration-style tests with a real
(temp) database.

Entry point: run_recommendation_refresh(), registered as the
"recommendation_refresh" job kind in core/jobs.py so it gets the existing
durable-job machinery (heartbeat, singleton-per-kind, resumability, cancel)
for free — see docs/RECOMMENDATION_ARCHITECTURE.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.recommendations.correlation import (
    CorrelationSnapshot,
    build_correlation_snapshot,
    is_managed_in_radarr,
    is_managed_in_sonarr,
)
from backend.core.recommendations.scoring import CandidateSignals, score_candidate
from backend.core.recommendations.sourcing import SourcedCandidate, source_candidates_for_owned_movie
from backend.core.recommendations.streaming import fetch_availability
from backend.database import (
    Movie,
    Recommendation,
    RecommendationCandidate,
    RecommendationFeedback,
    RecommendationReason,
    StreamingAvailability,
    async_session,
)
from backend.integrations.tmdb import TMDBClient, TMDBError

# Recommendations already dismissed/hidden/actioned/watchlisted/marked-owned
# are never silently overwritten by a later refresh — a fresh scan
# re-surfacing a title the user explicitly dismissed would be exactly the
# kind of "the app ignores what I told it" behavior this feature must not
# have. already_available/already_managed are included because
# mark_owned_recommendation() (an explicit user action) sets
# already_available - without protecting it, the next refresh's correlation
# check (which can't see e.g. a physical-media copy or a library Slimarr
# doesn't scan) would flip it straight back to "active", undoing the user's
# action. If a title is later genuinely removed from the library, dismissing
# it directly resets it - refresh is not the mechanism for that.
_PROTECTED_STATES = {"dismissed", "hidden", "watchlisted", "actioned", "already_available", "already_managed"}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _excluded_genre(candidate_genres: tuple[str, ...], exclude: list[str]) -> str | None:
    for genre in candidate_genres:
        if genre in exclude:
            return genre
    return None


def _matched_genres(candidate_genres: tuple[str, ...], include: list[str]) -> tuple[str, ...]:
    return tuple(g for g in candidate_genres if g in include) if include else ()


def _keyword_blocked(title: str, overview: str | None, excluded_keywords: list[str]) -> str | None:
    haystack = f"{title} {overview or ''}".lower()
    for keyword in excluded_keywords:
        if keyword.strip() and keyword.strip().lower() in haystack:
            return keyword
    return None


async def _get_or_create_candidate(
    db, sourced: SourcedCandidate, *, imdb_id: str | None = None,
) -> RecommendationCandidate:
    existing = (
        await db.execute(
            select(RecommendationCandidate).where(
                RecommendationCandidate.media_type == sourced.media_type,
                RecommendationCandidate.tmdb_id == sourced.tmdb_id,
            )
        )
    ).scalar_one_or_none()

    now = _utc_now_naive()
    if existing is None:
        existing = RecommendationCandidate(
            media_type=sourced.media_type,
            tmdb_id=sourced.tmdb_id,
            imdb_id=imdb_id,
            title=sourced.title,
            year=sourced.year,
            poster_path=sourced.poster_path,
            backdrop_path=sourced.backdrop_path,
            overview=sourced.overview,
            popularity=sourced.popularity,
            vote_average=sourced.vote_average,
            genres=json.dumps(list(sourced.genres)) if sourced.genres else None,
            first_seen_at=now,
            last_refreshed_at=now,
        )
        db.add(existing)
        await db.flush()
    else:
        existing.imdb_id = imdb_id or existing.imdb_id
        existing.title = sourced.title
        existing.year = sourced.year
        existing.poster_path = sourced.poster_path or existing.poster_path
        existing.backdrop_path = sourced.backdrop_path or existing.backdrop_path
        existing.overview = sourced.overview or existing.overview
        existing.popularity = sourced.popularity
        existing.vote_average = sourced.vote_average
        if sourced.genres:
            existing.genres = json.dumps(list(sourced.genres))
        existing.last_refreshed_at = now

    return existing


async def _upsert_availability(db, candidate: RecommendationCandidate, entries) -> None:
    for entry in entries:
        existing = (
            await db.execute(
                select(StreamingAvailability).where(
                    StreamingAvailability.candidate_id == candidate.id,
                    StreamingAvailability.region == entry.region,
                    StreamingAvailability.provider_id == entry.provider_id,
                    StreamingAvailability.availability_type == entry.availability_type,
                )
            )
        ).scalar_one_or_none()
        checked_at = entry.checked_at.replace(tzinfo=None)
        expires_at = entry.expires_at.replace(tzinfo=None)
        if existing is None:
            db.add(StreamingAvailability(
                candidate_id=candidate.id,
                region=entry.region,
                provider_id=entry.provider_id,
                provider_name=entry.provider_name,
                display_priority=entry.display_priority,
                availability_type=entry.availability_type,
                source=entry.source,
                source_url=entry.source_url,
                checked_at=checked_at,
                expires_at=expires_at,
            ))
        else:
            existing.provider_name = entry.provider_name
            existing.display_priority = entry.display_priority
            existing.checked_at = checked_at
            existing.expires_at = expires_at


async def _upsert_recommendation(
    db, candidate: RecommendationCandidate, category: str, scored,
) -> str:
    """Returns one of: "created" | "updated" | "skipped_protected" |
    "skipped_excluded" | "already_available" | "already_managed". The latter
    two are returned distinctly from "skipped_excluded" even though a row IS
    persisted for them, so refresh-summary counters don't conflate "nothing
    was touched" with "a row was written but isn't actionable".

    scored.state == "excluded" (blocked keyword/person/genre, disabled media
    type) is a config-level filter, not a per-title state worth its own audit
    trail the way dismiss/hide are — no Recommendation row is created or
    touched for it. already_available/already_managed ARE part of the
    documented state vocabulary and are persisted so the UI can show "why
    isn't this suggested" transparently.
    """
    existing = (
        await db.execute(
            select(Recommendation).where(
                Recommendation.candidate_id == candidate.id,
                Recommendation.category == category,
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.state in _PROTECTED_STATES:
        return "skipped_protected"

    if scored.state == "excluded":
        return "skipped_excluded"

    if scored.state in {"already_available", "already_managed"}:
        if existing is None:
            existing = Recommendation(candidate_id=candidate.id, category=category)
            db.add(existing)
            await db.flush()
        existing.state = scored.state
        existing.score = scored.score
        await _replace_reasons(db, existing, scored.reasons)
        return scored.state

    if existing is None:
        existing = Recommendation(candidate_id=candidate.id, category=category, state="active")
        db.add(existing)
        await db.flush()
        existing.score = scored.score
        await _replace_reasons(db, existing, scored.reasons)
        return "created"

    existing.score = scored.score
    existing.state = "active"
    await _replace_reasons(db, existing, scored.reasons)
    return "updated"


async def _expire_if_below_threshold(db, media_type: str, tmdb_id: int, category: str) -> bool:
    """A candidate that no longer clears minimum_score (popularity dropped,
    config filters tightened, etc.) must not leave a previously-persisted
    "active" Recommendation frozen at its old score forever - retention only
    prunes by count, not by "does this still qualify", so nothing else would
    ever catch a stale row here. Expires it instead of leaving it untouched.
    Never touches a protected state - dismissing/hiding/watchlisting is still
    the user's call, not something a score drop should override.

    Returns True if a row was found and expired (for summary counting).
    """
    candidate = (
        await db.execute(
            select(RecommendationCandidate).where(
                RecommendationCandidate.media_type == media_type,
                RecommendationCandidate.tmdb_id == tmdb_id,
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        return False

    existing = (
        await db.execute(
            select(Recommendation).where(
                Recommendation.candidate_id == candidate.id,
                Recommendation.category == category,
            )
        )
    ).scalar_one_or_none()
    if existing is None or existing.state in _PROTECTED_STATES or existing.state == "expired":
        return False

    existing.state = "expired"
    return True


async def _replace_reasons(db, recommendation: Recommendation, reasons) -> None:
    existing_reasons = (
        await db.execute(select(RecommendationReason).where(RecommendationReason.recommendation_id == recommendation.id))
    ).scalars().all()
    for r in existing_reasons:
        await db.delete(r)
    await db.flush()
    for reason in reasons:
        db.add(RecommendationReason(
            recommendation_id=recommendation.id,
            reason_code=reason.reason_code,
            explanation=reason.explanation,
            source_movie_id=reason.source_movie_id,
            source_provider=reason.source_provider,
            weight=reason.weight,
        ))


def _build_signals(
    sourced: SourcedCandidate,
    *,
    snapshot: CorrelationSnapshot,
    imdb_id: str | None,
    rec_config,
    availability,
) -> CandidateSignals:
    blocked_keyword = _keyword_blocked(sourced.title, sourced.overview, rec_config.excluded_keywords)
    excluded_genre = _excluded_genre(sourced.genres, rec_config.genres_exclude)
    genre_matches = _matched_genres(sourced.genres, rec_config.genres_include)

    provider_names = tuple(
        e.provider_name for e in availability
        if not rec_config.subscribed_providers or e.provider_id in rec_config.subscribed_providers
    )
    # Only meaningful when a region IS configured and we actually looked up
    # availability but found none of the user's subscribed providers there —
    # not simply "we never checked" (region blank) or "user has no
    # subscribed-provider filter configured".
    checked_but_unavailable = (
        bool(rec_config.region) and bool(rec_config.subscribed_providers) and not provider_names
    )

    return CandidateSignals(
        media_type=sourced.media_type,
        popularity=sourced.popularity,
        vote_average=sourced.vote_average,
        release_year=sourced.year,
        collection_name=sourced.collection_name,
        collection_owned_count=sourced.collection_owned_count,
        collection_total_count=sourced.collection_total_count,
        is_sequel_or_prequel=sourced.is_sequel or sourced.is_prequel,
        sequel_source_title=sourced.related_to_title,
        sequel_source_movie_id=sourced.related_to_movie_id,
        related_source_titles=(sourced.related_to_title,) if sourced.category == "related_title" and sourced.related_to_title else (),
        genre_matches=genre_matches,
        available_on_subscribed_provider=bool(provider_names),
        available_provider_names=provider_names,
        already_managed_radarr=(
            is_managed_in_radarr(snapshot, imdb_id=imdb_id) if sourced.media_type == "movie" else False
        ),
        already_managed_sonarr=(
            is_managed_in_sonarr(snapshot, title=sourced.title) if sourced.media_type == "tv" else False
        ),
        blocked_keyword_match=blocked_keyword,
        excluded_genre_match=excluded_genre,
        unsupported_media_type=sourced.media_type not in rec_config.media_types,
        outside_language_preference=False,  # language data not available from collection/related listings in this increment
        unavailable_in_configured_region=checked_but_unavailable,
    )


async def run_recommendation_refresh(*, max_movies: int = 200) -> dict:
    from backend.config import get_config

    config = get_config()
    rec_config = config.recommendations
    summary = {
        "status": "ok",
        "movies_scanned": 0,
        "candidates_sourced": 0,
        "created": 0,
        "updated": 0,
        "skipped_excluded": 0,
        "skipped_protected": 0,
        "already_available": 0,
        "already_managed": 0,
        "expired_below_threshold": 0,
        "errors": 0,
    }

    if not rec_config.enabled:
        summary["status"] = "disabled"
        return summary

    tmdb = TMDBClient()
    snapshot = await build_correlation_snapshot(config)
    try:
        genre_map = await tmdb.get_genre_map()
    except Exception as exc:  # genre filtering is an optional signal, not required for a refresh to proceed
        logger.warning("Recommendation refresh: genre map fetch failed, genre filtering disabled this run: {}", exc)
        genre_map = {}

    async with async_session() as db:
        movies = (
            await db.execute(
                select(Movie.id, Movie.title, Movie.year, Movie.tmdb_id)
                .where(Movie.tmdb_id.is_not(None))
                .order_by(Movie.id)
                .limit(max_movies)
            )
        ).all()

    summary["movies_scanned"] = len(movies)

    collection_cache: dict[int, dict] = {}
    sourced_by_tmdb_id: dict[int, list[SourcedCandidate]] = {}

    for movie_id, title, year, tmdb_id in movies:
        try:
            candidates = await source_candidates_for_owned_movie(
                movie_id=movie_id, movie_title=title, movie_year=year, tmdb_id=tmdb_id,
                tmdb=tmdb, snapshot=snapshot, collection_cache=collection_cache, genre_map=genre_map,
            )
        except Exception as exc:  # sourcing failures for one movie must not abort the whole refresh
            logger.warning("Recommendation sourcing failed for movie_id={}: {}", movie_id, exc)
            summary["errors"] += 1
            continue
        for candidate in candidates:
            if candidate.category not in rec_config.enabled_categories:
                continue
            sourced_by_tmdb_id.setdefault(candidate.tmdb_id, []).append(candidate)

    # A tmdb_id can be sourced multiple times (two owned movies in the same
    # collection both point at the same missing sequel, or the same related
    # title surfaces from two different seeds). Prefer collection_completion
    # (a stronger, more specific signal) over related_title for the same
    # underlying title, and only ever create one Recommendation category per
    # candidate per refresh run.
    merged: dict[int, SourcedCandidate] = {}
    for tmdb_id, entries in sourced_by_tmdb_id.items():
        collection_entries = [e for e in entries if e.category == "collection_completion"]
        merged[tmdb_id] = collection_entries[0] if collection_entries else entries[0]

    summary["candidates_sourced"] = len(merged)

    for tmdb_id, sourced in merged.items():
        try:
            # Pre-filter score (no Radarr/Sonarr/streaming signals yet) decides
            # whether this candidate is even worth the extra TMDB calls below —
            # bounds external_ids/watch-providers traffic to titles that would
            # actually be surfaced, not every sourced candidate.
            preliminary_signals = _build_signals(
                sourced, snapshot=snapshot, imdb_id=None, rec_config=rec_config, availability=[],
            )
            preliminary = score_candidate(preliminary_signals)
            if preliminary.state == "active" and preliminary.score < rec_config.minimum_score:
                async with async_session() as db:
                    if await _expire_if_below_threshold(db, sourced.media_type, tmdb_id, sourced.category):
                        summary["expired_below_threshold"] += 1
                        await db.commit()
                continue
            if preliminary.state != "active":
                # Hard-excluded already (blocked keyword, unsupported media
                # type, genre exclusion) — no need for further API calls.
                async with async_session() as db:
                    candidate_row = await _get_or_create_candidate(db, sourced)
                    outcome = await _upsert_recommendation(db, candidate_row, sourced.category, preliminary)
                    summary[outcome] += 1
                    await db.commit()
                continue

            imdb_id: str | None = None
            try:
                external_ids = await tmdb.get_external_ids(tmdb_id, media_type=sourced.media_type)
                imdb_id = external_ids.get("imdb_id")
            except TMDBError as exc:
                logger.debug("external_ids lookup failed for tmdb_id={}: {}", tmdb_id, exc)

            availability = []
            if rec_config.region:
                availability = await fetch_availability(
                    tmdb=tmdb, tmdb_id=tmdb_id, media_type=sourced.media_type, region=rec_config.region,
                )

            final_signals = _build_signals(
                sourced, snapshot=snapshot, imdb_id=imdb_id, rec_config=rec_config, availability=availability,
            )
            final = score_candidate(final_signals)

            async with async_session() as db:
                candidate_row = await _get_or_create_candidate(db, sourced, imdb_id=imdb_id)
                if availability:
                    await _upsert_availability(db, candidate_row, availability)
                if final.state == "active" and final.score < rec_config.minimum_score:
                    if await _expire_if_below_threshold(db, sourced.media_type, tmdb_id, sourced.category):
                        summary["expired_below_threshold"] += 1
                    else:
                        summary["skipped_excluded"] += 1
                else:
                    outcome = await _upsert_recommendation(db, candidate_row, sourced.category, final)
                    summary[outcome] += 1
                await db.commit()

        except Exception as exc:
            logger.warning("Recommendation persistence failed for tmdb_id={}: {}", tmdb_id, exc)
            summary["errors"] += 1

    await _apply_retention(rec_config.max_recommendations_retained)
    return summary


async def _apply_retention(max_retained: int) -> None:
    """Expire the lowest-scored active recommendations beyond the retained
    cap. Never touches dismissed/hidden/watchlisted/actioned rows."""
    async with async_session() as db:
        active = (
            await db.execute(
                select(Recommendation)
                .where(Recommendation.state == "active")
                .order_by(Recommendation.score.desc())
            )
        ).scalars().all()
        if len(active) <= max_retained:
            return
        now = _utc_now_naive()
        for rec in active[max_retained:]:
            rec.state = "expired"
            rec.expires_at = now
        await db.commit()


async def record_feedback(recommendation_id: int, action: str, detail: dict | None = None) -> bool:
    """Append-only audit trail — see RecommendationFeedback in
    docs/RECOMMENDATION_ARCHITECTURE.md. Returns False if the recommendation
    doesn't exist."""
    async with async_session() as db:
        recommendation = await db.get(Recommendation, recommendation_id)
        if recommendation is None:
            return False
        db.add(RecommendationFeedback(
            recommendation_id=recommendation_id,
            action=action,
            detail=json.dumps(detail) if detail else None,
        ))
        await db.commit()
        return True
