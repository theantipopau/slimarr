"""Local media probing using pymediainfo for bitrate/stream enrichment."""
from __future__ import annotations

import os
from typing import Any


def _resolution_from_height(height: int | None) -> str:
    if not height:
        return ""
    if height >= 2000:
        return "2160p"
    if height >= 1000:
        return "1080p"
    if height >= 700:
        return "720p"
    if height >= 500:
        return "480p"
    return ""


def probe_media_file(path: str) -> dict[str, Any]:
    """Return best-effort media details for a local file.

    Output keys:
    - bitrate_kbps: int | None
    - video_codec: str | None
    - audio_codec: str | None
    - resolution: str | None
    """
    if not path or not os.path.isfile(path):
        return {}

    try:
        from pymediainfo import MediaInfo
    except Exception:
        return {}

    try:
        info = MediaInfo.parse(path)
    except Exception:
        return {}

    video_track = None
    audio_track = None
    general_track = None
    for track in info.tracks:
        t = (getattr(track, "track_type", "") or "").lower()
        if t == "general" and general_track is None:
            general_track = track
        elif t == "video" and video_track is None:
            video_track = track
        elif t == "audio" and audio_track is None:
            audio_track = track

    bitrate = None
    for track in (video_track, general_track):
        if track is None:
            continue
        raw = getattr(track, "bit_rate", None)
        if raw:
            try:
                bitrate = int(float(raw) / 1000)
                break
            except Exception:
                continue

    video_codec = None
    if video_track is not None:
        video_codec = (
            getattr(video_track, "format", None)
            or getattr(video_track, "codec_id", None)
            or getattr(video_track, "format_profile", None)
        )

    audio_codec = None
    if audio_track is not None:
        audio_codec = getattr(audio_track, "format", None) or getattr(audio_track, "codec_id", None)

    height = None
    if video_track is not None:
        raw_h = getattr(video_track, "height", None)
        if raw_h is not None:
            try:
                height = int(raw_h)
            except Exception:
                height = None
    resolution = _resolution_from_height(height)

    return {
        "bitrate_kbps": bitrate,
        "video_codec": str(video_codec).lower() if video_codec else None,
        "audio_codec": str(audio_codec).lower() if audio_codec else None,
        "resolution": resolution or None,
    }
