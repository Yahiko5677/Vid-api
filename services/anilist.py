"""
# v5 - 2026-03-20
services/anilist.py — AniList GraphQL API service for fetching English episode titles.

Endpoint: https://graphql.anilist.co
No API key required.
"""

import re
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)

ANILIST_URL = "https://graphql.anilist.co"

async def get_anilist_episode_titles(title: str, season: int = 1) -> dict[int, str]:
    """
    Search AniList by title + season and return a dict of {local_ep_number: "English Episode Title"}.
    Strictly filters out non-TV formats and trailers/promos to prevent season mismatches.
    """
    if not title:
        return {}

    search_term = f"{title} Season {season}" if season > 1 else title
    variables = {"search": search_term}
    raw_titles: dict[float, str] = {}

    query = """
    query ($search: String) {
      Page (page: 1, perPage: 10) {
        media (search: $search, type: ANIME) {
          id
          format
          title { romaji english }
          episodes
          streamingEpisodes {
            title
          }
        }
      }
    }
    """

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(ANILIST_URL, json={"query": query, "variables": variables}) as resp:
                if resp.status != 200:
                    logger.warning(f"AniList GraphQL HTTP {resp.status}")
                    return {}
                data = await resp.json()
                media_list = data.get("data", {}).get("Page", {}).get("media", [])
                
                for media in media_list:
                    fmt = (media.get("format") or "").upper()
                    # Skip movies/OVAs/specials for season series queries
                    if season >= 1 and fmt in ("MOVIE", "OVA", "SPECIAL", "MUSIC"):
                        continue

                    for ep in media.get("streamingEpisodes", []):
                        raw_title = ep.get("title", "")
                        if not raw_title:
                            continue
                        # Ignore trailers, teasers, promotional videos
                        if re.search(r'\b(Trailer|Teaser|PV|CM|Preview)\b', raw_title, re.IGNORECASE):
                            continue

                        match = re.search(r'(?:Episode\s*)?(\d+(?:\.\d+)?)[\s:-]+(.+)', raw_title, re.IGNORECASE)
                        if match:
                            ep_num = float(match.group(1))
                            ep_name = match.group(2).strip()
                            if ep_name and not re.match(r'^Episode\s*\d+$', ep_name, re.IGNORECASE):
                                raw_titles[ep_num] = ep_name

    except Exception as e:
        logger.warning(f"AniList episode titles error: {e}")

    if not raw_titles:
        return {}

    # Sort integer episode numbers to determine global starting episode
    sorted_nums = sorted([n for n in raw_titles.keys() if n.is_integer()])
    min_global_ep = int(sorted_nums[0]) if sorted_nums else 1

    # Build local episode map (1..100) -> English title
    mapped_titles: dict[int, str] = {}
    for local_ep in range(1, 100):
        global_ep = min_global_ep + local_ep - 1
        found = raw_titles.get(local_ep) or raw_titles.get(global_ep) or raw_titles.get(float(global_ep))
        if found:
            mapped_titles[local_ep] = found

    return mapped_titles
