"""Blacklist system - manage failed releases and prevent re-attempt."""
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.database import async_session, DownloadBlacklist
from loguru import logger


async def add_to_blacklist(
    release_title: str,
    uploader: Optional[str] = None,
    indexer_name: Optional[str] = None,
    reason: str = "unknown",
    manual: bool = False,
    expires_in_days: Optional[int] = None,
) -> DownloadBlacklist:
    """Add a release to the blacklist."""
    # Generate hash from title + uploader + indexer for dedup
    hash_input = f"{release_title.lower()}:{uploader or ''}:{indexer_name or ''}"
    release_hash = hashlib.md5(hash_input.encode()).hexdigest()

    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    async with async_session() as session:
        entry = DownloadBlacklist(
            release_title=release_title,
            release_hash=release_hash,
            uploader=uploader,
            indexer_name=indexer_name,
            reason=reason,
            manual=manual,
            expires_at=expires_at,
        )
        session.add(entry)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.execute(
                select(DownloadBlacklist).where(DownloadBlacklist.release_hash == release_hash)
            )
            found = existing.scalars().first()
            if found:
                return found
            raise
        await session.refresh(entry)

        logger.info(f"Added to blacklist: {release_title} (reason={reason}, expires={expires_at})")
        return entry


async def is_blacklisted(
    release_title: str,
    uploader: Optional[str] = None,
    indexer_name: Optional[str] = None,
) -> Optional[str]:
    """
    Check if a release is blacklisted.
    Returns blacklist reason if found and not expired, None otherwise.
    """
    hash_inputs = [
        f"{release_title.lower()}:{uploader or ''}:{indexer_name or ''}",
        f"{release_title.lower()}:{uploader or ''}:",
    ]
    release_hashes = [hashlib.md5(value.encode()).hexdigest() for value in hash_inputs]
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(
            select(DownloadBlacklist).where(
                DownloadBlacklist.release_hash.in_(release_hashes)
            )
        )
        entry = result.scalars().first()

        if entry:
            # Check if expired
            if entry.expires_at and entry.expires_at < now:
                # Auto-delete expired entry
                await session.delete(entry)
                await session.commit()
                return None

            return entry.reason

    return None


async def get_blacklist_reasons(
    candidates: list[tuple[str, Optional[str], Optional[str]]],
) -> dict[int, str]:
    """Batched form of is_blacklisted() for a list of
    (release_title, uploader, indexer_name) tuples. Returns a dict of
    candidate index -> blacklist reason for any that are blacklisted (and not
    expired), using a single query instead of one per candidate — used by the
    retry ladder, which may need to check dozens of candidates per retry.
    """
    if not candidates:
        return {}

    hash_to_indices: dict[str, list[int]] = {}
    for i, (release_title, uploader, indexer_name) in enumerate(candidates):
        for hash_input in (
            f"{release_title.lower()}:{uploader or ''}:{indexer_name or ''}",
            f"{release_title.lower()}:{uploader or ''}:",
        ):
            h = hashlib.md5(hash_input.encode()).hexdigest()
            hash_to_indices.setdefault(h, []).append(i)

    now = datetime.now(timezone.utc)
    reasons: dict[int, str] = {}
    async with async_session() as session:
        result = await session.execute(
            select(DownloadBlacklist).where(
                DownloadBlacklist.release_hash.in_(hash_to_indices.keys())
            )
        )
        entries = result.scalars().all()

        expired = []
        for entry in entries:
            if entry.expires_at and entry.expires_at < now:
                expired.append(entry)
                continue
            for i in hash_to_indices.get(entry.release_hash, []):
                reasons.setdefault(i, entry.reason)

        if expired:
            for entry in expired:
                await session.delete(entry)
            await session.commit()

    return reasons


async def remove_from_blacklist(release_hash: str) -> bool:
    """Manually remove a blacklist entry."""
    async with async_session() as session:
        result = await session.execute(
            select(DownloadBlacklist).where(
                DownloadBlacklist.release_hash == release_hash
            )
        )
        entry = result.scalars().first()

        if entry:
            await session.delete(entry)
            await session.commit()
            logger.info(f"Removed from blacklist: {entry.release_title}")
            return True

    return False


async def get_all_blacklist_entries() -> list[DownloadBlacklist]:
    """Get all active (non-expired) blacklist entries."""
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(
            select(DownloadBlacklist).where(
                (DownloadBlacklist.expires_at.is_(None)) |
                (DownloadBlacklist.expires_at > now)
            )
        )
        return result.scalars().all()


async def cleanup_expired_blacklist() -> int:
    """Remove expired blacklist entries. Returns count deleted."""
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(
            select(DownloadBlacklist).where(
                (DownloadBlacklist.expires_at.isnot(None)) &
                (DownloadBlacklist.expires_at <= now)
            )
        )
        expired = result.scalars().all()

        for entry in expired:
            await session.delete(entry)

        await session.commit()

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired blacklist entries")

        return len(expired)
