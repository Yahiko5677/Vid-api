"""
Unified metadata resolver — searches Jikan + OMDB + TMDB.

In rich mode: returns ALL results for admin to pick from (picker shown in admin.py).
Auto-fetch: fetches full details once admin picks.
"""

import logging
from services.jikan import search_jikan, get_jikan_details
from services.tmdb  import search_tmdb, get_details as get_tmdb_details
from services.omdb  import search_omdb, get_omdb_details

logger = logging.getLogger(__name__)

# Emoji prefix per type — quick visual ID
TYPE_EMOJI = {
    "TV":      "📺",
    "Movie":   "🎬",
    "OVA":     "📼",
    "ONA":     "🌐",
    "Special": "⭐",
    "movie":   "🎬",
    "tv":      "📺",
    "series":  "📺",
    "anime":   "🎌",
}

TYPE_LABEL = {
    "TV":      "TV Series",
    "Movie":   "Movie",
    "OVA":     "OVA",
    "ONA":     "ONA",
    "Special": "Special",
    "movie":   "Movie",
    "tv":      "TV Series",
    "series":  "TV Series",
    "anime":   "Anime",
}

# Source badge
SOURCE_BADGE = {
    "jikan": "🎌 MAL",
    "omdb":  "🎬 OMDB",
    "tmdb":  "🎥 TMDB",
}


def _label(result: dict) -> str:
    mt     = result.get("media_type") or result.get("type") or ""
    src    = result.get("source", "")
    year   = result.get("year", "")
    emoji  = TYPE_EMOJI.get(mt, "❓")
    lbl    = TYPE_LABEL.get(mt, mt) if mt else "?"
    score  = result.get("score")
    badge  = SOURCE_BADGE.get(src, "")

    s = emoji + " " + lbl
    if year and year != "N/A":
        s += " " + str(year)
    if score and str(score) not in ("N/A", "None", ""):
        s += " ⭐" + str(score)
    if badge:
        s += " · " + badge
    return s


async def search_all(title: str) -> list[dict]:
    """
    Search all sources. Returns unified list sorted by relevance:
    TV/Anime types first, then by score desc.
    """
    results = []

    # Jikan — anime
    try:
        jikan = await search_jikan(title)
        results.extend(jikan[:4])
    except Exception as e:
        logger.warning(f"Jikan search failed: {e}")

    # OMDB — movies + series
    try:
        omdb = await search_omdb(title)
        results.extend(omdb[:3])
    except Exception as e:
        logger.warning(f"OMDB search failed: {e}")

    # TMDB — fallback
    try:
        tmdb = await search_tmdb(title)
        for item in tmdb[:3]:
            item.setdefault("score", None)
            item.setdefault("episodes", None)
            item.setdefault("studio", None)
            item["source"] = "tmdb"
        results.extend(tmdb[:3])
    except Exception as e:
        logger.warning(f"TMDB search failed: {e}")

    # Sort: TV/anime first, then score desc, deduplicate by title+year
    seen   = set()
    unique = []
    for r in results:
        key = (r.get("title","").lower(), r.get("year",""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    def sort_key(r):
        mt = (r.get("media_type") or r.get("type") or "").lower()
        tv_first  = 0 if mt in ("tv", "anime") else 1
        score_val = float(r.get("score") or 0)
        return (tv_first, -score_val)

    return sorted(unique, key=sort_key)[:8]


async def get_full_meta(result: dict) -> dict | None:
    """Fetch full details for a picked result."""
    src = result.get("source")

    if src == "jikan":
        mal_id = result.get("mal_id")
        if mal_id:
            full = await get_jikan_details(mal_id)
            return full or result
        return result

    elif src == "omdb":
        imdb_id = result.get("imdb_id")
        if imdb_id:
            full = await get_omdb_details(imdb_id)
            return full or result
        return result

    elif src == "tmdb":
        tmdb_id = result.get("tmdb_id")
        ct      = result.get("type", "movie")
        if tmdb_id:
            full = await get_tmdb_details(tmdb_id, ct)
            if full:
                full.setdefault("score",    None)
                full.setdefault("episodes", None)
                full.setdefault("studio",   None)
                full["source"] = "tmdb"
                return full
        return result

    return result


def result_display_text(results: list[dict]) -> str:
    """Format results list for admin picker message."""
    lines = ["<b>Select correct metadata:</b>\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Unknown")
        label = _label(r)
        lines.append(str(i) + ". <b>" + title + "</b>  " + label)
    return "\n".join(lines)


# Keep simple fetch for non-rich / fallback use
async def fetch_metadata(title: str) -> dict | None:
    """Simple auto-fetch — picks best result without showing picker."""
    results = await search_all(title)
    if not results:
        return None
    best = results[0]
    return await get_full_meta(best)
