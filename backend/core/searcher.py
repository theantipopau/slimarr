"""
Usenet release searcher — queries indexers for a specific movie.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from loguru import logger
from sqlalchemy import select

from backend.core.comparer import compare_release
from backend.core.search_diagnostics import (
    emit_search_warning,
    normalize_exception,
    record_filter_summary,
    record_movie_search_completed,
)
from backend.core.parser import parse_release_title
from backend.database import DecisionAuditLog, Movie, SearchResult, async_session
from backend.realtime.events import emit_event

_category_warnings_seen: set[tuple[str, tuple[int, ...]]] = set()


def _nzb_age_days(raw_pub_date: str | None) -> int | None:
    if not raw_pub_date:
        return None

    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(raw_pub_date)
    except Exception:
        try:
            parsed = datetime.fromisoformat(raw_pub_date.replace("Z", "+00:00"))
        except Exception:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0, int(age.total_seconds() // 86400))


def _json_string_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        pass
    return []


async def search_for_movie(movie_id: int) -> list[dict]:
    """
    Search all configured indexers for a movie. Stores results in DB.
    Returns list of result dicts.
    """
    from backend.config import get_config
    from backend.integrations.newznab import NewznabClient
    from backend.integrations.prowlarr import ProwlarrClient

    config = get_config()

    async with async_session() as db:
        result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = result.scalar_one_or_none()
        if not movie:
            raise ValueError(f"Movie {movie_id} not found")

        await emit_event("search:started", {"movie_id": movie.id, "title": movie.title})
        logger.info(f"Searching for: {movie.title} ({movie.year})")

        all_raw: list[dict] = []
        indexer_attempts = 0
        indexer_failures = 0
        configured_sources = int(bool(config.prowlarr.enabled and config.prowlarr.url)) + len(
            [idx for idx in config.indexers if idx.name and idx.url]
        )

        if configured_sources == 0:
            logger.error(
                "Search cannot run for {}: Prowlarr is disabled/not configured and no direct indexers are configured",
                movie.title,
            )
            await emit_search_warning(
                "Search cannot run because no search providers are configured.",
                {"movie_id": movie.id, "title": movie.title},
            )

        for idx in config.indexers:
            if idx.name and idx.url and not _looks_like_movie_categories(idx.categories):
                key = (idx.name, tuple(idx.categories))
                if key not in _category_warnings_seen:
                    _category_warnings_seen.add(key)
                    logger.warning(
                        "Indexer {} categories {} do not appear to include Newznab movie categories (2000-2999)",
                        idx.name,
                        idx.categories,
                    )
                    await emit_search_warning(
                        "A direct indexer is configured without Newznab movie categories.",
                        {"indexer": idx.name, "categories": idx.categories},
                    )

        # Prowlarr path
        if config.prowlarr.enabled and config.prowlarr.url:
            indexer_attempts += 1
            try:
                prowlarr = ProwlarrClient()
                query = f"{movie.title} {movie.year}" if movie.year else movie.title
                prowlarr_results = await prowlarr.search(query=query, imdb_id=movie.imdb_id or "")
                all_raw.extend(prowlarr_results)
            except Exception as e:
                indexer_failures += 1
                logger.error(f"Prowlarr search failed: {normalize_exception(e)}")

        # Direct indexer path
        if not config.prowlarr.enabled or not all_raw:
            import asyncio

            async def _search_one(idx_cfg) -> tuple[list[dict], bool]:
                try:
                    client = NewznabClient(idx_cfg)
                    if movie.imdb_id:
                        return await client.search_by_imdb(movie.imdb_id), False
                    query = f"{movie.title} {movie.year}" if movie.year else movie.title
                    return await client.search_by_query(query), False
                except Exception as e:
                    logger.error(f"Indexer {idx_cfg.name} search failed: {normalize_exception(e)}")
                    return [], True

            direct_indexers = [idx for idx in config.indexers if idx.name and idx.url]
            indexer_attempts += len(direct_indexers)
            results_per_indexer = await asyncio.gather(*[_search_one(idx) for idx in direct_indexers])
            for r, failed in results_per_indexer:
                if failed:
                    indexer_failures += 1
                all_raw.extend(r)

        logger.info(
            "Found {} raw results for {} after {} provider attempt(s), {} failure(s)",
            len(all_raw),
            movie.title,
            indexer_attempts,
            indexer_failures,
        )

        # Remove duplicate URLs
        seen_urls: set[str] = set()
        unique_raw = []
        for r in all_raw:
            url = r.get("nzb_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_raw.append(r)

        # Delete previous search results for this movie
        old = await db.execute(select(SearchResult).where(SearchResult.movie_id == movie_id))
        for old_sr in old.scalars().all():
            await db.delete(old_sr)

        stored = []
        audit_logs = []
        for r in unique_raw:
            try:
                release_title = str(r.get("release_title") or "").strip()
                if not release_title:
                    logger.warning("Skipping malformed search result for {}: missing release title", movie.title)
                    continue

                candidate_size = int(r.get("size") or 0)
                if candidate_size <= 0:
                    logger.warning(
                        "Skipping malformed search result for {}: invalid size for '{}'",
                        movie.title,
                        release_title,
                    )
                    continue

                parsed = parse_release_title(release_title)
                age_days = r.get("age_days") if r.get("age_days") is not None else _nzb_age_days(r.get("pub_date"))
                cmp = compare_release(
                    local_size=movie.file_size or 0,
                    local_resolution=movie.resolution or "",
                    local_codec=movie.video_codec or "",
                    candidate_size=candidate_size,
                    candidate_title=release_title,
                    candidate_age_days=age_days,
                    movie_title=movie.title,
                    movie_year=movie.year,
                    local_bitrate=movie.bitrate,
                    local_source_type=movie.source_type or "",
                )

                sr = SearchResult(
                    movie_id=movie.id,
                    indexer_name=r.get("indexer_name") or "unknown",
                    release_title=release_title,
                    nzb_url=r.get("nzb_url") or "",
                    size=candidate_size,
                    resolution=parsed.resolution,
                    video_codec=parsed.video_codec,
                    audio_codec=parsed.audio_codec,
                    source=parsed.source,
                    hdr=parsed.hdr,
                    languages=",".join(parsed.languages or []),
                    age_days=age_days,
                    savings_bytes=cmp.savings_bytes,
                    savings_pct=cmp.savings_pct,
                    score=cmp.score,
                    confidence_score=cmp.confidence_score,
                    confidence_breakdown=json.dumps(cmp.confidence_breakdown or {}),
                    media_health_score=cmp.media_health_score,
                    media_health_rating=cmp.media_health_rating,
                    media_health_reasons=json.dumps(cmp.media_health_reasons or []),
                    decision=cmp.decision,
                    reject_reason=cmp.reject_reason,
                )
                db.add(sr)
                stored.append(sr)

                audit_logs.append(
                    DecisionAuditLog(
                        movie_id=movie.id,
                        movie_title=movie.title,
                        indexer_name=r.get("indexer_name"),
                        release_title=release_title,
                        candidate_size=candidate_size,
                        local_size=movie.file_size,
                        decision=cmp.decision,
                        score=cmp.score,
                        confidence_score=cmp.confidence_score,
                        confidence_breakdown=json.dumps(cmp.confidence_breakdown or {}),
                        media_health_score=cmp.media_health_score,
                        media_health_rating=cmp.media_health_rating,
                        media_health_reasons=json.dumps(cmp.media_health_reasons or []),
                        savings_bytes=cmp.savings_bytes,
                        savings_pct=cmp.savings_pct,
                        reject_reason=cmp.reject_reason,
                        notes=cmp.notes or None,
                    )
                )
            except Exception as exc:
                logger.error(
                    "Skipping result for {} due to processing error: {}",
                    movie.title,
                    normalize_exception(exc),
                )
                continue

        if audit_logs:
            db.add_all(audit_logs)

        movie.last_searched = datetime.now(timezone.utc)
        await db.commit()

        accepted_count = sum(1 for s in stored if s.decision == "accept")
        rejected_count = len(stored) - accepted_count
        best_savings = max((s.savings_pct for s in stored if s.decision == "accept"), default=0.0)
        rejection_reasons = Counter(
            (s.reject_reason or "unknown").split("(")[0].strip()
            for s in stored
            if s.decision == "reject"
        )
        record_filter_summary(
            movie_id=movie.id,
            title=movie.title,
            raw_count=len(all_raw),
            unique_count=len(unique_raw),
            stored_count=len(stored),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            rejection_reasons=dict(rejection_reasons.most_common(10)),
        )
        await record_movie_search_completed(
            movie_id=movie.id,
            title=movie.title,
            raw_count=len(all_raw),
            accepted_count=accepted_count,
            indexer_attempts=indexer_attempts,
            indexer_failures=indexer_failures,
            configured_sources=configured_sources,
        )

        # Log some insights about why things were rejected
        if rejected_count > 0:
            res_downgrades = sum(1 for s in stored if s.reject_reason and s.reject_reason.startswith("Resolution downgrade"))
            larger_size = sum(1 for s in stored if s.reject_reason and s.reject_reason.startswith("Candidate is not smaller"))
            logger.info(f"Analyzed {len(stored)} results: {accepted_count} accepted, {rejected_count} rejected "
                        f"({res_downgrades} due to resolution downgrade limit, {larger_size} due to larger size limit).")

        await emit_event("search:results", {
            "movie_id": movie.id,
            "title": movie.title,
            "raw_results": len(all_raw),
            "unique_results": len(unique_raw),
            "total_results": len(stored),
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "best_savings_pct": best_savings,
        })

        return [
            {
                "id": s.id,
                "release_title": s.release_title,
                "size": s.size,
                "resolution": s.resolution,
                "video_codec": s.video_codec,
                "audio_codec": s.audio_codec,
                "source": s.source,
                "age_days": s.age_days,
                "hdr": s.hdr,
                "languages": s.languages.split(",") if s.languages else [],
                "media_health_score": s.media_health_score,
                "media_health_rating": s.media_health_rating,
                "media_health_reasons": _json_string_list(s.media_health_reasons),
                "decision": s.decision,
                "score": s.score,
                "confidence_score": s.confidence_score,
                "confidence_breakdown": s.confidence_breakdown,
                "savings_pct": s.savings_pct,
                "savings_bytes": s.savings_bytes,
                "reject_reason": s.reject_reason,
            }
            for s in stored
        ]


def _looks_like_movie_categories(categories: list[int]) -> bool:
    if not categories:
        return False
    return any(2000 <= int(cat) < 3000 for cat in categories)
