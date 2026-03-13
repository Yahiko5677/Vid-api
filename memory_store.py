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

Fixes:
    - asyncio.create_task() replaced with loop.create_task() (safe in sync)
    - defaultdict reads replaced with .get() chain (no ghost keys)
    - DB imports moved to top-level (no repeated lazy imports)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Top-level DB import (fix #3) ─────────────────────────────────────────
from database.db import pending_col

# ── Primary memory store ─────────────────────────────────────────────────
# Plain dict — no defaultdict to avoid ghost key creation (fix #2)
# { admin_id: { title_key: { season: { episode: doc } } } }
_store: dict = {}


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
) -> dict:
    """Save a quality entry to memory. Returns the updated episode doc."""

    # Build nested structure safely without defaultdict
    _store.setdefault(admin_id, {})
    _store[admin_id].setdefault(title_key, {})
    _store[admin_id][title_key].setdefault(season, {})

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

    # Fire-and-forget DB sync (fix #1 — safe loop.create_task in sync context)
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_db_upsert(ep))
    except RuntimeError:
        pass  # No event loop yet — DB will sync on next reload

    return ep


# ═══════════════════════════════════════════════════════
#  READ  (all use safe .get() chain — fix #2)
# ═══════════════════════════════════════════════════════

def get_episode(admin_id: int, title_key: str, season: int, episode: int) -> Optional[dict]:
    return (
        _store
        .get(admin_id, {})
        .get(title_key, {})
        .get(season, {})
        .get(episode)
    )


def get_season_episodes(admin_id: int, title_key: str, season: int) -> list[dict]:
    """All episodes for a title+season, sorted by episode number."""
    eps = (
        _store
        .get(admin_id, {})
        .get(title_key, {})
        .get(season, {})
    )
    return sorted(eps.values(), key=lambda x: x["episode"])


def get_all_pending(admin_id: int) -> list[dict]:
    """Flat list of all pending episodes for an admin, sorted."""
    result = []
    for title_key, seasons in _store.get(admin_id, {}).items():
        for season, episodes in seasons.items():
            for ep in episodes.values():
                if ep.get("status") != "posted":
                    result.append(ep)
    return sorted(result, key=lambda x: (x["title_key"], x["season"], x["episode"]))


def count_pending(admin_id: int) -> int:
    return len(get_all_pending(admin_id))


# ═══════════════════════════════════════════════════════
#  REMOVE
# ═══════════════════════════════════════════════════════

def remove_episode(admin_id: int, title_key: str, season: int, episode: int):
    """Remove from memory after posting + async DB delete."""
    try:
        del _store[admin_id][title_key][season][episode]
        # Clean up empty parent dicts
        if not _store[admin_id][title_key][season]:
            del _store[admin_id][title_key][season]
        if not _store[admin_id][title_key]:
            del _store[admin_id][title_key]
        if not _store[admin_id]:
            del _store[admin_id]
    except KeyError:
        pass

    # Fire-and-forget DB delete (fix #1)
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_db_delete(admin_id, title_key, season, episode))
    except RuntimeError:
        pass


# ═══════════════════════════════════════════════════════
#  STARTUP: reload DB → memory
# ═══════════════════════════════════════════════════════

async def reload_from_db():
    """
    Called once on bot startup.
    Pulls all non-posted pending docs from DB into memory.
    """
    try:
        cursor = pending_col.find({"status": {"$ne": "posted"}})
        docs   = await cursor.to_list(length=None)
        count  = 0
        for doc in docs:
            a  = doc["admin_id"]
            tk = doc["title_key"]
            s  = doc["season"]
            e  = doc["episode"]
            # Use setdefault to avoid overwriting existing memory entries
            _store.setdefault(a, {})
            _store[a].setdefault(tk, {})
            _store[a][tk].setdefault(s, {})
            _store[a][tk][s].setdefault(e, doc)
            count += 1
        logger.info(f"✅ Memory reloaded: {count} pending episode(s) from DB")
    except Exception as ex:
        logger.warning(f"⚠️ DB reload failed (running memory-only): {ex}")


# ═══════════════════════════════════════════════════════
#  DB SYNC HELPERS  (fire-and-forget)
# ═══════════════════════════════════════════════════════

async def _db_upsert(ep: dict):
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
    try:
        await pending_col.delete_one({
            "admin_id":  admin_id,
            "title_key": title_key,
            "season":    season,
            "episode":   episode,
        })
    except Exception as ex:
        logger.debug(f"DB sync delete failed: {ex}")
