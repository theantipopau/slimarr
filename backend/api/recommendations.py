"""Recommendation & Collection Completion API.

See docs/RECOMMENDATION_ARCHITECTURE.md for the data model and
docs/RECOMMENDATION_INTEGRATIONS.md for the hand-off capability model. Every
route here requires authentication, matching the rest of the app's
data-bearing endpoints (see docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md's audit
of existing auth coverage).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.api.models import (
    RecommendationActionResponse,
    RecommendationCapabilitiesResponse,
    RecommendationListResponse,
    RecommendationRefreshResponse,
    SendToRadarrRequest,
    SendToSonarrRequest,
)
from backend.auth.dependencies import get_current_user
from backend.core.recommendations.streaming import is_stale as availability_is_stale
from backend.database import Movie, Recommendation, RecommendationCandidate, async_session
from backend.utils.responses import get_correlation_id, not_found, service_unavailable, validation_error

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

_SORT_MAP = {
    "relevance": lambda: Recommendation.score.desc(),
    "date_added": lambda: Recommendation.created_at.desc(),
    "popularity": lambda: RecommendationCandidate.popularity.desc(),
    "release_date": lambda: RecommendationCandidate.year.desc(),
}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _is_already_in_plex(db, tmdb_id: int, imdb_id: str | None) -> bool:
    query = select(func.count()).select_from(Movie).where(Movie.tmdb_id == tmdb_id)
    count = (await db.execute(query)).scalar_one()
    if count > 0:
        return True
    if imdb_id:
        count = (
            await db.execute(select(func.count()).select_from(Movie).where(Movie.imdb_id == imdb_id))
        ).scalar_one()
        return count > 0
    return False


def _serialize(rec: Recommendation, candidate: RecommendationCandidate, already_in_plex: bool) -> dict:
    return {
        "id": rec.id,
        "candidate_id": candidate.id,
        "media_type": candidate.media_type,
        "title": candidate.title,
        "year": candidate.year,
        "tmdb_id": candidate.tmdb_id,
        "imdb_id": candidate.imdb_id,
        "poster_path": candidate.poster_path,
        "backdrop_path": candidate.backdrop_path,
        "overview": candidate.overview,
        "popularity": candidate.popularity,
        "vote_average": candidate.vote_average,
        "category": rec.category,
        "score": rec.score,
        "state": rec.state,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
        "reasons": [
            {
                "reason_code": r.reason_code,
                "explanation": r.explanation,
                "source_movie_id": r.source_movie_id,
                "source_provider": r.source_provider,
                "weight": r.weight,
            }
            for r in sorted(rec.reasons, key=lambda r: -(r.weight or 0))
        ],
        "availability": [
            {
                "region": a.region,
                "provider_id": a.provider_id,
                "provider_name": a.provider_name,
                "display_priority": a.display_priority,
                "availability_type": a.availability_type,
                "source": a.source,
                "source_url": a.source_url,
                "checked_at": a.checked_at.isoformat() if a.checked_at else None,
                "stale": availability_is_stale(a.checked_at) if a.checked_at else True,
            }
            for a in candidate.availability
        ],
        "already_in_plex": already_in_plex,
    }


@router.get("", response_model=RecommendationListResponse)
async def list_recommendations(
    page: int = 1,
    per_page: int = 30,
    media_type: str = "",
    category: str = "",
    state: str = "active",
    provider_id: int | None = None,
    sort: str = "relevance",
    user=Depends(get_current_user),
):
    """Defaults to state="active" — pass state="" to see every state
    (including dismissed/hidden/already_managed) for a full audit view."""
    page = max(1, page)
    per_page = max(1, min(per_page, 100))

    async with async_session() as db:
        query = (
            select(Recommendation)
            .join(RecommendationCandidate)
            .options(selectinload(Recommendation.reasons), selectinload(Recommendation.candidate).selectinload(RecommendationCandidate.availability))
        )
        count_query = select(func.count()).select_from(Recommendation).join(RecommendationCandidate)

        if state:
            query = query.where(Recommendation.state == state)
            count_query = count_query.where(Recommendation.state == state)
        if category:
            query = query.where(Recommendation.category == category)
            count_query = count_query.where(Recommendation.category == category)
        if media_type:
            query = query.where(RecommendationCandidate.media_type == media_type)
            count_query = count_query.where(RecommendationCandidate.media_type == media_type)

        total = (await db.execute(count_query)).scalar_one()

        query = query.order_by(_SORT_MAP.get(sort, _SORT_MAP["relevance"])())
        query = query.offset((page - 1) * per_page).limit(per_page)
        recs = (await db.execute(query)).unique().scalars().all()

        if provider_id is not None:
            recs = [
                r for r in recs
                if any(a.provider_id == provider_id for a in r.candidate.availability)
            ]

        out = []
        for rec in recs:
            already_owned = await _is_already_in_plex(db, rec.candidate.tmdb_id, rec.candidate.imdb_id)
            out.append(_serialize(rec, rec.candidate, already_owned))

    return {"total": total, "page": page, "per_page": per_page, "recommendations": out}


@router.get("/capabilities", response_model=RecommendationCapabilitiesResponse)
async def get_capabilities(user=Depends(get_current_user)):
    """Capability detection for hand-off actions — the frontend disables an
    action gracefully rather than the backend silently failing on click.
    See docs/RECOMMENDATION_INTEGRATIONS.md for why Seerr hand-off is
    reported unavailable in this release."""
    from backend.config import get_config

    config = get_config()

    def _radarr_sonarr_status(cfg) -> dict:
        if not (cfg.enabled and cfg.url and cfg.api_key):
            return {"available": False, "reason": "Not configured."}
        return {"available": True, "reason": None}

    return {
        "radarr": _radarr_sonarr_status(config.radarr),
        "sonarr": _radarr_sonarr_status(config.sonarr),
        "seerr": {
            "available": False,
            "reason": (
                "Seerr hand-off requires verifying the configured instance's actual API "
                "version against live capability detection, which this release does not "
                "yet implement — see docs/RECOMMENDATION_INTEGRATIONS.md."
            ),
        },
    }


@router.post("/refresh", response_model=RecommendationRefreshResponse)
async def trigger_refresh(user=Depends(get_current_user)):
    """Reuses the existing durable-job singleton mechanism (core/jobs.py) —
    a second refresh request while one is already running returns
    already_running instead of starting a duplicate, which is also this
    endpoint's rate limit."""
    from backend.config import get_config
    from backend.core.jobs import enqueue_job

    config = get_config()
    if not config.recommendations.enabled:
        raise validation_error(
            "Recommendations are disabled — enable recommendations.enabled in Settings first.",
            correlation_id=get_correlation_id(),
        )

    result = await enqueue_job("recommendation_refresh", singleton=True)
    if result["already_running"]:
        return {"status": "already_running", "already_running": True, "job_id": result["job"]["id"]}
    return {"status": "started", "job_id": result["job"]["id"]}


