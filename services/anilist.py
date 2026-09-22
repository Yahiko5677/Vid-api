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

QUERY = """
query ($search: String) {
  Media (search: $search, type: ANIME) {
    id
    title {
      romaji
      english
    }
    streamingEpisodes {
      title
    }
  }
}
"""


async def get_anilist_episode_titles(title: str) -> dict[int, str]:
    """
    Search AniList by title and return a dict of {ep_number: "English Episode Title"}.
    Only extracts valid English episode names.
    """
    if not title:
        return {}

    variables = {"search": title}
    result: dict[int, str] = {}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(ANILIST_URL, json={"query": QUERY, "variables": variables}) as resp:
                if resp.status != 200:
                    logger.warning(f"AniList GraphQL HTTP {resp.status}")
                    return {}
                data = await resp.json()
                media = data.get("data", {}).get("Media")
                if not media:
                    return {}

                episodes = media.get("streamingEpisodes", [])
                for ep in episodes:
                    raw_title = ep.get("title", "")
                    if not raw_title:
                        continue
                    # Match "Episode 1 - Title" or "1 - Title" or "Episode 1: Title"
                    match = re.search(r'(?:Episode\s*)?(\d+)[\s:-]+(.+)', raw_title, re.IGNORECASE)
                    if match:
                        ep_num = int(match.group(1))
                        ep_name = match.group(2).strip()
                        # Ensure name is not redundant "Episode X"
                        if ep_name and not re.match(r'^Episode\s*\d+$', ep_name, re.IGNORECASE):
                            result[ep_num] = ep_name
    except Exception as e:
        logger.warning(f"AniList episode titles error: {e}")

    return result
