"""
memory_store.py — Primary in-memory store for pending files.

Priority:  MEMORY FIRST  →  DB only as restart-recovery backup.

Structure:
    _store[admin_id][title_key][season][episode] = {
        "title":     str,
        "qualities": { "480p": {...}, "720p": {...}, "1080p": {...} },
        "created_at": datetime,
    }

DB sync:
    - Write to DB after every change (fire-and-forget, non-blocking)
    - On bot startup → reload() pulls DB into memory once
    - On post → remove from memory + delete from DB
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Primary memory store ─────────────────────────────────────────────────
# { admin_id: { title_key: { season: { episode: doc } } } }
_store: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))


# ═══════════════════════════════════════════════════════
#  WRITE
# ═══════════════════════════════════════════════════════

def save_file(
    admin_id:  int,
    title:     str,
    title_key: str,
    season:    int,
    episode:   int,
    quality:   str,
    file_id:   str,
    msg_id:    int,
    file_name: str,
):
    """Save a quality entry to memory. Returns the updated episode doc."""
    ep = _store[admin_id][title_key][season].get(episode, {
        "title":      title,
        "title_key":  title_key,
        "admin_id":   admin_id,
        "season":     season,
        "episode":    episode,
        "qualities":  {},
        "created_at": datetime.utcnow(),
        "status":     "pending",
    })

    ep["qualities"][quality] = {
        "file_id":   file_id,
        "msg_id":    msg_id,
        "file_name": file_name,
    }
    ep["updated_at"] = datetime.utcnow()

    _store[admin_id][title_key][season][episode] = ep

    # Fire-and-forget DB sync
    asyncio.create_task(_db_upsert(ep))

    return ep


def get_episode(admin_id: int, title_key: str, season: int, episode: int) -> Optional[dict]:
    return _store[admin_id][title_key][season].get(episode)


def get_season_episodes(admin_id: int, title_key: str, season: int) -> list[dict]:
    """All episodes for a title+season, sorted by episode number."""
    eps = _store[admin_id][title_key][season]
    return sorted(eps.values(), key=lambda x: x["episode"])


def get_all_pending(admin_id: int) -> list[dict]:
    """Flat list of all pending episodes for an admin, sorted."""
    result = []
    for title_key, seasons in _store[admin_id].items():
        for season, episodes in seasons.items():
            for ep in episodes.values():
                if ep.get("status") != "posted":
                    result.append(ep)
    return sorted(result, key=lambda x: (x["title_key"], x["season"], x["episode"]))


def remove_episode(admin_id: int, title_key: str, season: int, episode: int):
    """Remove from memory after posting."""
    try:
        del _store[admin_id][title_key][season][episode]
        # Clean up empty dicts
        if not _store[admin_id][title_key][season]:
            del _store[admin_id][title_key][season]
        if not _store[admin_id][title_key]:
            del _store[admin_id][title_key]
    except KeyError:
        pass
    asyncio.create_task(_db_delete(admin_id, title_key, season, episode))


def count_pending(admin_id: int) -> int:
    return len(get_all_pending(admin_id))


# ═══════════════════════════════════════════════════════
#  STARTUP: reload DB → memory
# ═══════════════════════════════════════════════════════

async def reload_from_db():
    """
    Called once on bot startup.
    Pulls all non-posted pending docs from DB into memory.
    """
    from database.db import pending_col
    try:
        cursor = pending_col.find({"status": {"$ne": "posted"}})
        docs   = await cursor.to_list(length=None)
        count  = 0
        for doc in docs:
            a  = doc["admin_id"]
            tk = doc["title_key"]
            s  = doc["season"]
            e  = doc["episode"]
            _store[a][tk][s][e] = doc
            count += 1
        logger.info(f"✅ Memory reloaded: {count} pending episode(s) from DB")
    except Exception as ex:
        logger.warning(f"⚠️ DB reload failed (running memory-only): {ex}")


# ═══════════════════════════════════════════════════════
#  DB SYNC HELPERS  (fire-and-forget)
# ═══════════════════════════════════════════════════════

async def _db_upsert(ep: dict):
    from database.db import pending_col
    try:
        doc = {k: v for k, v in ep.items() if k != "_id"}
        await pending_col.update_one(
            {
                "admin_id":  ep["admin_id"],
                "title_key": ep["title_key"],
                "season":    ep["season"],
                "episode":   ep["episode"],
            },
            {"$set": doc},
            upsert=True,
        )
    except Exception as ex:
        logger.debug(f"DB sync write failed (memory still ok): {ex}")


async def _db_delete(admin_id: int, title_key: str, season: int, episode: int):
    from database.db import pending_col
    try:
        await pending_col.delete_one({
            "admin_id":  admin_id,
            "title_key": title_key,
            "season":    season,
            "episode":   episode,
        })
    except Exception as ex:
        logger.debug(f"DB sync delete failed: {ex}")
