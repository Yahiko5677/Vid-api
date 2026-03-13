"""
Unified metadata resolver.

Strategy:
  1. Try Jikan (MAL) — best for anime, no key needed
  2. If no results → fall back to TMDB

Both return the same unified dict shape so post.py doesn't care which
source was used:

{
    source       : "jikan" | "tmdb"
    title        : str
    year         : str
    genres       : list[str]
    synopsis     : str
    score        : str | None      (MAL score; None for TMDB)
    episodes     : str | None      (ep count; None for TMDB movies)
    studio       : str | None
    poster_url   : str | None
    type         : "anime" | "movie" | "tv"
}
"""

import logging
from services.jikan import search_jikan, get_jikan_details
from services.tmdb  import search_tmdb, get_details

logger = logging.getLogger(__name__)


async def fetch_metadata(title: str) -> dict | None:
    """
    Try Jikan first. If no result, fall back to TMDB.
    Returns unified meta dict or None.
    """
    # ── 1. Jikan ──────────────────────────────────────────────
    try:
        jikan_results = await search_jikan(title)
        if jikan_results:
            best = jikan_results[0]
            # Get full details (includes studios, full genres)
            if best.get("mal_id"):
                full = await get_jikan_details(best["mal_id"])
                if full:
                    logger.info(f"✅ Metadata from Jikan: {full['title']}")
                    return full
            logger.info(f"✅ Metadata from Jikan (partial): {best['title']}")
            return best
    except Exception as e:
        logger.warning(f"Jikan failed, trying TMDB: {e}")

    # ── 2. TMDB fallback ──────────────────────────────────────
    try:
        tmdb_results = await search_tmdb(title)
        if tmdb_results:
            best    = tmdb_results[0]
            details = await get_details(best["tmdb_id"], best["type"])
            if details:
                # Normalize to unified shape
                details.setdefault("score",    None)
                details.setdefault("episodes", None)
                details.setdefault("studio",   None)
                details["source"] = "tmdb"
                logger.info(f"✅ Metadata from TMDB: {details['title']}")
                return details
    except Exception as e:
        logger.warning(f"TMDB also failed: {e}")

    logger.warning(f"No metadata found for: {title}")
    return None
