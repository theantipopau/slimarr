"""Release name parser — extracts resolution, codec, source, audio from NZB titles."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedRelease:
    title: str
    year: Optional[int] = None
    resolution: Optional[str] = None    # "2160p" | "1080p" | "720p" | "480p"
    video_codec: Optional[str] = None   # "h265" | "h264" | "av1" | "xvid"
    audio_codec: Optional[str] = None   # "atmos" | "truehd" | "dts-hd ma" | "dts" | "aac" | "dd5.1"
    source: Optional[str] = None        # "bluray" | "remux" | "web-dl" | "webrip" | "hdtv"
    hdr: Optional[str] = None           # "hdr10" | "hdr10+" | "dolby vision" | None (SDR)
    group: Optional[str] = None


# Resolution priority (higher = better)
RESOLUTION_RANK: dict[str, int] = {
    "2160p": 4, "4k": 4,
    "1080p": 3,
    "720p": 2,
    "480p": 1,
    "sd": 0,
}

# Codec efficiency ranking
CODEC_RANK: dict[str, int] = {
    "av1": 100,
    "h265": 80, "hevc": 80, "x265": 80,
    "h264": 50, "x264": 50, "avc": 50,
    "mpeg2": 20,
    "xvid": 10, "divx": 10,
}


def parse_release_title(title: str) -> ParsedRelease:
    result = ParsedRelease(title=title)
    t = title.lower()

    # Year
    ym = re.search(r'[\.\s\(]((?:19|20)\d{2})[\.\s\)]', title)
    if ym:
        result.year = int(ym.group(1))

    # Resolution
    if re.search(r'2160p|4k\b|uhd\b', t):
        result.resolution = "2160p"
    elif re.search(r'1080p|1080i', t):
        result.resolution = "1080p"
    elif re.search(r'720p', t):
        result.resolution = "720p"
    elif re.search(r'480p|576p|\bsd\b', t):
        result.resolution = "480p"

    # Video codec
    if re.search(r'\bav1\b', t):
        result.video_codec = "av1"
    elif re.search(r'x\.?265|h\.?265|hevc', t):
        result.video_codec = "h265"
    elif re.search(r'x\.?264|h\.?264|\bavc\b', t):
        result.video_codec = "h264"
    elif re.search(r'\bxvid\b|\bdivx\b', t):
        result.video_codec = "xvid"
    elif re.search(r'mpeg-?2', t):
        result.video_codec = "mpeg2"

    # Source
    if re.search(r'\bremux\b', t):
        result.source = "remux"
    elif re.search(r'blu-?ray|bdremux|bdrip', t):
        result.source = "bluray"
    elif re.search(r'web-?dl|webdl', t):
        result.source = "web-dl"
    elif re.search(r'web-?rip|webrip', t):
        result.source = "webrip"
    elif re.search(r'\bhdtv\b', t):
        result.source = "hdtv"
    elif re.search(r'\bdvdrip\b|\bdvd\b', t):
        result.source = "dvdrip"
    elif re.search(r'\bweb\b', t):
        result.source = "web-dl"

    # Audio codec
    if re.search(r'\batmos\b', t):
        result.audio_codec = "atmos"
    elif re.search(r'truehd|true-hd', t):
        result.audio_codec = "truehd"
    elif re.search(r'dts-?hd[\. ]?ma', t):
        result.audio_codec = "dts-hd ma"
    elif re.search(r'dts-?hd', t):
        result.audio_codec = "dts-hd"
    elif re.search(r'\bdts\b', t):
        result.audio_codec = "dts"
    elif re.search(r'dd[\+p]?[\. ]?5[\. ]?1|ac3|dolby.?digital', t):
        result.audio_codec = "dd5.1"
    elif re.search(r'\baac\b', t):
        result.audio_codec = "aac"
    elif re.search(r'\bflac\b', t):
        result.audio_codec = "flac"

    # HDR
    if re.search(r'dolby[\. ]?vision|dovi|\bdv\b', t):
        result.hdr = "dolby vision"
    elif re.search(r'hdr10\+|hdr10plus', t):
        result.hdr = "hdr10+"
    elif re.search(r'hdr10|\bhdr\b', t):
        result.hdr = "hdr10"
    elif re.search(r'\bhlg\b', t):
        result.hdr = "hlg"

    # Release group
    gm = re.search(r'-([a-zA-Z0-9]{2,20})(?:\.[a-z]{2,4})?$', title)
    if gm:
        result.group = gm.group(1)

    return result


def normalize_resolution(res: str) -> str:
    if not res:
        return "unknown"
    r = res.lower().strip()
    mapping = {"4k": "2160p", "uhd": "2160p", "2160": "2160p",
               "1080": "1080p", "720": "720p", "480": "480p",
               "576": "480p", "sd": "480p"}
    if r in mapping:
        return mapping[r]
    return r if r.endswith("p") else f"{r}p"


def normalize_codec(codec: str) -> str:
    if not codec:
        return "unknown"
    c = codec.lower().strip()
    aliases = {"hevc": "h265", "x265": "h265", "avc": "h264", "x264": "h264", "divx": "xvid"}
    return aliases.get(c, c)


def get_resolution_rank(resolution: str) -> int:
    return RESOLUTION_RANK.get(normalize_resolution(resolution), 0)


def get_codec_rank(codec: str) -> int:
    return CODEC_RANK.get(normalize_codec(codec), 0)
