import re
import uuid
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, CallbackQuery

from config import ADMINS
from utils import pacing, FILE_STORE_CHANNEL
from helper_func import parse_quality, parse_episode, parse_title
from memory_store import save_file
from keyboards import confirm_upload, force_post_keyboard
from services.log import log_file_received, log_file_confirmed

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)

# ── Stores ────────────────────────────────────────────────────────────────
# { key: file data }
_pending_confirm: dict[str, dict] = {}

# Confirmed titles per admin — cleared after posting
# { admin_id: { title_key: confirmed_title } }
_title_cache: dict[int, dict] = {}

# Files queued per (admin_id, title_key) waiting for one title confirm
# { (admin_id, title_key): [key, key, ...] }
_waiting_for_title: dict[tuple, list] = {}


def get_cached_title(admin_id: int, title_key: str) -> str | None:
    return _title_cache.get(admin_id, {}).get(title_key)


def cache_title(admin_id: int, title_key: str, title: str):
    _title_cache.setdefault(admin_id, {})[title_key] = title


def clear_title_cache(admin_id: int, title_key: str):
    """Called after posting — remove title from cache."""
    _title_cache.get(admin_id, {}).pop(title_key, None)


def _make_title_key(title: str) -> str:
    return re.sub(r'\W+', '_', title.lower()).strip("_")


# ─────────────────────────────────────────────────────────────
#  Store file — copy to FILE_STORE_CHANNEL, save to memory
# ─────────────────────────────────────────────────────────────

async def _store_file(client: Client, chat_id: int, data: dict, title: str, title_key: str):
    """Copy file to FILE_STORE_CHANNEL and save to memory store."""
    admin_id = data["admin_id"]
    ep_str   = f"S{data['season']:02d}E{data['episode']:02d}"

    # Retry loop — handles FloodWait automatically
    for attempt in range(5):
        try:
            stored = await pacing.copy_message(client, 
                chat_id             = FILE_STORE_CHANNEL,
                from_chat_id        = data["from_chat_id"],
                message_id          = data["msg_id"],
                disable_notification= True,
            )
            real_msg_id = stored.id
            await asyncio.sleep(0.1)
            break
        except FloodWait as e:
            wait = e.value + 2
            logger.warning(f"FloodWait {wait}s on copy — waiting...")
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error(f"Failed to copy to FILE_STORE_CHANNEL: {e}")
            await pacing.send(client, 
                chat_id,
                f"❌ Failed to store <code>{data['file_name']}</code>:\n<code>{e}</code>"
            )
            return
    else:
        await pacing.send(client, chat_id, f"❌ Failed after 5 retries: <code>{data['file_name']}</code>")
        return

    ep = save_file(
        admin_id  = admin_id,
        title     = title,
        title_key = title_key,
        season    = data["season"],
        episode   = data["episode"],
        quality   = data["quality"],
        file_id   = data["file_id"],
        msg_id    = real_msg_id,
        file_name = data["file_name"],
    )

    have    = list(ep["qualities"].keys())
    missing = [q for q in ["480p", "720p", "1080p"] if q not in have]

    if missing:
        await pacing.send(client, 
            chat_id,
            f"✅ <b>Saved</b> <code>{title} {ep_str} {data['quality']}</code>\n"
            f"⏳ Missing: <code>{', '.join(missing)}</code>"
        )
    else:
        # All qualities ready for this episode — check if whole season is done
        from memory_store import get_season_episodes
        all_eps  = get_season_episodes(data["admin_id"], title_key, data["season"])
        all_done = all(
            not [q for q in ["480p","720p","1080p"] if q not in list(e.get("qualities",{}).keys())]
            for e in all_eps
        )
        if all_done and len(all_eps) > 1:
            await pacing.send(client, 
                chat_id,
                f"✅ <b>All qualities ready!</b> <code>{title} {ep_str}</code>\n\n"
                f"🎉 <b>Full season ready!</b> {len(all_eps)} episodes — post the whole season at once?",
                reply_markup=force_post_keyboard(title_key, data["season"]),
            )
        else:
            await pacing.send(client, 
                chat_id,
                f"✅ <b>All qualities ready!</b> <code>{title} {ep_str}</code>",
            )

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_confirmed(client, admin_id, title, data["quality"], ep_str, log_ch)


# ─────────────────────────────────────────────────────────────
#  Receive video
# ─────────────────────────────────────────────────────────────

