"""Media health scoring for local files and candidate releases."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.parser import ParsedRelease, get_codec_rank, get_resolution_rank, get_source_rank, parse_release_title


@dataclass
class MediaHealth:
    rating: str
    score: float
    reasons: list[str] = field(default_factory=list)
    badges: list[str] = field(default_factory=list)


def _rating(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Acceptable"
    if score >= 30:
        return "Risky"
    return "Reject"


def _suspicious_size(parsed: ParsedRelease, size_bytes: int) -> bool:
    size_mb = size_bytes / 1_048_576 if size_bytes else 0
    if parsed.resolution == "2160p":
        return size_mb < 2500
    if parsed.resolution == "1080p":
        return size_mb < 700
    if parsed.resolution == "720p":
        return size_mb < 350
    return size_mb > 0 and size_mb < 200


def score_release_health(
    release_title: str,
    size_bytes: int = 0,
    *,
    uploader_health: float = 0.5,
) -> MediaHealth:
    parsed = parse_release_title(release_title)
    score = 50.0
    reasons: list[str] = []
    badges: list[str] = []

    res_rank = get_resolution_rank(parsed.resolution or "")
    source_rank = get_source_rank(parsed.source)
    codec_rank = get_codec_rank(parsed.video_codec or "")

    score += (res_rank - 2) * 8
    score += (source_rank - 50) * 0.45
    score += (codec_rank - 50) * 0.12
    score += (max(0.0, min(1.0, uploader_health)) - 0.5) * 12

    if parsed.is_low_quality_source:
        score -= 45
        reasons.append("candidate_has_bad_source")
        badges.append("Bad source")
    elif parsed.source in {"web-dl", "bluray", "remux"}:
        score += 12
        reasons.append("candidate_has_good_source")
        badges.append(parsed.source.upper())
    elif parsed.source == "webrip":
        reasons.append("candidate_has_unknown_quality")
        badges.append("WEBRip")
    else:
        reasons.append("candidate_has_unknown_quality")

    if _suspicious_size(parsed, size_bytes):
        score -= 35
        reasons.append("candidate_is_suspiciously_small")
        badges.append("Tiny encode")

    if parsed.has_dolby_vision and not parsed.has_hdr_fallback:
        score -= 18
        reasons.append("candidate_has_dv_risk")
        badges.append("DV risk")
    elif parsed.hdr:
        badges.append(parsed.hdr.upper())

    if parsed.has_hardcoded_subs:
        score -= 20
        reasons.append("candidate_has_subtitle_risk")
        badges.append("Hardcoded subs")

    if parsed.languages:
        badges.extend(lang.upper() for lang in parsed.languages[:3])

    if parsed.proper:
        score += 3
        badges.append("PROPER")
    if parsed.repack:
        score += 2
        badges.append("REPACK")

    score = round(max(0.0, min(100.0, score)), 2)
    return MediaHealth(rating=_rating(score), score=score, reasons=reasons, badges=badges)


def score_local_media_health(
    *,
    resolution: str = "",
    codec: str = "",
    bitrate: int | None = None,
    source_type: str = "",
    file_size: int | None = None,
) -> MediaHealth:
    score = 55.0
    reasons: list[str] = []
    badges: list[str] = []

    res_rank = get_resolution_rank(resolution or "")
    codec_rank = get_codec_rank(codec or "")
    source_rank = get_source_rank(source_type)
    score += (res_rank - 2) * 10
    score += (codec_rank - 50) * 0.1

    if source_type:
        score += (source_rank - 50) * 0.4

    if resolution in {"480p", "720p", "sd"}:
        score -= 18 if resolution == "720p" else 30
        reasons.append("existing_copy_is_low_quality")
        badges.append("Low resolution")

    if source_type in {"cam", "ts", "hdts", "hdcam", "telecine"}:
        score -= 45
        reasons.append("existing_copy_is_low_quality")
        badges.append("Bad source")

    if bitrate and bitrate > 0:
        if resolution == "1080p" and bitrate < 2500:
            score -= 18
            reasons.append("existing_copy_has_low_bitrate")
            badges.append("Low bitrate")
        if resolution == "720p" and bitrate < 1400:
            score -= 12
            reasons.append("existing_copy_has_low_bitrate")
            badges.append("Low bitrate")

    if file_size and resolution == "1080p" and file_size < 700 * 1_048_576:
        score -= 15
        reasons.append("existing_copy_is_suspiciously_small")
        badges.append("Tiny file")

    score = round(max(0.0, min(100.0, score)), 2)
    return MediaHealth(rating=_rating(score), score=score, reasons=sorted(set(reasons)), badges=badges)
