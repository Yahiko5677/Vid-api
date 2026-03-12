"""
encode / decode logic — 100% compatible with your existing File Store Bot.

Encode:  string  → base64url  (used when generating share links)
Decode:  base64url → string   (used on /start deep-link)

Link format:
    Single file : get-{msg_id * abs(channel_id)}
    Batch range : get-{start * abs(channel_id)}-{end * abs(channel_id)}

Share link   : https://t.me/{FILE_STORE_BOT}?start={base64_string}
"""

import base64
import re
from config import FILE_STORE_BOT, FILE_STORE_CHANNEL


# ── Core encode / decode ─────────────────────────────────────────────────

async def encode(string: str) -> str:
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return (base64_bytes.decode("ascii")).strip("=")


async def decode(base64_string: str) -> str:
    base64_string = base64_string.strip("=")
    # Pad to multiple of 4
    padding = 4 - len(base64_string) % 4
    if padding != 4:
        base64_string += "=" * padding
    base64_bytes = base64_string.encode("ascii")
    return base64.urlsafe_b64decode(base64_bytes).decode("ascii")


# ── Link generators (compatible with File Store Bot) ─────────────────────

async def get_link(msg_id: int) -> str:
    """Single-file share link."""
    string = f"get-{msg_id * abs(FILE_STORE_CHANNEL)}"
    b64    = await encode(string)
    return f"https://t.me/{FILE_STORE_BOT}?start={b64}"


async def get_batch_link(start_id: int, end_id: int) -> str:
    """Batch-range share link."""
    string = f"get-{start_id * abs(FILE_STORE_CHANNEL)}-{end_id * abs(FILE_STORE_CHANNEL)}"
    b64    = await encode(string)
    return f"https://t.me/{FILE_STORE_BOT}?start={b64}"


# ── Filename parsers ─────────────────────────────────────────────────────

QUALITY_PATTERNS = [
    (r'2160p?|4k|uhd',  '2160p'),
    (r'1080p?',         '1080p'),
    (r'720p?',          '720p'),
    (r'480p?',          '480p'),
    (r'360p?',          '360p'),
]

EPISODE_PATTERNS = [
    r'[Ss](\d{1,2})[Ee](\d{1,3})',           # S01E01
    r'[Ss]eason\s*(\d{1,2}).*[Ee]p?\s*(\d{1,3})',  # Season 1 Ep 1
    r'[Ee]p?isode\s*(\d{1,3})',              # Episode 01 (no season)
    r'[Ee](\d{1,3})',                         # E01
]


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
    Best-effort title extraction.
    Strips quality tags, episode markers, year, extension, dots/underscores.
    """
    name = re.sub(r'\.\w{2,4}$', '', filename)          # remove extension
    name = re.sub(
        r'[Ss]\d{1,2}[Ee]\d{1,3}.*|[Ss]eason\s*\d+.*|[Ee]p?\d+.*|'
        r'2160p?|4[Kk]|[Uu][Hh][Dd]|1080p?|720p?|480p?|360p?|'
        r'BluRay|WEB-?DL|HDRip|HEVC|x264|x265|10bit|AAC|DD5\.1|'
        r'\[\w+\]|\(\w+\)',
        '', name, flags=re.IGNORECASE
    )
    name = re.sub(r'[\._\-]+', ' ', name).strip()
    # Remove trailing year like (2024) or .2024.
    name = re.sub(r'\s*[\(\[]?\d{4}[\)\]]?\s*$', '', name).strip()
    return name.title() if name else filename


# ── Admin filter ─────────────────────────────────────────────────────────
from pyrogram import filters as pyro_filters
from config import ADMINS

admin = pyro_filters.user(ADMINS)
