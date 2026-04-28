"""Retry ladder system - auto-retry failed downloads with next best candidate."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from backend.database import async_session, Download, SearchResult
from backend.config import get_config
from backend.core.blacklist import add_to_blacklist, is_blacklisted
from backend.core.parser import parse_release_title
from loguru import logger


def _max_retries() -> int:
    cfg = get_config()
    return int(getattr(cfg.blacklist, "max_retry_count", 3) or 3)


async def can_retry_download(download_id: int) -> tuple[bool, Optional[str]]:
    """
    Check if a download can be retried.
    Returns (can_retry, reason_if_not).
    """
    async with async_session() as session:
        result = await session.execute(
            select(Download).where(Download.id == download_id)
        )
        download = result.scalars().first()
        
        if not download:
            return False, "Download not found"
        
        max_retries = _max_retries()
        if download.retry_count >= max_retries:
            return False, f"Max retries ({max_retries}) reached"
        
        if download.status not in ["failed", "error"]:
            return False, f"Download status is {download.status}, not failed"
        
        return True, None


async def get_next_candidate(
    download_id: int,
) -> Optional[SearchResult]:
    """
    Find the next best candidate for a failed download.
    Excludes current release and blacklisted releases.
    Returns highest-scored accepted candidate or None.
    """
    async with async_session() as session:
        # Get the failed download
        result = await session.execute(
            select(Download).where(Download.id == download_id)
        )
        download = result.scalars().first()
        
        if not download or not download.movie_id:
            return None
        
        attempted_result = await session.execute(
            select(Download.release_title).where(Download.movie_id == download.movie_id)
        )
        attempted_titles = {
            title for title in attempted_result.scalars().all() if title
        }

        # Get accepted search results for this movie, excluding attempted releases.
        candidates_result = await session.execute(
            select(SearchResult).where(
                SearchResult.movie_id == download.movie_id,
                SearchResult.decision == "accept",
            ).order_by(SearchResult.score.desc())
        )
        candidates = candidates_result.scalars().all()
        
        # Filter out already-attempted release and check blacklist
        for candidate in candidates:
            if candidate.release_title in attempted_titles:
                continue
            
            # Check if blacklisted
            parsed = parse_release_title(candidate.release_title)
            blacklist_reason = await is_blacklisted(
                candidate.release_title,
                uploader=parsed.uploader,
                indexer_name=candidate.indexer_name,
            )
            
            if blacklist_reason:
                logger.debug(f"Skipping blacklisted: {candidate.release_title} ({blacklist_reason})")
                continue
            
            return candidate
    
    return None


async def retry_failed_download(
    download_id: int,
) -> tuple[bool, Optional[str], Optional[int]]:
    """
    Attempt to retry a failed download with the next best candidate.
    Returns (success, message).
    """
    # Check if retry is allowed
    can_retry, reason = await can_retry_download(download_id)
    if not can_retry:
        return False, f"Cannot retry: {reason}", None
    
    # Find next candidate
    next_candidate = await get_next_candidate(download_id)
    if not next_candidate:
        return False, "No alternative candidates available for retry", None
    
    # Capture current failed release details and increment retry counter on the failed row.
    old_release_title: str | None = None
    old_retry_count = 0
    async with async_session() as session:
        result = await session.execute(
            select(Download).where(Download.id == download_id)
        )
        download = result.scalars().first()

        if download:
            old_release_title = download.release_title
            old_retry_count = int(download.retry_count or 0)
            download.retry_count = old_retry_count + 1
            download.last_error_at = datetime.now(timezone.utc)
            await session.commit()

    if old_release_title:
        parsed_old = parse_release_title(old_release_title)
        await add_to_blacklist(
            release_title=old_release_title,
            uploader=parsed_old.uploader,
            indexer_name=None,
            reason="retry_failed_release",
            manual=False,
            expires_in_days=30,
        )

    from backend.core.downloader import start_download
    new_dl = await start_download(next_candidate.id)

    async with async_session() as session:
        result = await session.execute(select(Download).where(Download.id == new_dl.id))
        inserted = result.scalars().first()
        if inserted:
            inserted.retry_count = old_retry_count + 1
            inserted.grabbed_at = datetime.now(timezone.utc)
            await session.commit()

    logger.info(
        f"Retrying download {download_id} with candidate {next_candidate.id}: {next_candidate.release_title}"
    )
    return True, f"Retry #{old_retry_count + 1} started: {next_candidate.release_title}", new_dl.id


async def get_download_retry_count(download_id: int) -> int:
    """Get current retry count for a download."""
    async with async_session() as session:
        result = await session.execute(
            select(Download.retry_count).where(Download.id == download_id)
        )
        count = result.scalars().first()
        return count if count is not None else 0


async def mark_release_failed(
    download_id: int,
    reason: str = "unknown",
) -> None:
    """
    Mark a release as failed and add to blacklist.
    If max retries reached, blacklist permanently for this movie.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Download).where(Download.id == download_id)
        )
        download = result.scalars().first()
        
        if not download:
            return
        
        retry_count = download.retry_count + 1
        if not download.release_title:
            return

        parsed = parse_release_title(download.release_title)
        
        cfg = get_config()
        auto_expire_days = int(getattr(cfg.blacklist, "auto_expire_days", 30) or 30)

        # If max retries reached, add to permanent blacklist
        if retry_count >= _max_retries():
            await add_to_blacklist(
                release_title=download.release_title,
                uploader=parsed.uploader,
                indexer_name=None,
                reason=f"Max retries reached: {reason}",
                manual=False,
                expires_in_days=auto_expire_days,
            )
            logger.warning(f"Added to blacklist (max retries): {download.release_title}")
        else:
            # Temporary blacklist for this session (prevents immediate re-attempt)
            await add_to_blacklist(
                release_title=download.release_title,
                uploader=parsed.uploader,
                indexer_name=None,
                reason=f"Temporary failure: {reason}",
                manual=False,
                expires_in_days=1,  # Auto-expire after 1 day
            )
