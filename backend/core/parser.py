"""Release name parser — extracts resolution, codec, source, audio from NZB titles."""
from __future__ import annotations

import re
from datetime import datetime
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
    languages: list[str] = field(default_factory=list)
    audio_languages: list[str] = field(default_factory=list)
    subtitle_markers: list[str] = field(default_factory=list)
    audio_channels: Optional[str] = None
    proper: bool = False
    repack: bool = False
    is_dual_audio: bool = False
    is_multi_audio: bool = False
    has_hardcoded_subs: bool = False
    has_dolby_vision: bool = False
    has_hdr_fallback: bool = False
    is_low_quality_source: bool = False
    uploader: Optional[str] = None      # Release group/uploader name
    release_age_days: Optional[int] = None  # Days since release (if parseable)


# Resolution priority (higher = better)
RESOLUTION_RANK: dict[str, int] = {
    "2160p": 4, "4k": 4,
    "1080p": 3,
    "720p": 2,
    "480p": 1,
    "sd": 0,
}

SOURCE_RANK: dict[str, int] = {
    "cam": 5,
    "hdcam": 8,
    "ts": 10,
    "hdts": 12,
    "telecine": 20,
    "dvdrip": 35,
    "hdtv": 45,
    "webrip": 60,
    "web-dl": 75,
    "bluray": 85,
    "remux": 95,
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
    if re.search(r'\b(hd-?cam|hdcam)\b', t):
        result.source = "hdcam"
    elif re.search(r'\b(hd-?ts|hdts)\b', t):
        result.source = "hdts"
    elif re.search(r'\b(camrip|cam)\b', t):
        result.source = "cam"
    elif re.search(r'\b(telesync|tele-?sync|\bts\b)\b', t):
        result.source = "ts"
    elif re.search(r'\btelecine\b|\btc\b', t):
        result.source = "telecine"
    elif re.search(r'\bremux\b', t):
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

    channel_match = re.search(r'\b(7[._ ]?1|5[._ ]?1|2[._ ]?0|1[._ ]?0)\b', t)
    if channel_match:
        result.audio_channels = channel_match.group(1).replace("_", ".").replace(" ", ".")

    # HDR
    has_dv = re.search(r'dolby[\. ]?vision|dovi|\bdv\b', t) is not None
    has_hdr10_plus = re.search(r'hdr10\+|hdr10plus', t) is not None
    has_hdr10 = re.search(r'hdr10|\bhdr\b', t) is not None
    if has_dv:
        result.has_dolby_vision = True
        result.has_hdr_fallback = bool(has_hdr10 or has_hdr10_plus or re.search(r'\bhybrid\b', t))
        result.hdr = "dolby vision + hdr10" if result.has_hdr_fallback else "dolby vision"
    elif has_hdr10_plus:
        result.hdr = "hdr10+"
    elif has_hdr10:
        result.hdr = "hdr10"
    elif re.search(r'\bhlg\b', t):
        result.hdr = "hlg"
    elif re.search(r'\bsdr\b', t):
        result.hdr = "sdr"

    # Release group
    gm = re.search(r'-([a-zA-Z0-9]{2,20})(?:\.[a-z]{2,4})?$', title)
    if gm:
        result.group = gm.group(1)

    # Language and subtitle risk markers
    lang_patterns = {
        "english": r"\b(english|eng)\b",
        "italian": r"\b(italian|ita|trueita)\b",
        "german": r"\b(german|ger|deu)\b",
        "french": r"\b(french|fre|fr|truefrench|vff)\b",
        "spanish": r"\b(spanish|spa|esp|castellano|latino)\b",
        "russian": r"\b(russian|rus)\b",
        "korean": r"\b(korean|kor)\b",
        "japanese": r"\b(japanese|jpn)\b",
        "nordic": r"\bnordic\b",
    }
    langs = [name for name, pattern in lang_patterns.items() if re.search(pattern, t)]
    result.is_dual_audio = re.search(r"\bdual[- ._]?audio\b|\bdual\b", t) is not None
    result.is_multi_audio = re.search(r"\bmulti\b|\bmulti[- ._]?audio\b", t, re.IGNORECASE) is not None
    if result.is_multi_audio and "multi" not in langs:
        langs.append("multi")
    if result.is_dual_audio and "multi" not in langs:
        langs.append("multi")
    result.languages = langs
    result.audio_languages = [lang for lang in langs if lang != "multi"]

    subtitle_markers = []
    subtitle_patterns = {
        "korsub": r"\bkorsub\b",
        "vostfr": r"\bvostfr\b",
        "hc": r"\b(hc|hcsub|hcsubs|hardsub|hardsubs|hardcoded|subbed)\b",
    }
    for marker, pattern in subtitle_patterns.items():
        if re.search(pattern, t):
            subtitle_markers.append(marker)
    result.subtitle_markers = subtitle_markers
    result.has_hardcoded_subs = bool({"korsub", "vostfr", "hc"} & set(subtitle_markers))
    result.proper = re.search(r"\bproper\b", t) is not None
    result.repack = re.search(r"\brepack\b", t) is not None
    result.is_low_quality_source = result.source in {"cam", "ts", "hdts", "hdcam", "telecine"}
    result.uploader = parse_uploader(title)
    result.release_age_days = parse_release_age(title)

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


def get_source_rank(source: str | None) -> int:
    return SOURCE_RANK.get((source or "unknown").lower(), 50)


def parse_release_age(title: str) -> Optional[int]:
    """
    Attempt to extract release date from title and return age in days.
    Common patterns:
    - YYYY.MM.DD
    - YYYY-MM-DD
    - Month DD YYYY
    """
    t = title.lower()
    now = datetime.now()
    
    # Try ISO-like date patterns: YYYY.MM.DD or YYYY-MM-DD
    date_match = re.search(r'(\d{4})[.-](\d{1,2})[.-](\d{1,2})', title)
    if date_match:
        try:
            year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
            release_date = datetime(year, month, day)
            age = (now - release_date).days
            return max(0, age)  # Don't return negative ages
        except ValueError:
            pass
    
    # Try month name patterns: Jan 15 2023, January 15 2023, etc.
    month_names = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
        'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    for month_name, month_num in month_names.items():
        pattern = rf'{month_name}.*?(\d{{1,2}}).*?(\d{{4}})'
        match = re.search(pattern, t)
        if match:
            try:
                day = int(match.group(1))
                year = int(match.group(2))
                release_date = datetime(year, month_num, day)
                age = (now - release_date).days
                return max(0, age)
            except ValueError:
                pass
    
    return None


def parse_uploader(title: str) -> Optional[str]:
    """
    Extract uploader/group name from release title.
    Typically at the end after a dash or as the group name.
    """
    # Pattern 1: Trailing group after dash
    # Movie.Title.2023.1080p.BluRay.x264-GROUPNAME
    group_match = re.search(r'-([a-zA-Z0-9]{2,20})(?:\.[a-z]{2,4})?$', title)
    if group_match:
        return group_match.group(1)
    
    # Pattern 2: Group in brackets at end
    # Movie.Title.2023.1080p.BluRay.x264.[GROUPNAME]
    bracket_match = re.search(r'\[([a-zA-Z0-9]{2,20})\]$', title)
    if bracket_match:
        return bracket_match.group(1)
    
    # Pattern 3: Before extension if no dash
    # Movie.Title.2023.1080p.BluRay.x264.GROUPNAME.mkv
    if not group_match:
        last_part = re.search(r'([a-zA-Z0-9]{2,20})(?:\.[a-z]{2,4})?$', title)
        if last_part:
            candidate = last_part.group(1)
            # Filter out common extensions
            if candidate.lower() not in ['mkv', 'avi', 'mp4', 'wmv', 'mov']:
                return candidate
    
    return None
