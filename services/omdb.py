"""
OMDB service — Open Movie Database (movies + series).
API key required — free tier at omdbapi.com (1000 req/day).
Set OMDB_API_KEY in .env.

Returns unified meta dict compatible with Jikan/TMDB shape.
"""

import aiohttp
import logging
from config import OMDB_API_KEY

logger  = logging.getLogger(__name__)
BASE    = "https://www.omdbapi.com"
TIMEOUT = aiohttp.ClientTimeout(total=10)


async def search_omdb(title: str, media_type: str = "") -> list[dict]:
    """
    Search OMDB. media_type: "" | "movie" | "series"
    Returns up to 5 results in unified shape.
    """
    if not OMDB_API_KEY:
        return []

    params = {"apikey": OMDB_API_KEY, "s": title, "type": media_type or ""}
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get(BASE, params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                if data.get("Response") != "True":
                    return []
                results = []
                for item in data.get("Search", [])[:5]:
                    results.append({
                        "source":      "omdb",
                        "imdb_id":     item.get("imdbID", ""),
                        "type":        item.get("Type", ""),
                        "media_type":  item.get("Type", ""),
                        "title":       item.get("Title", ""),
                        "year":        item.get("Year", "N/A"),
                        "poster_url":  item.get("Poster") if item.get("Poster") != "N/A" else None,
                        # Full details fetched separately
                        "genres":      [],
                        "synopsis":    "",
                        "score":       None,
                        "episodes":    None,
                        "studio":      None,
                    })
                return results
        except Exception as e:
            logger.warning(f"OMDB search error: {e}")
            return []


async def get_omdb_details(imdb_id: str) -> dict | None:
    """Fetch full details by IMDB ID."""
    if not OMDB_API_KEY or not imdb_id:
        return None

    params = {"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "short"}
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get(BASE, params=params) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                if data.get("Response") != "True":
                    return None

                genres   = [g.strip() for g in data.get("Genre", "").split(",") if g.strip()]
                score    = data.get("imdbRating", "N/A")
                episodes = data.get("totalSeasons")
                director = data.get("Director", "N/A")
                poster   = data.get("Poster") if data.get("Poster") != "N/A" else None

                return {
                    "source":     "omdb",
                    "imdb_id":    imdb_id,
                    "type":       data.get("Type", ""),
                    "media_type": data.get("Type", ""),
                    "title":      data.get("Title", ""),
                    "year":       data.get("Year", "N/A"),
                    "genres":     genres[:4],
                    "synopsis":   data.get("Plot", ""),
                    "score":      score if score != "N/A" else None,
                    "episodes":   episodes,
                    "studio":     director if director != "N/A" else None,
                    "poster_url": poster,
                }
        except Exception as e:
            logger.warning(f"OMDB details error: {e}")
            return None
