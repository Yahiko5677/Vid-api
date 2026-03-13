"""
Jikan v4 service — MyAnimeList metadata (no API key required).

Endpoint: https://api.jikan.moe/v4
Rate limit: 3 req/sec, 60 req/min  →  we add a small sleep between calls.

Returns unified meta dict:
{
    source      : "jikan"
    mal_id      : int
    title       : str
    year        : str
    genres      : list[str]
    synopsis    : str
    score       : str   (e.g. "8.42")
    episodes    : str   (e.g. "24" or "Unknown")
    studio      : str
    poster_url  : str | None
    type        : "anime"
}
"""

import asyncio
import aiohttp
import logging

logger  = logging.getLogger(__name__)
BASE    = "https://api.jikan.moe/v4"
TIMEOUT = aiohttp.ClientTimeout(total=12)


async def search_jikan(title: str) -> list[dict]:
    """Search MAL for anime. Returns up to 5 results."""
    url    = f"{BASE}/anime"
    params = {"q": title, "limit": 5, "sfw": False}

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get(url, params=params) as r:
                if r.status != 200:
                    logger.warning(f"Jikan search HTTP {r.status}")
                    return []
                data = await r.json()
                results = []
                for item in data.get("data", []):
                    results.append(_parse_item(item))
                return results
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
    genres  += [g["name"] for g in item.get("themes", [])]     # add themes too
    studios  = [s["name"] for s in item.get("studios", [])]
    score    = item.get("score")
    episodes = item.get("episodes")
    aired    = item.get("aired", {}).get("prop", {}).get("from", {})
    year     = str(aired.get("year", "")) if aired.get("year") else (
               item.get("year") or item.get("season", "")
    )
    images   = item.get("images", {})
    poster   = (
        images.get("jpg", {}).get("large_image_url")
        or images.get("jpg", {}).get("image_url")
        or images.get("webp", {}).get("large_image_url")
    )
    synopsis = item.get("synopsis") or ""
    # trim long synopsis
    if len(synopsis) > 350:
        synopsis = synopsis[:347] + "..."

    return {
        "source":     "jikan",
        "mal_id":     item.get("mal_id"),
        "type":       "anime",
        "title":      item.get("title_english") or item.get("title") or "",
        "year":       str(year) if year else "N/A",
        "genres":     genres[:4],
        "synopsis":   synopsis,
        "score":      f"{score:.2f}" if isinstance(score, float) else (str(score) if score else "N/A"),
        "episodes":   str(episodes) if episodes else "?",
        "studio":     ", ".join(studios[:2]) if studios else "N/A",
        "poster_url": poster,
    }
