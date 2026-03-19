"""
# v5 - 2026-03-20
helper_func.py

encode / decode — 100% compatible with your existing File Store Bot.
Filename parsers — quality, episode, title extraction.
"""

import base64
import re


# ── Core encode / decode ─────────────────────────────────────────────────

async def encode(string: str) -> str:
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return (base64_bytes.decode("ascii")).strip("=")


async def decode(base64_string: str) -> str:
    base64_string = base64_string.strip("=")
    padding = 4 - len(base64_string) % 4
    if padding != 4:
        base64_string += "=" * padding
    base64_bytes = base64_string.encode("ascii")
    return base64.urlsafe_b64decode(base64_bytes).decode("ascii")


# ── Filename parsers ─────────────────────────────────────────────────────

QUALITY_PATTERNS = [
    (r'2160p?|4k|uhd',  '2160p'),
    (r'1080p?',         '1080p'),
    (r'720p?',          '720p'),
    (r'480p?',          '480p'),
    (r'360p?',          '360p'),
]

EPISODE_PATTERNS = [
    r'[Ss](\d{1,2})[Ee](\d{1,3})',               # S01E01
    r'[Ss](\d{1,2})\s+[Ee](\d{1,3})',            # S02 E23
    r'[Ss]eason\s*(\d{1,2}).*[Ee]p?\s*(\d{1,3})', # Season 1 Ep 1
    r'[Ee]p?isode\s*(\d{1,3})',                   # Episode 01
    r'[Ee](\d{1,3})',                              # E01 (last resort)
]

# Known anime movie title keywords — signals episode=0 (movie)
QUALITY_PATTERNS = [
    (r'2160p?|4k|uhd',  '2160p'),
    (r'1080p?',         '1080p'),
    (r'720p?',          '720p'),
    (r'480p?',          '480p'),
    (r'360p?',          '360p'),
]


def parse_quality(filename: str) -> str | None:
    fn = filename.lower()
    for pattern, label in QUALITY_PATTERNS:
        if re.search(pattern, fn):
            return label
    return None


# Generic movie keywords — title-independent
MOVIE_KEYWORDS = ["the movie", "- movie", ".movie.", "_movie_", "(movie)", " film "]


def parse_episode(filename: str):
    """
    Returns (season, episode) as ints.
    Returns (1, 0) for movies — episode=0 = movie.

    Priority:
    1. SxxExx / Episode.xx / Ep.xx  → series (always wins)
    2. Generic movie keyword         → movie
    3. Has year (1970-2030) + no Exx → movie
    4. Standalone Exx               → series
    5. Nothing found                → movie/standalone
    """
    name_lower = filename.lower()

    # ── 1. Series patterns (highest priority) ─────────────────
    # ── 1. Series patterns (highest priority) ─────────────────
    series_patterns = [
        (r'\[S(\d{1,2})-E(\d{1,3})\]',              2),  # [S07-E45]
        (r'\[S(\d{1,2})\]\s*\[E(\d{1,3})\]',        2),  # [S07][E45]
        (r'\[S(\d{1,2})\].*?\bE(\d{1,3})\b',        2),  # [S07] ... E45
        (r'\[S(\d{1,2})E(\d{1,3})\]',               2),  # [S07E45]
        (r'[Ss](\d{1,2})[Ee](\d{1,3})',             2),  # S01E01
        (r'[Ss](\d{1,2})\s+[Ee](\d{1,3})',          2),  # S02 E23
        (r'[Ss]eason\s*(\d{1,2}).*?[Ee]p?\s*(\d{1,3})', 2),  # Season 1 Ep 1
        (r'[Ee]pisode[\s.]*(\d{1,4})',               1),  # Episode.320
        (r'[Ee]p[\s.]+(\d{1,3})',                    1),  # Ep 04
        (r'\[S(\d{1,2})\]',                         3),  # [S07] alone
    ]
    for pat, groups in series_patterns:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            if groups == 2:
                return int(m.group(1)), int(m.group(2))
            elif groups == 3:
                return int(m.group(1)), 1
            return 1, int(m.group(1))
    # ── 2. Generic movie keywords ──────────────────────────────
    if any(kw in name_lower for kw in MOVIE_KEYWORDS):
        return 1, 0

    # ── 3. Has year + no episode number → movie ───────────────
    has_year  = bool(re.search(r'\b(19[7-9]\d|20[0-2]\d)\b', filename))
    has_exx   = bool(re.search(r'\bE\d{1,3}\b', filename, re.IGNORECASE))
    if has_year and not has_exx:
        return 1, 0

    # ── 4. Standalone Exx ─────────────────────────────────────
    m = re.search(r'\bE(\d{1,3})\b', filename, re.IGNORECASE)
    if m:
        return 1, int(m.group(1))

    # ── 5. Nothing → movie/standalone ─────────────────────────
    return 1, 0

# Compiled junk regex — strips quality/technical tokens from title
_JUNK_RE = re.compile(
    r'\b(?:2160p?|4[Kk]|[Uu][Hh][Dd]|1080p?|720p?|480p?|360p?'
    r'|BluRay|BDRip|BRRip|WEB-?DL|WEBRip|HDRip|AMZN|NF|DSNP'
    r'|HEVC|[Hx]\.?264|[Hx]\.?265|10bit|8bit'
    r'|AAC|AC3|DD[P+]?|DTS|FLAC|MP3|Atmos'
    r'|\d+\.\d+ch?|Multi[-\s]?Audio|Dual[-\s]?Audio'
    r'|ESub|MSub|Eng?|Jap?|Hin?|Tam?|Tel?'
    r'|HD\b|SD\b|FHD\b|UHD\b)\b',
    re.IGNORECASE
)


def parse_title(filename: str) -> str:
    """
    Best-effort title extraction. Returns "" if no title can be determined.
    Handles:
      A) Fairy.Tail.S02E07.480p.mkv           → Fairy Tail
      B) [@Chan] S02 E23 Fairy Tail 1080p.mkv → Fairy Tail
      C) [@Chan] Movie Title (2025) 480p.mkv  → Movie Title
      D) [S07-E45] [1080p] @Channel.mkv       → ""  (no title)
    """
    name = re.sub(r'\.\w{2,4}$', '', filename)          # remove extension
    name = re.sub(r'^(\s*\[[^\]]*\]\s*)+', '', name).strip()  # strip ALL leading [tags]
    name = re.sub(r'@\w+', '', name).strip()              # strip @handles

    # Detect Format B: starts with SxxExx — title is after
    if re.match(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}', name):
        name = re.sub(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}\s*', '', name)
    else:
        # Format A/C: strip from episode marker onward
        name = re.sub(
            r'[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}.*'
            r'|[Ss]eason\s*\d+.*'
            r'|[Ee]p?\d+.*',
            '', name, flags=re.IGNORECASE
        )

    # Strip remaining [..] (..) blocks, quality/junk tokens, decimal patterns
    name = re.sub(r'\[[^\]]*\]|\([^\)]*\)', '', name)
    name = _JUNK_RE.sub('', name)
    name = re.sub(r'\b\d+\.\d+\b', '', name)
    name = re.sub(r'[\._\-]+', ' ', name).strip()
    name = re.sub(r'\s*[\(\[]?\d{4}[\)\]]?\s*$', '', name).strip()
    name = re.sub(r'\s{2,}', ' ', name).strip()

    return name.title() if name else ""


# ── Admin filter ─────────────────────────────────────────────────────────
from pyrogram import filters as pyro_filters
from config import ADMINS

admin = pyro_filters.user(ADMINS)
