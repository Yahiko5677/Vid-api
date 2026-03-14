"""
Unified metadata resolver.

Strategy:
  1. Try Jikan (MAL) with TV-type priority — best for anime
  2. Only fall back to TMDB if Jikan returns zero results at all
     (not just wrong type — if Jikan finds anything, we trust it)

This prevents TMDB returning a movie when the title is an anime series.
"""

import logging
from services.jikan import search_jikan, get_jikan_details
from services.tmdb  import search_tmdb, get_details

logger = logging.getLogger(__name__)


async def fetch_metadata(title: str) -> dict | None:
    """
    Fetch metadata. Jikan first (TV priority), TMDB only if Jikan has zero results.
    """
    # ── 1. Jikan — TV priority ────────────────────────────────
    try:
        jikan_results = await search_jikan(title)
        if jikan_results:
            best = jikan_results[0]   # already sorted TV > others, score desc
            media_type = best.get("media_type", "")
            logger.info(f"Jikan top result: '{best['title']}' [{media_type}]")

            # Get full details
            if best.get("mal_id"):
                full = await get_jikan_details(best["mal_id"])
                if full:
                    logger.info(f"✅ Metadata from Jikan: {full['title']} [{full.get('media_type','')}]")
                    return full

            logger.info(f"✅ Metadata from Jikan (partial): {best['title']}")
            return best

    except Exception as e:
        logger.warning(f"Jikan failed: {e}")

    # ── 2. TMDB fallback — only if Jikan had zero results ─────
    # (if Jikan found something but it wasn't ideal, we still trust
    #  Jikan over TMDB to avoid getting movie results for anime)
    try:
        tmdb_results = await search_tmdb(title)
        if tmdb_results:
            # Prefer TV over movie in TMDB results too
            tv_results    = [r for r in tmdb_results if r.get("type") == "tv"]
            best          = tv_results[0] if tv_results else tmdb_results[0]
            details       = await get_details(best["tmdb_id"], best["type"])
            if details:
                details.setdefault("score",      None)
                details.setdefault("episodes",   None)
                details.setdefault("studio",     None)
                details.setdefault("media_type", best.get("type", ""))
                details["source"] = "tmdb"
                logger.info(f"✅ Metadata from TMDB: {details['title']} [{best.get('type','')}]")
                return details
    except Exception as e:
        logger.warning(f"TMDB also failed: {e}")

    logger.warning(f"No metadata found for: {title}")
    return None
