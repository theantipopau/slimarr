"""Comparison engine: decide whether a candidate should replace local media."""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from backend.config import get_config
from backend.core.media_health import score_local_media_health, score_release_health
from backend.core.parser import (
    get_codec_rank,
    get_resolution_rank,
    get_source_rank,
    normalize_codec,
    parse_release_title,
)


@dataclass
class ComparisonResult:
    decision: str
    score: float
    savings_bytes: int
    savings_pct: float
    reject_reason: Optional[str] = None
    notes: str = ""
    confidence_score: float = 0.0
    confidence_breakdown: dict[str, float] | None = None
    media_health_score: float = 0.0
    media_health_rating: str = "Unknown"
    media_health_reasons: list[str] | None = None


def _uploader_health_score(uploader: Optional[str]) -> float:
    if not uploader:
        return 0.5

    db_path = os.environ.get("SLIMARR_DB", "data/slimarr.db")
    if not os.path.exists(db_path):
        return 0.5

    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT health_score FROM uploader_stats WHERE uploader = ?", (uploader,))
            row = cur.fetchone()

        if not row or row[0] is None:
            return 0.5

        score = float(row[0])
        return max(0.0, min(1.0, score))
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
        "telecine": 20.0,
        "hdts": 12.0,
        "ts": 10.0,
        "hdcam": 8.0,
        "cam": 5.0,
    }
    return scores.get(source, 55.0)


