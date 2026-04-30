"""
Comparison engine — decides if a candidate release should replace the local file.
Core rule: NEVER increase file size.
"""
from __future__ import annotations

import os
import re
import sqlite3
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
    confidence_score: float = 0.0
    confidence_breakdown: dict[str, float] | None = None



def _uploader_health_score(uploader: Optional[str]) -> float:
    """Fetch uploader health score from SQLite, defaulting to neutral (0.5)."""
    if not uploader:
        return 0.5

    db_path = os.environ.get("SLIMARR_DB", "data/slimarr.db")
    if not os.path.exists(db_path):
        return 0.5

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT health_score FROM uploader_stats WHERE uploader = ?", (uploader,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return 0.5
        return max(0.0, min(1.0, float(row[0])))
    except Exception:
        return 0.5


def _normalize_title(value: str) -> str:
    value = re.sub(r"[\._\-]+", " ", value.lower())
    value = re.sub(r"\b(19|20)\d{2}\b.*$", "", value)
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _title_match_score(movie_title: str, release_title: str) -> float:
    expected = _normalize_title(movie_title)
    candidate = _normalize_title(release_title)
    if not expected or not candidate:
        return 35.0
    if expected == candidate or candidate.startswith(expected):
        return 100.0

    expected_tokens = {t for t in expected.split() if len(t) > 1}
    candidate_tokens = {t for t in candidate.split() if len(t) > 1}
    if not expected_tokens:
        return 35.0
    overlap = len(expected_tokens & candidate_tokens) / len(expected_tokens)
    return round(overlap * 100, 2)


def _source_quality_score(source: str | None) -> float:
    source = (source or "").lower()
    scores = {
        "remux": 100.0,
        "bluray": 88.0,
        "web-dl": 78.0,
        "webrip": 64.0,
        "hdtv": 45.0,
        "dvdrip": 30.0,
    }
    return scores.get(source, 55.0)

