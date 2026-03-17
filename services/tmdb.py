"""
TMDB service — fetch movie/series metadata.
Returns: title, year, genres, overview, poster_url
"""

import aiohttp
import logging
from config import TMDB_API_KEY

logger = logging.getLogger(__name__)

BASE      = "https://api.themoviedb.org/3"
IMG_BASE  = "https://image.tmdb.org/t/p/w500"


async def search_tmdb(title: str, content_type: str = "auto") -> list[dict]:
    """
    Search TMDB for title.
    content_type: "movie" | "tv" | "auto"
    Returns list of results [{id, title, year, type, genres, overview, poster_url}]
    """
    if not TMDB_API_KEY:
        return []

    results = []
    types   = ["movie", "tv"] if content_type == "auto" else [content_type]

    async with aiohttp.ClientSession() as session:
        for t in types:
            url    = f"{BASE}/search/{t}"
            params = {"api_key": TMDB_API_KEY, "query": title, "language": "en-US"}
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    for item in data.get("results", [])[:5]:
                        name     = item.get("title") or item.get("name") or title
                        date_str = item.get("release_date") or item.get("first_air_date") or ""
                        year     = date_str[:4] if date_str else "N/A"
                        poster   = f"{IMG_BASE}{item['poster_path']}" if item.get("poster_path") else None
                        results.append({
                            "tmdb_id":  item["id"],
                            "type":     t,
                            "title":    name,
                            "year":     year,
                            "overview": item.get("overview", "")[:200],
                            "poster_url":   poster,
                    "backdrop_url": backdrop,
                            "genres":   [],   # filled by get_details if needed
                        })
            except Exception as e:
                logger.warning(f"TMDB search error: {e}")

    return results


async def get_details(tmdb_id: int, content_type: str) -> dict | None:
    """Fetch full details including genres."""
    if not TMDB_API_KEY:
        return None

    url = f"{BASE}/{content_type}/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                data   = await r.json()
                name   = data.get("title") or data.get("name") or ""
                date_s = data.get("release_date") or data.get("first_air_date") or ""
                genres = [g["name"] for g in data.get("genres", [])]
                poster   = f"{IMG_BASE}{data['poster_path']}" if data.get("poster_path") else None
                backdrop = f"{IMG_BASE}{data['backdrop_path']}" if data.get("backdrop_path") else None
                return {
                    "tmdb_id":    tmdb_id,
                    "type":       content_type,
                    "title":      name,
                    "year":       date_s[:4] if date_s else "N/A",
                    "overview":   data.get("overview", "")[:300],
                    "genres":     genres,
                    "poster_url":   poster,
                    "backdrop_url": backdrop,
                }
        except Exception as e:
            logger.warning(f"TMDB details error: {e}")
            return None


async def download_poster(url: str) -> bytes | None:
    """Download poster image bytes."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.read()
        except Exception as e:
            logger.warning(f"Poster download error: {e}")
    return None
