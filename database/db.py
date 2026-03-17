"""
MongoDB layer — Motor async.

Collections:
  pending_files   — uploaded files grouped by title+season+episode
  admin_settings  — per-admin configuration (all UX settings)
  posted          — history of posted episodes
"""

from motor.motor_asyncio import AsyncIOMotorClient
from config import (
    MONGO_URI, DB_NAME,
    DEFAULT_CAPTION_TEMPLATE, DEFAULT_BUTTON_LABEL, DEFAULT_BUTTON_LAYOUT,
)
from datetime import datetime
import logging

logger       = logging.getLogger(__name__)
client       = AsyncIOMotorClient(MONGO_URI)
db           = client[DB_NAME]
pending_col  = db["pending_files"]
settings_col = db["admin_settings"]
posted_col   = db["posted"]


# ═══════════════════════════════════════════════════════
#  INDEXES
# ═══════════════════════════════════════════════════════

async def ensure_indexes():
    await pending_col.create_index(
        [("admin_id", 1), ("title_key", 1), ("season", 1), ("episode", 1)]
    )
    await settings_col.create_index("admin_id", unique=True)
    logger.info("✅ MongoDB indexes ensured")


# ═══════════════════════════════════════════════════════
#  PENDING FILES
# ═══════════════════════════════════════════════════════

async def save_pending_file(
    admin_id: int, title: str, title_key: str,
    season: int, episode: int, quality: str,
    file_id: str, msg_id: int, file_name: str,
):
    await pending_col.update_one(
        {"admin_id": admin_id, "title_key": title_key, "season": season, "episode": episode},
        {
            "$set": {
                "title": title,
                f"qualities.{quality}": {"file_id": file_id, "msg_id": msg_id, "file_name": file_name},
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {"created_at": datetime.utcnow(), "status": "pending"},
        },
        upsert=True,
    )


async def mark_posted(admin_id: int, title_key: str, season: int, episode: int):
    await pending_col.update_one(
        {"admin_id": admin_id, "title_key": title_key, "season": season, "episode": episode},
        {"$set": {"status": "posted", "posted_at": datetime.utcnow()}},
    )


# ═══════════════════════════════════════════════════════
#  ADMIN SETTINGS
# ═══════════════════════════════════════════════════════

DEFAULT_SETTINGS = {
    "post_mode":        "simple",
    "audio_info":       "Hindi + English",
    "sub_info":         "English",
    "sticker_id":       None,

    # Caption & button UX
    "caption_template": DEFAULT_CAPTION_TEMPLATE,
    "button_label":     DEFAULT_BUTTON_LABEL,
    "button_layout":    DEFAULT_BUTTON_LAYOUT,   # e.g. "2,1" or "3" or "1,1,1"
    "watermark":        "",                       # watermark text on thumbnail

    # Per-quality File Store Bot overrides (None = use config.py global)
    # { "480p": {"bot": "Bot480", "channel": -100123}, "720p": {...}, "1080p": {...} }
    "quality_bots":     {},

    # Channels with quality assignments
    # [ {"id": int, "name": str, "qualities": ["480p","720p","1080p"]} ]
    "channels":         [],
}


async def get_settings(admin_id: int) -> dict:
    doc = await settings_col.find_one({"admin_id": admin_id})
    if not doc:
        return {**DEFAULT_SETTINGS, "admin_id": admin_id}
    for k, v in DEFAULT_SETTINGS.items():
        doc.setdefault(k, v)
    return doc


async def update_settings(admin_id: int, **kwargs):
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$set": kwargs},
        upsert=True,
    )


async def add_channel(admin_id: int, channel_id: int, channel_name: str, qualities: list = None):
    """Add channel. Default qualities = all three."""
    if qualities is None:
        qualities = ["480p", "720p", "1080p"]
    # Remove if already exists then re-add
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$pull": {"channels": {"id": channel_id}}},
        upsert=True,
    )
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$push": {"channels": {"id": channel_id, "name": channel_name, "qualities": qualities}}},
    )


async def update_channel_qualities(admin_id: int, channel_id: int, qualities: list):
    """Update quality assignment for a channel."""
    await settings_col.update_one(
        {"admin_id": admin_id, "channels.id": channel_id},
        {"$set": {"channels.$.qualities": qualities}},
    )


async def remove_channel(admin_id: int, channel_id: int):
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$pull": {"channels": {"id": channel_id}}},
    )


async def set_quality_bot(admin_id: int, quality: str, bot_username: str, channel_id: int):
    """Set per-quality File Store Bot override for this admin."""
    await settings_col.update_one(
        {"admin_id": admin_id},
        {"$set": {f"quality_bots.{quality}": {"bot": bot_username, "channel": channel_id}}},
        upsert=True,
    )


# ═══════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════

async def get_stats(admin_id: int) -> dict:
    pending = await pending_col.count_documents({"admin_id": admin_id, "status": "pending"})
    posted  = await pending_col.count_documents({"admin_id": admin_id, "status": "posted"})
    return {"pending": pending, "posted": posted}
