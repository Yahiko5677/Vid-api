"""
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
    series_patterns = [
        (r'[Ss](\d{1,2})[Ee](\d{1,3})',                2),  # S01E01
        (r'[Ss](\d{1,2})\s+[Ee](\d{1,3})',             2),  # S02 E23
        (r'[Ss]eason\s*(\d{1,2}).*?[Ee]p?\s*(\d{1,3})', 2),  # Season 1 Ep 1
        (r'[Ee]pisode[\s.]*(\d{1,4})',                  1),  # Episode.320
        (r'[Ee]p[\s.]+(\d{1,3})',                       1),  # Ep 04
    ]
    for pat, groups in series_patterns:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            if groups == 2:
                return int(m.group(1)), int(m.group(2))
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

def parse_title(filename: str) -> str:
    """
    Best-effort title extraction.
    Handles both formats:
      A) Title BEFORE episode:  Fairy.Tail.S02E07.480p.mkv
      B) Title AFTER episode:   [@Chan] S02 E23 Fairy Tail 1080p.mkv
      C) Movie:                 [@Chan] My Hero Academia Two Heroes (2018) 480p.mkv
    """
    # Remove extension
    name = re.sub(r'\.\w{2,4}$', '', filename)
    # Strip leading [tag] like [@Vertex_Anime]
    name = re.sub(r'^\s*\[[^\]]*\]\s*', '', name).strip()

    # Detect Format B: starts with SxxExx
    if re.match(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}', name):
        name = re.sub(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}\s*', '', name)
    else:
        # Format A/C: strip episode markers and everything after
        name = re.sub(
            r'[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}.*'
            r'|[Ss]eason\s*\d+.*'
            r'|[Ee]p?\d+.*',
            '', name, flags=re.IGNORECASE
        )

    # Strip all remaining [..] and (..) blocks (quality tags, year, etc.)
    name = re.sub(r'\[[^\]]*\]|\([^\)]*\)', '', name)

    # Strip quality/technical junk words
    name = _JUNK_RE.sub('', name)

    # Strip decimal patterns like "5.1" leftover from audio tags
    name = re.sub(r'\b\d+\.\d+\b', '', name)

    # Clean separators
    name = re.sub(r'[\._\-]+', ' ', name).strip()
    # Remove trailing year
    name = re.sub(r'\s*[\(\[]?\d{4}[\)\]]?\s*$', '', name).strip()
    # Collapse multiple spaces
    name = re.sub(r'\s{2,}', ' ', name).strip()

    return name.title() if name else filename


# ── Admin filter ─────────────────────────────────────────────────────────
from pyrogram import filters as pyro_filters
from config import ADMINS

admin = pyro_filters.user(ADMINS)
