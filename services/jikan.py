"""
Jikan v4 service — MyAnimeList metadata (no API key required).

Endpoint: https://api.jikan.moe/v4
Rate limit: 3 req/sec, 60 req/min

Search priority:
  1. Search with type=tv — main series only (no movies/OVAs/specials)
  2. If no TV results → search without type filter, prefer TV from results
  3. Always pick highest-scored TV type result

This prevents returning MHA Movie instead of MHA TV series.
"""

import asyncio
import aiohttp
import logging

logger  = logging.getLogger(__name__)
BASE    = "https://api.jikan.moe/v4"
TIMEOUT = aiohttp.ClientTimeout(total=12)

# Types we prefer (main series first)
TV_TYPES    = {"TV"}
AVOID_TYPES = {"Movie", "OVA", "ONA", "Special", "Music"}


async def search_jikan(title: str) -> list[dict]:
    """
    Search MAL for anime title.
    Returns TV-type results first, sorted by score descending.
    """
    # ── Pass 1: TV type only ──────────────────────────────────
    results = await _search(title, media_type="tv")

    # ── Pass 2: no type filter if pass 1 empty ────────────────
    if not results:
        results = await _search(title)

    if not results:
        return []

    # Sort: TV first, then by score descending
    def sort_key(r):
        type_score = 0 if r.get("media_type", "").lower() == "tv" else 1
        mal_score  = float(r.get("score", 0) or 0)
        return (type_score, -mal_score)

    return sorted(results, key=sort_key)


async def _search(title: str, media_type: str | None = None) -> list[dict]:
    url    = f"{BASE}/anime"
    params = {"q": title, "limit": 8, "sfw": "false"}
    if media_type:
        params["type"] = media_type

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get(url, params=params) as r:
                if r.status != 200:
                    logger.warning(f"Jikan search HTTP {r.status}")
                    return []
                data = await r.json()
                return [_parse_item(item) for item in data.get("data", [])]
        except asyncio.TimeoutError:
            logger.warning("Jikan search timed out")
            return []
        except Exception as e:
            logger.warning(f"Jikan search error: {e}")
            return []


async def get_jikan_details(mal_id: int) -> dict | None:
    """Fetch full anime details by MAL ID."""
    url = f"{BASE}/anime/{mal_id}/full"
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            await asyncio.sleep(0.4)   # respect rate limit
            async with session.get(url) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                return _parse_item(data.get("data", {}))
        except Exception as e:
            logger.warning(f"Jikan details error: {e}")
            return None


def _parse_item(item: dict) -> dict:
    genres   = [g["name"] for g in item.get("genres", [])]
    genres  += [g["name"] for g in item.get("themes", [])]
    studios  = [s["name"] for s in item.get("studios", [])]
    score    = item.get("score")
    episodes = item.get("episodes")
    aired    = item.get("aired", {}).get("prop", {}).get("from", {})
    year     = str(aired.get("year", "")) if aired and aired.get("year") else (
               str(item.get("year") or ""))

    images   = item.get("images", {})
    poster   = (
        images.get("jpg", {}).get("large_image_url")
        or images.get("jpg", {}).get("image_url")
        or images.get("webp", {}).get("large_image_url")
    )
    synopsis = item.get("synopsis") or ""
    if len(synopsis) > 350:
        synopsis = synopsis[:347] + "..."

    # Prefer English title, fall back to romaji
    title = (
        item.get("title_english")
        or item.get("title")
        or ""
    )

    media_type = item.get("type", "")

    return {
        "source":      "jikan",
        "mal_id":      item.get("mal_id"),
        "type":        "anime",
        "media_type":  media_type,          # TV / Movie / OVA / etc.
        "title":       title,
        "year":        year or "N/A",
        "genres":      genres[:4],
        "synopsis":    synopsis,
        "score":       f"{score:.2f}" if isinstance(score, float) else (str(score) if score else "N/A"),
        "episodes":    str(episodes) if episodes else "?",
        "studio":      ", ".join(studios[:2]) if studios else "N/A",
        "poster_url":  poster,
    }
