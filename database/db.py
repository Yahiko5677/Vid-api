"""
MongoDB layer using Motor (async).

Collections:
  pending_files   — uploaded files awaiting grouping / posting
  admin_settings  — per-admin configuration
  posted          — history of posted episodes
"""

from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

client      = AsyncIOMotorClient(MONGO_URI)
db          = client[DB_NAME]
pending_col = db["pending_files"]
settings_col = db["admin_settings"]
posted_col  = db["posted"]


# ═══════════════════════════════════════════════════════════
#  INDEXES
# ═══════════════════════════════════════════════════════════
async def ensure_indexes():
    await pending_col.create_index(
        [("admin_id", 1), ("title_key", 1), ("season", 1), ("episode", 1)]
    )
    await settings_col.create_index("admin_id", unique=True)
    logger.info("✅ MongoDB indexes ensured")


# ═══════════════════════════════════════════════════════════
#  PENDING FILES
# ═══════════════════════════════════════════════════════════

async def save_pending_file(
    admin_id: int,
    title: str,
    title_key: str,
    season: int,
    episode: int,
    quality: str,
    file_id: str,
    msg_id: int,
    file_name: str,
):
    await pending_col.update_one(
        {
            "admin_id":  admin_id,
            "title_key": title_key,
            "season":    season,
            "episode":   episode,
        },
        {
            "$set": {
                "title":                  title,
                f"qualities.{quality}":   {
                    "file_id":   file_id,
                    "msg_id":    msg_id,
                    "file_name": file_name,
                },
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow(),
                "status":     "pending",
            },
        },
        upsert=True,
    )


async def get_pending_episodes(admin_id: int, title_key: str, season: int) -> list:
    cursor = pending_col.find(
        {
            "admin_id":  admin_id,
            "title_key": title_key,
            "season":    season,
            "status":    {"$ne": "posted"},
        },
        sort=[("episode", 1)],
    )
    return await cursor.to_list(length=None)


async def get_all_pending(admin_id: int) -> list:
    cursor = pending_col.find(
        {"admin_id": admin_id, "status": {"$ne": "posted"}},
        sort=[("title_key", 1), ("season", 1), ("episode", 1)],
    )
    return await cursor.to_list(length=None)


async def mark_posted(admin_id: int, title_key: str, season: int, episode: int):
    """Mark episode as posted by natural key (no _id needed)."""
    await pending_col.update_one(
        {"admin_id": admin_id, "title_key": title_key, "season": season, "episode": episode},
        {"$set": {"status": "posted", "posted_at": datetime.utcnow()}},
    )


async def delete_pending_by_id(episode_doc_id):
    await pending_col.delete_one({"_id": episode_doc_id})


# ═══════════════════════════════════════════════════════════
#  ADMIN SETTINGS
# ═══════════════════════════════════════════════════════════

DEFAULT_SETTINGS = {
    "post_mode":  "simple",
    "audio_info": "Hindi + English",
    "sub_info":   "English",
    "sticker_id": None,
    "channels":   [],
}


async def get_settings(admin_id: int) -> dict:
    doc = await settings_col.find_one({"admin_id": admin_id})
    if not doc:
        return {**DEFAULT_SETTINGS, "admin_id": admin_id}
    # fill missing keys with defaults
    for k, v in DEFAULT_SETTINGS.items():
        doc.setdefault(k, v)
    return doc


async def update_settings(admin_id: int, **kwargs):
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$set": kwargs},
        upsert=True,
    )


async def add_channel(admin_id: int, channel_id: int, channel_name: str):
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$addToSet": {"channels": {"id": channel_id, "name": channel_name}}},
        upsert=True,
    )


async def remove_channel(admin_id: int, channel_id: int):
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$pull": {"channels": {"id": channel_id}}},
    )


# ═══════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════

async def get_stats(admin_id: int) -> dict:
    pending = await pending_col.count_documents(
        {"admin_id": admin_id, "status": "pending"}
    )
    total_posted = await pending_col.count_documents(
        {"admin_id": admin_id, "status": "posted"}
    )
    return {"pending": pending, "posted": total_posted}