async def _get_recommendation_or_404(db, recommendation_id: int) -> Recommendation:
    rec = (
        await db.execute(
            select(Recommendation)
            .where(Recommendation.id == recommendation_id)
            .options(selectinload(Recommendation.candidate))
        )
    ).scalar_one_or_none()
    if rec is None:
        raise not_found("Recommendation", correlation_id=get_correlation_id())
    return rec


async def _set_state_and_record(recommendation_id: int, new_state: str, action: str, detail: dict | None = None) -> dict:
    from backend.core.recommendations.engine import record_feedback

    async with async_session() as db:
        rec = await _get_recommendation_or_404(db, recommendation_id)
        rec.state = new_state
        if new_state == "dismissed":
            rec.dismissed_at = _utc_now_naive()
        if new_state == "actioned":
            rec.acted_at = _utc_now_naive()
        await db.commit()
        state = rec.state

    await record_feedback(recommendation_id, action, detail)
    return {"success": True, "id": recommendation_id, "state": state}


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationActionResponse)
async def dismiss_recommendation(recommendation_id: int, user=Depends(get_current_user)):
    return await _set_state_and_record(recommendation_id, "dismissed", "dismissed")


@router.post("/{recommendation_id}/hide", response_model=RecommendationActionResponse)
async def hide_recommendation(recommendation_id: int, user=Depends(get_current_user)):
    return await _set_state_and_record(recommendation_id, "hidden", "hidden")


@router.post("/{recommendation_id}/watchlist", response_model=RecommendationActionResponse)
async def watchlist_recommendation(recommendation_id: int, user=Depends(get_current_user)):
    return await _set_state_and_record(recommendation_id, "watchlisted", "watchlisted")


@router.post("/{recommendation_id}/mark-owned", response_model=RecommendationActionResponse)
async def mark_owned_recommendation(recommendation_id: int, user=Depends(get_current_user)):
    return await _set_state_and_record(recommendation_id, "already_available", "marked_owned")