def _has_explicit_language_marker(candidate_title: str, language: str) -> bool:
    checks = {
        "english": r"\b(eng|english|dual[- ._]?audio[ ._]?eng?)\b",
        "italian": r"\b(ita|italian|trueita|subita)\b",
        "french": r"\b(fr|fra|french|vff|truefrench|vostfr)\b",
        "german": r"\b(ger|deu|german)\b",
        "spanish": r"\b(esp|spa|spanish|castellano|latino)\b",
        "russian": r"\b(rus|russian)\b",
    }
    pattern = checks.get((language or "").strip().lower())
    if not pattern:
        return False
    return re.search(pattern, candidate_title, re.IGNORECASE) is not None


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
    local_bitrate: int | None = None,
    local_source_type: str = "",
) -> ComparisonResult:
    config = get_config()
    parsed = parse_release_title(candidate_title)
    uploader_health = _uploader_health_score(parsed.uploader or parsed.group)
    reliability = indexer_reliability if indexer_reliability is not None else uploader_health
    candidate_health = score_release_health(candidate_title, candidate_size, uploader_health=reliability)
    local_health = score_local_media_health(
        resolution=local_resolution or "",
        codec=local_codec or "",
        bitrate=local_bitrate,
        source_type=local_source_type or "",
        file_size=local_size,
    )

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
            media_health_score=candidate_health.score,
            media_health_rating=candidate_health.rating,
            media_health_reasons=candidate_health.reasons,
        )

    if candidate_size <= 0:
        return _reject("Candidate has no size information")

    cand_res = parsed.resolution or "unknown"
    cand_res_rank = get_resolution_rank(cand_res)
    local_res_rank = get_resolution_rank(local_resolution)
    candidate_good_upgrade = (
        local_health.rating in {"Risky", "Reject"}
        and cand_res_rank >= max(local_res_rank, 3)
        and parsed.source in {"web-dl", "webrip", "bluray", "remux"}
        and not parsed.is_low_quality_source
    )
    size_increase_pct = ((candidate_size - local_size) / max(local_size, 1)) * 100
    quality_upgrade_allows_larger = (
        bool(config.comparison.allow_size_increase_for_low_quality)
        and candidate_good_upgrade
        and candidate_size <= int(config.comparison.max_quality_upgrade_size_gb * 1024 * 1024 * 1024)
        and size_increase_pct <= config.comparison.max_size_increase_percent_for_quality_upgrade
    )

    if candidate_size >= local_size and not quality_upgrade_allows_larger:
        diff_mb = (candidate_size - local_size) / 1_048_576
        return _reject(f"Candidate is not smaller (+{diff_mb:.0f} MB vs local)")

    if parsed.has_dolby_vision and config.comparison.avoid_dolby_vision:
        if not (parsed.has_hdr_fallback and config.comparison.allow_dolby_vision_with_hdr_fallback):
            return _reject("Dolby Vision release blocked by compatibility safety mode")

    if parsed.has_hardcoded_subs and config.comparison.reject_hardcoded_subs:
        return _reject("Hardcoded subtitle marker blocked by subtitle safety rules")

    if parsed.is_dual_audio and config.comparison.reject_dual_audio:
        return _reject("Dual-audio release blocked by language safety rules")

    if parsed.is_multi_audio and config.comparison.reject_multi_audio:
        return _reject("Multi-audio release blocked by language safety rules")

    preferred_language = (config.comparison.preferred_language or "").strip().lower()
    detected_languages = [lang.lower() for lang in (parsed.languages or [])]
    explicit_audio_languages = [lang for lang in detected_languages if lang != "multi"]
    if config.comparison.require_english_audio and preferred_language == "english":
        if explicit_audio_languages and "english" not in explicit_audio_languages and "multi" not in detected_languages:
            return _reject(
                f"English audio required; detected explicit non-English audio markers: {','.join(explicit_audio_languages)}"
            )

    min_size_bytes = config.comparison.minimum_file_size_mb * 1_048_576
    if min_size_bytes > 0 and candidate_size < min_size_bytes:
        return _reject(
            f"Candidate size {candidate_size / 1_048_576:.0f} MB is below "
            f"minimum {config.comparison.minimum_file_size_mb} MB threshold"
        )

    if "candidate_is_suspiciously_small" in candidate_health.reasons:
        return _reject("candidate_is_suspiciously_small")

    if parsed.is_low_quality_source:
        return _reject("candidate_is_low_quality")

    savings_bytes = local_size - candidate_size
    savings_pct = (savings_bytes / max(local_size, 1)) * 100

    if candidate_age_days is not None and config.comparison.max_candidate_age_days > 0:
        if candidate_age_days > config.comparison.max_candidate_age_days:
            return _reject(f"NZB age {candidate_age_days}d exceeds max {config.comparison.max_candidate_age_days}d")

    if movie_year and parsed.year and config.comparison.require_year_match:
        if abs(int(parsed.year) - int(movie_year)) > 1:
            return _reject(f"Release year {parsed.year} does not match movie year {movie_year}")

    match_score = _title_match_score(movie_title, candidate_title) if movie_title else 75.0
    if movie_title and match_score < 70.0:
        return _reject(f"Title match confidence too low ({match_score:.0f}%)")

    if savings_pct < config.comparison.min_savings_percent and not quality_upgrade_allows_larger:
        return _reject(f"Savings {savings_pct:.1f}% < minimum {config.comparison.min_savings_percent}%")

    if cand_res_rank < local_res_rank:
        if not config.comparison.allow_resolution_downgrade:
            return _reject(f"Resolution downgrade {local_resolution}->{cand_res} not allowed")
        if savings_pct < config.comparison.downgrade_min_savings_percent:
            return _reject(
                f"Resolution downgrade requires {config.comparison.downgrade_min_savings_percent}% savings, "
                f"got {savings_pct:.1f}%"
            )

    if config.comparison.reject_upscaled and re.search(r"\b(upscaled|upscale|ds4k)\b", candidate_title, re.IGNORECASE):
        if cand_res_rank >= local_res_rank:
            return _reject("Upscaled release rejected by safety rules")

    score = savings_pct
    if quality_upgrade_allows_larger:
        score = 12.0 + min(35.0, (candidate_health.score - local_health.score) * 0.8)

    if cand_res_rank >= 4 and cand_res_rank > local_res_rank:
        score += 50.0

    if preferred_language:
        has_preferred_language = preferred_language in detected_languages
        non_preferred_languages = [lang for lang in detected_languages if lang not in {preferred_language, "multi"}]
        if detected_languages:
            if not has_preferred_language and "multi" not in detected_languages:
                return _reject(
                    f"Preferred language '{preferred_language}' not found in release tags: {','.join(detected_languages)}"
                )
            if non_preferred_languages:
                score -= 3.0
            score += 5.0
        elif preferred_language == "english":
            explicit_non_english = [
                lang for lang in ["italian", "french", "german", "spanish", "russian"]
                if _has_explicit_language_marker(candidate_title, lang)
            ]
            if explicit_non_english and not _has_explicit_language_marker(candidate_title, "english"):
                return _reject(f"Non-English language marker detected in release title: {','.join(explicit_non_english)}")
            score += 2.0

    cand_codec = normalize_codec(parsed.video_codec or "")
    codec_delta = get_codec_rank(cand_codec) - get_codec_rank(normalize_codec(local_codec))
    score += codec_delta * 0.5
    if cand_res_rank > local_res_rank:
        score += 20.0
    if cand_codec in [c.lower() for c in config.comparison.preferred_codecs]:
        score += 10.0

    age_days = candidate_age_days if candidate_age_days is not None else parsed.release_age_days
    stale_days = int(getattr(config.quality, "stale_release_days", 30) or 30)
    if age_days is not None:
        if age_days > stale_days:
            score -= min(35.0, (age_days - stale_days) / 10)
        elif age_days > 7:
            score -= (age_days - 7) * 0.3
        else:
            score += 2.0

    if uploader_health < 0.3:
        return _reject(f"Uploader quality too low ({uploader_health:.2f})")
    score += uploader_health * 10.0
    score += (candidate_health.score - 50.0) * 0.15

    size_score = max(0.0, min(100.0, savings_pct * 2.0 if not quality_upgrade_allows_larger else 60.0))
    codec_score = max(0.0, min(100.0, 55.0 + codec_delta * 12.0))
    if cand_res_rank == local_res_rank:
        resolution_score = 100.0
    elif cand_res_rank > local_res_rank:
        resolution_score = 92.0
    else:
        resolution_score = 30.0

    language_score = 100.0
    if parsed.languages and preferred_language:
        if preferred_language in detected_languages:
            language_score = 95.0
            if any(lang not in {preferred_language, "multi"} for lang in detected_languages):
                language_score = 80.0
        elif "multi" in detected_languages:
            language_score = 70.0
        else:
            language_score = 20.0

    source_score = _source_quality_score(parsed.source)
    reliability_score = max(0.0, min(100.0, reliability * 100.0))
    confidence_breakdown = {
        "size_reduction": round(size_score, 2),
        "codec": round(codec_score, 2),
        "resolution": round(resolution_score, 2),
        "source": round(source_score, 2),
        "language": round(language_score, 2),
        "match_certainty": round(match_score, 2),
        "indexer_reliability": round(reliability_score, 2),
        "media_health": round(candidate_health.score, 2),
    }
    confidence_score = round(
        size_score * 0.20
        + codec_score * 0.11
        + resolution_score * 0.15
        + source_score * 0.12
        + language_score * 0.12
        + match_score * 0.17
        + reliability_score * 0.06
        + candidate_health.score * 0.07,
        2,
    )
    if confidence_score < config.comparison.minimum_confidence_score:
        result = _reject(f"Confidence {confidence_score:.0f} < minimum {config.comparison.minimum_confidence_score:.0f}")
        result.confidence_score = confidence_score
        result.confidence_breakdown = confidence_breakdown
        return result

    notes = list(candidate_health.reasons)
    if local_health.rating in {"Risky", "Reject"}:
        notes.append("existing_copy_is_low_quality")
    if cand_res_rank > local_res_rank:
        notes.append("candidate_improves_resolution")
    if codec_delta > 0:
        notes.append(f"Codec upgrade: {local_codec}->{cand_codec}")
    if get_source_rank(parsed.source) >= 75:
        notes.append("candidate_has_good_source")
    if get_source_rank(parsed.source) > get_source_rank(local_source_type):
        notes.append("candidate_improves_source")
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
        notes="; ".join(dict.fromkeys(notes)),
        confidence_score=confidence_score,
        confidence_breakdown=confidence_breakdown,
        media_health_score=candidate_health.score,
        media_health_rating=candidate_health.rating,
        media_health_reasons=candidate_health.reasons,
    )


def rank_candidates(
    local_size: int,
    local_resolution: str,
    local_codec: str,
    candidates: list[dict],
) -> list[tuple[dict, ComparisonResult]]:
    results = [
        (c, compare_release(local_size, local_resolution, local_codec, c["size"], c["release_title"], c.get("age_days")))
        for c in candidates
    ]
    accepted = [(c, r) for c, r in results if r.decision == "accept"]
    accepted.sort(key=lambda x: x[1].score, reverse=True)
    return accepted
