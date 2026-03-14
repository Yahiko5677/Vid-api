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

# Season+episode patterns — ordered most specific first
EPISODE_PATTERNS = [
    r'[Ss](\d{1,2})[Ee](\d{1,3})',               # S01E01
    r'[Ss](\d{1,2})\s+[Ee](\d{1,3})',            # S02 E23 (space between)
    r'[Ss]eason\s*(\d{1,2}).*[Ee]p?\s*(\d{1,3})', # Season 1 Ep 1
    r'[Ee]p?isode\s*(\d{1,3})',                   # Episode 01
    r'[Ee](\d{1,3})',                              # E01 (last resort)
]

# Junk to always strip from title
_JUNK = (
    r'2160p?|4[Kk]|[Uu][Hh][Dd]|1080p?|720p?|480p?|360p?'
    r'|BluRay|WEB-?DL|HDRip|HEVC|x264|x265|10bit|AAC|DD5\.1'
    r'|MULTI|DUAL|SUB|DUB|ENG|JAP|HIN'
    r'|\[[^\]]*\]|\([^\)]*\)'
)


def parse_quality(filename: str) -> str | None:
    fn = filename.lower()
    for pattern, label in QUALITY_PATTERNS:
        if re.search(pattern, fn):
            return label
    return None


def parse_episode(filename: str):
    """Returns (season, episode) as ints. Season defaults to 1 if not found."""
    for pat in EPISODE_PATTERNS:
        m = re.search(pat, filename, re.IGNORECASE)
        if m:
            if len(m.groups()) == 2:
                return int(m.group(1)), int(m.group(2))
            elif len(m.groups()) == 1:
                return 1, int(m.group(1))
    return None, None


def parse_title(filename: str) -> str:
    """
    Best-effort title extraction. Handles two formats:

    Format A — title BEFORE episode:
        Fairy.Tail.S02E07.480p.mkv  →  Fairy Tail

    Format B — title AFTER episode (common in channel-tagged files):
        [@Vertex_Anime] S02 E23 Fairy tail 1080p.mkv  →  Fairy Tail
    """
    # Remove extension
    name = re.sub(r'\.\w{2,4}$', '', filename)
    # Strip leading [tag] like [@Vertex_Anime]
    name = re.sub(r'^\s*\[[^\]]*\]\s*', '', name).strip()

    # Detect format B: starts with SxxExx or Sxx Exx
    ep_at_start = re.match(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}', name)
    if ep_at_start:
        # Title is AFTER the episode marker
        # Strip everything up to and including the episode marker
        name = re.sub(r'^[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}\s*', '', name)
    else:
        # Format A: title BEFORE episode — strip from episode marker onward
        name = re.sub(
            r'[Ss]\d{1,2}[\s_]?[Ee]\d{1,3}.*'
            r'|[Ss]eason\s*\d+.*'
            r'|[Ee]p?\d+.*',
            '', name, flags=re.IGNORECASE
        )

    # Strip quality/junk from whatever remains
    name = re.sub(_JUNK, '', name, flags=re.IGNORECASE)
    # Clean separators
    name = re.sub(r'[\._\-]+', ' ', name).strip()
    # Remove trailing year
    name = re.sub(r'\s*[\(\[]?\d{4}[\)\]]?\s*$', '', name).strip()

    return name.title() if name else filename


# ── Admin filter ─────────────────────────────────────────────────────────
from pyrogram import filters as pyro_filters
from config import ADMINS

admin = pyro_filters.user(ADMINS)
