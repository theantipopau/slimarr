"""
Comparison engine — decides if a candidate release should replace the local file.
Core rule: NEVER increase file size.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.config import get_config
from backend.core.parser import (
    get_codec_rank, get_resolution_rank, normalize_codec, normalize_resolution,
    parse_release_title,
)


@dataclass
class ComparisonResult:
    decision: str               # "accept" | "reject"
    score: float
    savings_bytes: int
    savings_pct: float
    reject_reason: Optional[str] = None
    notes: str = ""


def compare_release(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidate_size: int,
    candidate_title: str,
) -> ComparisonResult:
    config = get_config()
    parsed = parse_release_title(candidate_title)

    def _reject(reason: str) -> ComparisonResult:
        savings = local_size - candidate_size
        pct = (savings / max(local_size, 1)) * 100
        return ComparisonResult(
            decision="reject",
            score=0.0,
            savings_bytes=savings,
            savings_pct=round(pct, 2),
            reject_reason=reason,
        )

    # Hard rule: candidate must be smaller
    if candidate_size <= 0:
        return _reject("Candidate has no size information")
    if candidate_size >= local_size:
        diff_mb = (candidate_size - local_size) / 1_048_576
        return _reject(
            f"Candidate is not smaller (+{diff_mb:.0f} MB vs local)"
        )

    savings_bytes = local_size - candidate_size
    savings_pct = (savings_bytes / max(local_size, 1)) * 100

    # Minimum savings threshold
    if savings_pct < config.comparison.min_savings_percent:
        return _reject(
            f"Savings {savings_pct:.1f}% < minimum {config.comparison.min_savings_percent}%"
        )

    # Resolution check
    local_res_rank = get_resolution_rank(local_resolution)
    cand_res = parsed.resolution or "unknown"
    cand_res_rank = get_resolution_rank(cand_res)

    if cand_res_rank < local_res_rank:
        if not config.comparison.allow_resolution_downgrade:
            return _reject(
                f"Resolution downgrade {local_resolution}→{cand_res} not allowed"
            )
        if savings_pct < config.comparison.downgrade_min_savings_percent:
            return _reject(
                f"Resolution downgrade requires {config.comparison.downgrade_min_savings_percent}% savings, "
                f"got {savings_pct:.1f}%"
            )

    # Score calculation
    score = savings_pct

    cand_codec = normalize_codec(parsed.video_codec or "")
    codec_delta = get_codec_rank(cand_codec) - get_codec_rank(normalize_codec(local_codec))
    score += codec_delta * 0.5

    if cand_res_rank > local_res_rank:
        score += 20.0   # Big bonus for resolution upgrade at smaller size

    if cand_codec in [c.lower() for c in config.comparison.preferred_codecs]:
        score += 10.0

    notes = []
    if cand_res_rank > local_res_rank:
        notes.append(f"Resolution upgrade: {local_resolution}→{cand_res}")
    if codec_delta > 0:
        notes.append(f"Codec upgrade: {local_codec}→{cand_codec}")

    return ComparisonResult(
        decision="accept",
        score=round(score, 2),
        savings_bytes=savings_bytes,
        savings_pct=round(savings_pct, 2),
        notes="; ".join(notes),
    )


def rank_candidates(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidates: list[dict],
) -> list[tuple[dict, ComparisonResult]]:
    """Return accepted candidates sorted by score descending."""
    results = [
        (c, compare_release(local_size, local_resolution, local_codec,
                             c["size"], c["release_title"]))
        for c in candidates
    ]
    accepted = [(c, r) for c, r in results if r.decision == "accept"]
    accepted.sort(key=lambda x: x[1].score, reverse=True)
    return accepted
