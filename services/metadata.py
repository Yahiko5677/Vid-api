"""
# v5 - 2026-03-20
Unified metadata resolver.

Routing by content type (selected by admin at post time):
  Anime / TV  → Jikan first → OMDB fallback
  Movie       → TMDB first  → OMDB fallback

Picker: returns all results from relevant sources for admin to choose.
"""

import logging
from services.jikan import search_jikan, get_jikan_details
from services.tmdb  import search_tmdb, get_details as get_tmdb_details
from services.omdb  import search_omdb, get_omdb_details

logger = logging.getLogger(__name__)

CONTENT_TYPES = ["anime", "tv", "movie"]

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

SOURCE_BADGE = {
    "jikan": "🎌 MAL",
    "omdb":  "🎬 OMDB",
    "tmdb":  "🎥 TMDB",
}


def _label(result: dict) -> str:
    mt    = result.get("media_type") or result.get("type") or ""
    src   = result.get("source", "")
    year  = result.get("year", "")
    emoji = TYPE_EMOJI.get(mt, "❓")
    lbl   = TYPE_LABEL.get(mt, mt) if mt else "?"
    score = result.get("score")
    badge = SOURCE_BADGE.get(src, "")

    s = emoji + " " + lbl
    if year and year not in ("N/A", ""):
        s += " " + str(year)
    if score and str(score) not in ("N/A", "None", ""):
        s += " ⭐" + str(score)
    if badge:
        s += " · " + badge
    return s


async def search_all(title: str, content_type: str = "anime") -> list[dict]:
    """
    Search based on content type:
      anime / tv → Jikan first, OMDB fallback
      movie      → TMDB first, OMDB fallback
    """
    results = []
    seen    = set()

    def _add(items):
        for r in items:
            key = (r.get("title","").lower(), r.get("year",""))
            if key not in seen:
                seen.add(key)
                results.append(r)

    if content_type in ("anime", "tv"):
        # ── Jikan (MAL) ───────────────────────────────────────
        try:
            jikan = await search_jikan(title)
            _add(jikan[:5])
        except Exception as e:
            logger.warning(f"Jikan failed: {e}")

        # ── OMDB fallback ─────────────────────────────────────
        try:
            omdb_type = "series"
            omdb = await search_omdb(title, media_type=omdb_type)
            _add(omdb[:3])
        except Exception as e:
            logger.warning(f"OMDB failed: {e}")

    else:
        # content_type == "movie"
        # ── TMDB (best for movies) ────────────────────────────
        try:
            tmdb = await search_tmdb(title, content_type="movie")
            for item in tmdb[:5]:
                item.setdefault("score",    None)
                item.setdefault("episodes", None)
                item.setdefault("studio",   None)
                item["source"] = "tmdb"
            _add(tmdb[:5])
        except Exception as e:
            logger.warning(f"TMDB failed: {e}")

        # ── OMDB fallback ─────────────────────────────────────
        try:
            omdb = await search_omdb(title, media_type="movie")
            _add(omdb[:3])
        except Exception as e:
            logger.warning(f"OMDB failed: {e}")

    return results[:8]


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
    lines = ["<b>Select correct metadata:</b>\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Unknown")
        label = _label(r)
        lines.append(str(i) + ". <b>" + title + "</b>  " + label)
    return "\n".join(lines)


async def fetch_metadata(title: str, content_type: str = "anime") -> dict | None:
    """Auto-fetch best result without showing picker."""
    results = await search_all(title, content_type)
    if not results:
        return None
    return await get_full_meta(results[0])
