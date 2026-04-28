"""
Usenet release searcher — queries indexers for a specific movie.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from loguru import logger
from sqlalchemy import select

from backend.core.comparer import compare_release
from backend.core.parser import parse_release_title
from backend.database import DecisionAuditLog, Movie, SearchResult, async_session
from backend.realtime.events import emit_event


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

        # Prowlarr path
        if config.prowlarr.enabled and config.prowlarr.url:
            try:
                prowlarr = ProwlarrClient()
                query = f"{movie.title} {movie.year}" if movie.year else movie.title
                all_raw.extend(await prowlarr.search(query=query))
            except Exception as e:
                logger.error(f"Prowlarr search failed: {e}")

        # Direct indexer path
        if not config.prowlarr.enabled or not all_raw:
                import asyncio

                async def _search_one(idx_cfg) -> list[dict]:
                    try:
                        client = NewznabClient(idx_cfg)
                        if movie.imdb_id:
                            return await client.search_by_imdb(movie.imdb_id)
                        query = f"{movie.title} {movie.year}" if movie.year else movie.title
                        return await client.search_by_query(query)
                    except Exception as e:
                        logger.error(f"Indexer {idx_cfg.name} search failed: {e}")
                        return []

                results_per_indexer = await asyncio.gather(*[_search_one(idx) for idx in config.indexers])
                for r in results_per_indexer:
                    all_raw.extend(r)

        logger.info(f"Found {len(all_raw)} raw results for {movie.title}")

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
            parsed = parse_release_title(r["release_title"])
            age_days = r.get("age_days") if r.get("age_days") is not None else _nzb_age_days(r.get("pub_date"))
            cmp = compare_release(
                local_size=movie.file_size or 0,
                local_resolution=movie.resolution or "",
                local_codec=movie.video_codec or "",
                candidate_size=r["size"],
                candidate_title=r["release_title"],
                candidate_age_days=age_days,
            )
            sr = SearchResult(
                movie_id=movie.id,
                indexer_name=r["indexer_name"],
                release_title=r["release_title"],
                nzb_url=r["nzb_url"],
                size=r["size"],
                resolution=parsed.resolution,
                video_codec=parsed.video_codec,
                audio_codec=parsed.audio_codec,
                source=parsed.source,
                age_days=age_days,
                savings_bytes=cmp.savings_bytes,
                savings_pct=cmp.savings_pct,
                score=cmp.score,
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
                    release_title=r["release_title"],
                    candidate_size=r.get("size"),
                    local_size=movie.file_size,
                    decision=cmp.decision,
                    score=cmp.score,
                    savings_bytes=cmp.savings_bytes,
                    savings_pct=cmp.savings_pct,
                    reject_reason=cmp.reject_reason,
                    notes=cmp.notes or None,
                )
            )

        if audit_logs:
            db.add_all(audit_logs)

        movie.last_searched = datetime.now(timezone.utc)
        await db.commit()

        accepted_count = sum(1 for s in stored if s.decision == "accept")
        rejected_count = len(stored) - accepted_count
        best_savings = max((s.savings_pct for s in stored if s.decision == "accept"), default=0.0)

        # Log some insights about why things were rejected
        if rejected_count > 0:
            res_downgrades = sum(1 for s in stored if s.reject_reason and s.reject_reason.startswith("Resolution downgrade"))
            larger_size = sum(1 for s in stored if s.reject_reason and s.reject_reason.startswith("Candidate is not smaller"))
            logger.info(f"Analyzed {len(stored)} results: {accepted_count} accepted, {rejected_count} rejected "
                        f"({res_downgrades} due to resolution downgrade limit, {larger_size} due to larger size limit).")

        await emit_event("search:results", {
            "movie_id": movie.id,
            "title": movie.title,
            "total_results": len(stored),
            "accepted_count": accepted_count,
            "best_savings_pct": best_savings,
        })

        return [
            {
                "id": s.id,
                "release_title": s.release_title,
                "size": s.size,
                "resolution": s.resolution,
                "video_codec": s.video_codec,
                "age_days": s.age_days,
                "decision": s.decision,
                "score": s.score,
                "savings_pct": s.savings_pct,
                "savings_bytes": s.savings_bytes,
            }
            for s in stored
        ]
