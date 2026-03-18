"""
memory_store.py — Primary in-memory store for pending files.

Priority:  MEMORY FIRST  →  DB only as restart-recovery backup.

Design:
    - Plain dict (no defaultdict) — avoids ghost key creation on reads
    - DB collection lazy-loaded on first use — safe for Pyrofork plugin loader
    - asyncio.get_running_loop() — correct for Python 3.10+ / 3.12
    - datetime.now(timezone.utc) — replaces deprecated utcnow()
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Plain dict — no defaultdict
_store: dict = {}

# Lazy-loaded DB collection — not imported at module level
# (avoids MongoDB connect attempt before bot.start())
_pending_col = None


def _get_col():
    global _pending_col
    if _pending_col is None:
        from database.db import pending_col
        _pending_col = pending_col
    return _pending_col


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Shared short-key → (title_key, season) map for callback data (64-byte limit)
_cb_map: dict[str, tuple] = {}


# ═══════════════════════════════════════════════════════
#  WRITE
# ═══════════════════════════════════════════════════════

def save_file(
    admin_id:     int,
    title:        str,
    title_key:    str,
    season:       int,
    episode:      int,
    quality:      str,
    file_id:      str,
    msg_id:       int,
    file_name:    str,
    from_chat_id: int = 0,   # admin PM chat_id — needed at post time for DB copy
) -> dict:
    """Save a quality entry to memory. Returns the updated episode doc."""

    # Safe nested build without defaultdict
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
        "created_at": _now(),
        "status":     "pending",
    })

    ep["qualities"][quality] = {
        "file_id":    file_id,
        "msg_id":     msg_id,
        "file_name":  file_name,
        "from_chat_id": from_chat_id,  # admin PM chat for post-time DB copy
    }
    ep["updated_at"] = _now()
    _store[admin_id][title_key][season][episode] = ep

    # Fire-and-forget DB sync
    # get_running_loop() — safe in Python 3.10+/3.12, always works in async context
    try:
        asyncio.get_running_loop().create_task(_db_upsert(ep))
    except RuntimeError:
        pass  # No running loop yet — DB will sync on next reload

    return ep


# ═══════════════════════════════════════════════════════
#  READ — all use safe .get() chain
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
    eps = (
        _store
        .get(admin_id, {})
        .get(title_key, {})
        .get(season, {})
    )
    return sorted(eps.values(), key=lambda x: x["episode"])


def get_all_pending(admin_id: int) -> list[dict]:
    result = []
    for title_key, seasons in _store.get(admin_id, {}).items():
        for season, episodes in seasons.items():
            for ep in episodes.values():
                if ep.get("status") != "posted":
                    result.append(ep)
    return sorted(result, key=lambda x: (x["title_key"], x["season"], x["episode"]))


def count_pending(admin_id: int) -> int:
    return len(get_all_pending(admin_id))


def clear_all_pending(admin_id: int) -> int:
    """Clear ALL pending episodes for admin from memory. Returns count cleared."""
    count = count_pending(admin_id)
    _store.pop(admin_id, None)
    asyncio.get_running_loop().create_task(_db_clear_all(admin_id))
    return count


def clear_pending_season(admin_id: int, title_key: str, season: int) -> int:
    """Clear one season from memory. Returns count cleared."""
    eps   = get_season_episodes(admin_id, title_key, season)
    count = len(eps)
    try:
        del _store[admin_id][title_key][season]
        if not _store[admin_id][title_key]:
            del _store[admin_id][title_key]
        if not _store[admin_id]:
            del _store[admin_id]
    except KeyError:
        pass
    asyncio.get_running_loop().create_task(_db_clear_season(admin_id, title_key, season))
    return count


# ═══════════════════════════════════════════════════════
#  REMOVE
# ═══════════════════════════════════════════════════════

def remove_episode(admin_id: int, title_key: str, season: int, episode: int):
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

    try:
        asyncio.get_running_loop().create_task(_db_delete(admin_id, title_key, season, episode))
    except RuntimeError:
        pass


# ═══════════════════════════════════════════════════════
#  STARTUP — reload DB → memory
# ═══════════════════════════════════════════════════════

async def reload_from_db():
    """Called once on bot startup — pulls pending docs from DB into memory."""
    try:
        cursor = _get_col().find({"status": {"$ne": "posted"}})
        docs   = await cursor.to_list(length=None)
        count  = 0
        for doc in docs:
            a  = doc["admin_id"]
            tk = doc["title_key"]
            s  = doc["season"]
            e  = doc["episode"]
            _store.setdefault(a, {})
            _store[a].setdefault(tk, {})
            _store[a][tk].setdefault(s, {})
            _store[a][tk][s].setdefault(e, doc)  # setdefault — never overwrites live memory
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
        await _get_col().update_one(
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


async def _db_clear_all(admin_id: int):
    try:
        await _get_col().delete_many({"admin_id": admin_id, "status": "pending"})
    except Exception as ex:
        logger.debug(f"DB clear all failed: {ex}")


async def _db_clear_season(admin_id: int, title_key: str, season: int):
    try:
        await _get_col().delete_many({"admin_id": admin_id, "title_key": title_key, "season": season})
    except Exception as ex:
        logger.debug(f"DB clear season failed: {ex}")


async def _db_delete(admin_id: int, title_key: str, season: int, episode: int):
    try:
        await _get_col().delete_one({
            "admin_id":  admin_id,
            "title_key": title_key,
            "season":    season,
            "episode":   episode,
        })
    except Exception as ex:
        logger.debug(f"DB sync delete failed: {ex}")