@Client.on_message(_admin_filter & (filters.document | filters.video))
async def on_video_upload(client: Client, message: Message):
    doc = message.document or message.video
    if not doc:
        return

    file_name = getattr(doc, "file_name", "") or ""
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if ext not in ("mkv", "mp4", "avi", "mov"):
        return

    admin_id        = message.from_user.id
    quality         = parse_quality(file_name) or "480p"
    season, episode = parse_episode(file_name)
    season          = season  or 1
    episode         = episode or 1
    raw_title       = parse_title(file_name)
    title_key       = _make_title_key(raw_title)
    key             = uuid.uuid4().hex[:8]
    ep_str          = f"S{season:02d}E{episode:02d}"

    data = {
        "key":           key,
        "admin_id":      admin_id,
        "file_id":       doc.file_id,
        "msg_id":        message.id,
        "from_chat_id":  message.chat.id,
        "file_name":     file_name,
        "raw_title":     raw_title,
        "title_key":     title_key,
        "season":        season,
        "episode":       episode,
        "quality":       quality,
        "editing_title": False,
    }

    # ── Title already confirmed → auto-save silently ──────────
    cached = get_cached_title(admin_id, title_key)
    if cached:
        await pacing.reply(message, 
            f"📥 <code>{cached} {ep_str} {quality}</code> — auto-saving...",
            quote=True,
        )
        await _store_file(client, message.chat.id, data, cached, title_key)
        from database.db import settings_col
        s      = await settings_col.find_one({"admin_id": admin_id}) or {}
        log_ch = s.get("log_channel_id")
        await log_file_received(client, admin_id, cached, quality, ep_str, log_ch)
        return

    # ── New title_key — queue and ask once ────────────────────
    _pending_confirm[key] = data
    group_key      = (admin_id, title_key)
    already_asking = group_key in _waiting_for_title
    _waiting_for_title.setdefault(group_key, []).append(key)

    if already_asking:
        await pacing.reply(message, 
            f"⏳ <code>{ep_str} {quality}</code> queued — waiting for title confirm.",
            quote=True,
        )
    else:
        await pacing.reply(message, 
            f"📁 <b>New title detected</b>\n\n"
            f"📌 Title   : <code>{raw_title}</code>\n"
            f"📺 Episode : <code>{ep_str}</code>\n"
            f"🎞 Quality : <code>{quality}</code>\n\n"
            f"Confirm title for <b>all queued files</b>:",
            reply_markup=confirm_upload(raw_title, season, episode, quality, key),
            quote=True,
        )

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_received(client, admin_id, raw_title, quality, ep_str, log_ch)


# ─────────────────────────────────────────────────────────────
#  Confirm — saves ALL queued files for this title_key
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^cu:") & filters.user(ADMINS))
async def cb_confirm_upload(client: Client, cb: CallbackQuery):
    key  = cb.data.split(":", 1)[1]
    data = _pending_confirm.get(key)
    if not data:
        return await cb.answer("Already confirmed or expired.", show_alert=True)

    admin_id  = data["admin_id"]
    title_key = data["title_key"]
    title     = data["raw_title"]
    chat_id   = cb.message.chat.id

    cache_title(admin_id, title_key, title)

    group_key   = (admin_id, title_key)
    queued_keys = _waiting_for_title.pop(group_key, [key])

    await pacing.edit(cb.message, 
        f"✅ <b>Title confirmed:</b> <code>{title}</code>\n"
        f"⏳ Saving {len(queued_keys)} file(s)..."
    )
    await cb.answer("Saving all queued files...")

    for qkey in queued_keys:
        qdata = _pending_confirm.pop(qkey, None)
        if qdata:
            await _store_file(client, chat_id, qdata, title, title_key)
            await asyncio.sleep(0.3)

    await pacing.edit(cb.message, 
        f"✅ <b>{title}</b> — {len(queued_keys)} file(s) saved.\n"
        f"Title remembered until next post."
    )


# ─────────────────────────────────────────────────────────────
#  Edit title
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^et:") & filters.user(ADMINS))
async def cb_edit_title(client: Client, cb: CallbackQuery):
    key  = cb.data.split(":", 1)[1]
    data = _pending_confirm.get(key)
    if not data:
        return await cb.answer("Already confirmed or expired.", show_alert=True)

    data["editing_title"] = True
    group_key    = (data["admin_id"], data["title_key"])
    queued_count = len(_waiting_for_title.get(group_key, [key]))

    await pacing.edit(cb.message, 
        f"✏️ Send the <b>corrected title</b>\n"
        f"Will apply to all <b>{queued_count}</b> queued file(s):"
    )
    await cb.answer()


# Fix #1 & #2 — recalculate title_key + guard against commands
@Client.on_message(
    filters.text & ~filters.command(["start","settings","pending","log","stats","cancel"])
    & _admin_filter,
    group=1
)
async def on_title_edit_reply(client: Client, message: Message):
    admin_id = message.from_user.id
    editing  = [
        (k, v) for k, v in _pending_confirm.items()
        if v.get("admin_id") == admin_id and v.get("editing_title")
    ]
    if not editing:
        return

    new_title     = message.text.strip()
    new_title_key = _make_title_key(new_title)  # Fix #1 — recalculate

    for key, data in editing:
        old_title_key = data["title_key"]
        old_group_key = (admin_id, old_title_key)
        new_group_key = (admin_id, new_title_key)

        # Move queued keys to new title_key group
        queued = _waiting_for_title.pop(old_group_key, [])
        _waiting_for_title[new_group_key] = queued

        # Update all queued files' title_key
        for qkey in queued:
            if qkey in _pending_confirm:
                _pending_confirm[qkey]["title_key"] = new_title_key
                _pending_confirm[qkey]["raw_title"] = new_title

        data["raw_title"]     = new_title
        data["title_key"]     = new_title_key
        data["editing_title"] = False

        ep_str = f"S{data['season']:02d}E{data['episode']:02d}"
        await pacing.reply(message, 
            f"✅ Title set to: <code>{new_title}</code>\n\n"
            f"Confirm for all <b>{len(queued)}</b> queued file(s)?",
            reply_markup=confirm_upload(
                new_title, data["season"], data["episode"], data["quality"], key
            ),
        )


# ─────────────────────────────────────────────────────────────
#  Discard
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^du:") & filters.user(ADMINS))
async def cb_discard_upload(client: Client, cb: CallbackQuery):
    key  = cb.data.split(":", 1)[1]
    data = _pending_confirm.pop(key, None)
    if data:
        group_key = (data["admin_id"], data["title_key"])
        # Discard ALL queued files for this title
        for qkey in _waiting_for_title.pop(group_key, []):
            _pending_confirm.pop(qkey, None)
    await pacing.edit(cb.message, "🗑 Discarded all queued files for this title.")
    await cb.answer()