@router.post("/{recommendation_id}/refresh-availability", response_model=RecommendationActionResponse)
async def refresh_availability(recommendation_id: int, user=Depends(get_current_user)):
    from backend.config import get_config
    from backend.core.recommendations.engine import _upsert_availability
    from backend.core.recommendations.streaming import fetch_availability
    from backend.integrations.tmdb import TMDBClient

    config = get_config()
    async with async_session() as db:
        rec = await _get_recommendation_or_404(db, recommendation_id)
        candidate = rec.candidate
        if not config.recommendations.region:
            raise validation_error(
                "Set recommendations.region in Settings before checking availability.",
                correlation_id=get_correlation_id(),
            )
        entries = await fetch_availability(
            tmdb=TMDBClient(), tmdb_id=candidate.tmdb_id, media_type=candidate.media_type,
            region=config.recommendations.region,
        )
        await _upsert_availability(db, candidate, entries)
        await db.commit()
        state = rec.state

    from backend.core.recommendations.engine import record_feedback
    await record_feedback(recommendation_id, "availability_refreshed")
    return {"success": True, "id": recommendation_id, "state": state, "message": f"{len(entries)} provider(s) found"}


@router.post("/{recommendation_id}/send-to-radarr", response_model=RecommendationActionResponse)
async def send_to_radarr(recommendation_id: int, body: SendToRadarrRequest, user=Depends(get_current_user)):
    from backend.config import get_config
    from backend.integrations.radarr import RadarrClient

    config = get_config()
    if not (config.radarr.enabled and config.radarr.url and config.radarr.api_key):
        raise service_unavailable("Radarr", correlation_id=get_correlation_id())

    async with async_session() as db:
        rec = await _get_recommendation_or_404(db, recommendation_id)
        candidate = rec.candidate
        if candidate.media_type != "movie":
            raise validation_error("Only movie candidates can be sent to Radarr.", correlation_id=get_correlation_id())

        client = RadarrClient()
        existing = await client.find_movie_by_imdb(candidate.imdb_id) if candidate.imdb_id else None
        if existing:
            raise validation_error(
                f"'{candidate.title}' is already managed in Radarr.", correlation_id=get_correlation_id(),
            )

        result = await client.add_movie(
            tmdb_id=candidate.tmdb_id,
            title=candidate.title,
            year=candidate.year,
            root_folder_path=body.root_folder_path,
            quality_profile_id=body.quality_profile_id,
            monitored=body.monitored,
            search_now=body.search_now,
        )
        rec.state = "actioned"
        rec.acted_at = _utc_now_naive()
        await db.commit()
        state = rec.state

    from backend.core.recommendations.engine import record_feedback
    await record_feedback(recommendation_id, "sent_to_radarr", {"radarr_movie_id": result.get("id")})
    return {"success": True, "id": recommendation_id, "state": state, "message": "Sent to Radarr"}


@router.post("/{recommendation_id}/send-to-sonarr", response_model=RecommendationActionResponse)
async def send_to_sonarr(recommendation_id: int, body: SendToSonarrRequest, user=Depends(get_current_user)):
    from backend.config import get_config
    from backend.integrations.sonarr import SonarrClient

    config = get_config()
    if not (config.sonarr.enabled and config.sonarr.url and config.sonarr.api_key):
        raise service_unavailable("Sonarr", correlation_id=get_correlation_id())

    async with async_session() as db:
        rec = await _get_recommendation_or_404(db, recommendation_id)
        candidate = rec.candidate
        if candidate.media_type != "tv":
            raise validation_error("Only TV candidates can be sent to Sonarr.", correlation_id=get_correlation_id())
        if not candidate.tvdb_id:
            raise validation_error(
                "This candidate has no TVDB ID on file, required by Sonarr.", correlation_id=get_correlation_id(),
            )

        client = SonarrClient()
        series_list = await client.get_all_series()
        target = candidate.title.strip().lower()
        if any(s.get("title", "").strip().lower() == target for s in series_list):
            raise validation_error(
                f"'{candidate.title}' is already managed in Sonarr.", correlation_id=get_correlation_id(),
            )

        result = await client.add_series(
            tvdb_id=candidate.tvdb_id,
            title=candidate.title,
            root_folder_path=body.root_folder_path,
            quality_profile_id=body.quality_profile_id,
            monitored=body.monitored,
            search_now=body.search_now,
        )
        rec.state = "actioned"
        rec.acted_at = _utc_now_naive()
        await db.commit()
        state = rec.state

    from backend.core.recommendations.engine import record_feedback
    await record_feedback(recommendation_id, "sent_to_sonarr", {"sonarr_series_id": result.get("id")})
    return {"success": True, "id": recommendation_id, "state": state, "message": "Sent to Sonarr"}
