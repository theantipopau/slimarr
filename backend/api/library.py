"""Library (movies) API routes."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import or_, select

from backend.auth.dependencies import get_current_user
from backend.database import Movie, SearchResult, async_session

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/movies")
async def list_movies(
    page: int = 1,
    per_page: int = 50,
    search: str = "",
    status: str = "",
    sort: str = "title",
    user=Depends(get_current_user),
):
    async with async_session() as db:
        query = select(Movie)
        if search:
            like = f"%{search}%"
            query = query.where(or_(Movie.title.ilike(like)))
        if status:
            query = query.where(Movie.status == status)

        sort_map = {
            "title": Movie.title.asc(),
            "year": Movie.year.desc(),
            "size": Movie.file_size.desc(),
            "status": Movie.status.asc(),
        }
        query = query.order_by(sort_map.get(sort, Movie.title.asc()))

        count_q = select(Movie)
        if search:
            count_q = count_q.where(Movie.title.ilike(f"%{search}%"))
        if status:
            count_q = count_q.where(Movie.status == status)

        from sqlalchemy import func
        total_result = await db.execute(select(func.count()).select_from(count_q.subquery()))
        total = total_result.scalar_one()

        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        movies = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "movies": [_movie_dict(m) for m in movies],
    }


@router.get("/movies/{movie_id}")
async def get_movie(movie_id: int, user=Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return _movie_dict(movie)


@router.get("/movies/{movie_id}/search-results")
async def get_search_results(movie_id: int, user=Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(
            select(SearchResult)
            .where(SearchResult.movie_id == movie_id)
            .order_by(SearchResult.score.desc())
        )
        srs = result.scalars().all()
    return [_sr_dict(s) for s in srs]


@router.post("/movies/{movie_id}/search-results/{result_id}/download")
async def download_result(
    movie_id: int,
    result_id: int,
    background: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Queue a specific search result for download."""
    async with async_session() as db:
        result = await db.execute(
            select(SearchResult).where(
                SearchResult.id == result_id,
                SearchResult.movie_id == movie_id,
            )
        )
        sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Search result not found")

    async def _do_download(sr_id: int) -> None:
        from backend.core.downloader import start_download
        try:
            await start_download(sr_id)
        except Exception as e:
            from loguru import logger
            logger.error(f"Download failed for search result {sr_id}: {e}")

    background.add_task(_do_download, result_id)
    return {"status": "download_queued", "search_result_id": result_id}


@router.post("/movies/{movie_id}/search")
async def trigger_search(movie_id: int, background: BackgroundTasks, user=Depends(get_current_user)):
    background.add_task(_run_search, movie_id)
    return {"status": "search_started", "movie_id": movie_id}


@router.post("/movies/{movie_id}/process")
async def trigger_process(movie_id: int, background: BackgroundTasks, user=Depends(get_current_user)):
    background.add_task(_run_process, movie_id)
    return {"status": "process_started", "movie_id": movie_id}


async def _run_search(movie_id: int) -> None:
    from backend.core.searcher import search_for_movie
    try:
        await search_for_movie(movie_id)
    except Exception as e:
        from loguru import logger
        logger.error(f"Background search failed for movie {movie_id}: {e}")


async def _run_process(movie_id: int) -> None:
    from backend.core.orchestrator import process_single_movie
    try:
        await process_single_movie(movie_id)
    except Exception as e:
        from loguru import logger
        logger.error(f"Background process failed for movie {movie_id}: {e}")


def _movie_dict(m: Movie) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "tmdb_id": m.tmdb_id,
        "imdb_id": m.imdb_id,
        "overview": m.overview,
        "poster_path": m.poster_path,
        "file_path": m.file_path,
        "file_size": m.file_size,
        "original_file_size": m.original_file_size,
        "resolution": m.resolution,
        "video_codec": m.video_codec,
        "audio_codec": m.audio_codec,
        "status": m.status,
        "last_scanned": m.last_scanned.isoformat() if m.last_scanned else None,
        "last_searched": m.last_searched.isoformat() if m.last_searched else None,
    }


def _sr_dict(s: SearchResult) -> dict:
    return {
        "id": s.id,
        "indexer_name": s.indexer_name,
        "release_title": s.release_title,
        "size": s.size,
        "resolution": s.resolution,
        "video_codec": s.video_codec,
        "score": s.score,
        "savings_bytes": s.savings_bytes,
        "savings_pct": s.savings_pct,
        "decision": s.decision,
        "reject_reason": s.reject_reason,
    }