def compare_release(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidate_size: int,
    candidate_title: str,
    candidate_age_days: int | None = None,
    movie_title: str = "",
    movie_year: int | None = None,
    indexer_reliability: float | None = None,
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
            confidence_score=0.0,
            confidence_breakdown={},
        )

    # Hard rule: candidate must be smaller
    if candidate_size <= 0:
        return _reject("Candidate has no size information")
    if candidate_size >= local_size:
        diff_mb = (candidate_size - local_size) / 1_048_576
        return _reject(
            f"Candidate is not smaller (+{diff_mb:.0f} MB vs local)"
        )

    # Minimum candidate file size floor (avoid tiny broken encodes)
    min_size_bytes = config.comparison.minimum_file_size_mb * 1_048_576
    if min_size_bytes > 0 and candidate_size < min_size_bytes:
        return _reject(
            f"Candidate size {candidate_size / 1_048_576:.0f} MB is below "
            f"minimum {config.comparison.minimum_file_size_mb} MB threshold"
        )

    savings_bytes = local_size - candidate_size
    savings_pct = (savings_bytes / max(local_size, 1)) * 100

    if candidate_age_days is not None and config.comparison.max_candidate_age_days > 0:
        if candidate_age_days > config.comparison.max_candidate_age_days:
            return _reject(
                f"NZB age {candidate_age_days}d exceeds max {config.comparison.max_candidate_age_days}d"
            )

    if movie_year and parsed.year and config.comparison.require_year_match:
        if abs(int(parsed.year) - int(movie_year)) > 1:
            return _reject(f"Release year {parsed.year} does not match movie year {movie_year}")

    match_score = _title_match_score(movie_title, candidate_title) if movie_title else 75.0
    if movie_title and match_score < 70.0:
        return _reject(f"Title match confidence too low ({match_score:.0f}%)")

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
    if config.comparison.reject_upscaled and re.search(r"\b(upscaled|upscale|ds4k)\b", candidate_title, re.IGNORECASE):
        if cand_res_rank >= local_res_rank:
            return _reject("Upscaled release rejected by safety rules")

    # Score calculation
    score = savings_pct

    # Resolution priority: strongly prefer 4K/UHD upgrades when they are smaller.
    if cand_res_rank >= 4 and cand_res_rank > local_res_rank:
        score += 50.0

    # LANGUAGE VALIDATION: Enforce English-only by default
    if config.comparison.preferred_language:
        pref = config.comparison.preferred_language.lower()
        # STRENGTHENED: Reject any release with non-English tags unless multi
        if parsed.languages:
            has_pref = pref in parsed.languages
            has_multi = 'multi' in parsed.languages
            
            # If no explicit preference or if we found explicit non-preferred languages
            if not has_pref and not has_multi:
                found_langs = ','.join(parsed.languages)
                return _reject(f"Non-English release detected: {found_langs} (expected {pref})")
            
            # Bonus if language is explicitly tagged as preferred
            if has_pref:
                score += 5.0
        else:
            # No languages tagged - assume English (safe assumption for most content)
            score += 2.0
            
    cand_codec = normalize_codec(parsed.video_codec or "")
    codec_delta = get_codec_rank(cand_codec) - get_codec_rank(normalize_codec(local_codec))
    score += codec_delta * 0.5

    if cand_res_rank > local_res_rank:
        score += 20.0   # Big bonus for resolution upgrade at smaller size

    if cand_codec in [c.lower() for c in config.comparison.preferred_codecs]:
        score += 10.0

    # Release freshness: stale releases get penalized.
    age_days = candidate_age_days if candidate_age_days is not None else parsed.release_age_days
    stale_days = int(getattr(config.quality, "stale_release_days", 30) or 30)
    if age_days is not None:
        if age_days > stale_days:
            staleness_penalty = min(35.0, (age_days - stale_days) / 10)
            score -= staleness_penalty
        elif age_days > 7:
            staleness_penalty = (age_days - 7) * 0.3
            score -= staleness_penalty
        else:
            score += 2.0

    # Uploader quality: bad uploaders are rejected, good ones rewarded.
    uploader_health = _uploader_health_score(parsed.uploader or parsed.group)
    if uploader_health < 0.3:
        return _reject(f"Uploader quality too low ({uploader_health:.2f})")
    score += uploader_health * 10.0

    size_score = max(0.0, min(100.0, savings_pct * 2.0))
    codec_score = max(0.0, min(100.0, 55.0 + codec_delta * 12.0))
    if cand_res_rank == local_res_rank:
        resolution_score = 100.0
    elif cand_res_rank > local_res_rank:
        resolution_score = 92.0
    else:
        resolution_score = 30.0
    language_score = 100.0 if not parsed.languages else (95.0 if config.comparison.preferred_language.lower() in parsed.languages else 75.0 if "multi" in parsed.languages else 20.0)
    source_score = _source_quality_score(parsed.source)
    reliability_score = max(0.0, min(100.0, (indexer_reliability if indexer_reliability is not None else uploader_health) * 100.0))
    confidence_breakdown = {
        "size_reduction": round(size_score, 2),
        "codec": round(codec_score, 2),
        "resolution": round(resolution_score, 2),
        "source": round(source_score, 2),
        "language": round(language_score, 2),
        "match_certainty": round(match_score, 2),
        "indexer_reliability": round(reliability_score, 2),
    }
    confidence_score = round(
        size_score * 0.22
        + codec_score * 0.12
        + resolution_score * 0.16
        + source_score * 0.12
        + language_score * 0.12
        + match_score * 0.18
        + reliability_score * 0.08,
        2,
    )
    if confidence_score < config.comparison.minimum_confidence_score:
        result = _reject(
            f"Confidence {confidence_score:.0f} < minimum {config.comparison.minimum_confidence_score:.0f}"
        )
        result.confidence_score = confidence_score
        result.confidence_breakdown = confidence_breakdown
        return result

    notes = []
    if cand_res_rank > local_res_rank:
        notes.append(f"Resolution upgrade: {local_resolution}→{cand_res}")
    if codec_delta > 0:
        notes.append(f"Codec upgrade: {local_codec}→{cand_codec}")
    if age_days is not None:
        notes.append(f"NZB age: {age_days} days")
    if parsed.uploader or parsed.group:
        notes.append(f"Uploader score: {uploader_health:.2f}")
    notes.append(f"Confidence: {confidence_score:.0f}")

    return ComparisonResult(
        decision="accept",
        score=round(score, 2),
        savings_bytes=savings_bytes,
        savings_pct=round(savings_pct, 2),
        notes="; ".join(notes),
        confidence_score=confidence_score,
        confidence_breakdown=confidence_breakdown,
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
                             c["size"], c["release_title"], c.get("age_days")))
        for c in candidates
    ]
    accepted = [(c, r) for c, r in results if r.decision == "accept"]
    accepted.sort(key=lambda x: x[1].score, reverse=True)
    return accepted
