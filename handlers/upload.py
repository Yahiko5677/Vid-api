import re
import uuid
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, CallbackQuery

from config import ADMINS
from helper_func import parse_quality, parse_episode, parse_title
import uuid as _uuid
from memory_store import save_file, _cb_map
from keyboards import confirm_upload, force_post_keyboard, quality_picker
from services.log import log_file_received, log_file_confirmed
from utils import pacing

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)

# ── Stores ────────────────────────────────────────────────────────────────
_pending_confirm: dict[str, dict]    = {}

# Title cache keyed by (admin_id, title_key, season) — season-aware
# { admin_id: { "title_key_s01": "Fairy Tail", "title_key_s02": "Fairy Tail" } }
_title_cache: dict[int, dict]        = {}

# Queue: (admin_id, season_title_key) → [keys...]
_waiting_for_title: dict[tuple, list] = {}

# Track seasons already notified as complete — avoids repeated notices
_season_complete_notified: set = set()

# Debounce: accumulate files per admin, send summary after idle
# { admin_id: {"task": asyncio.Task, "saved": [], "failed": []} }
_debounce: dict[int, dict] = {}

DEBOUNCE_SECONDS = 3.0   # wait this long after last file before sending summary


def _make_title_key(title: str, season: int) -> str:
    """Season-aware key — S01 and S02 are separate groups."""
    base = re.sub(r'\W+', '_', title.lower()).strip("_")
    return f"{base}_s{season:02d}"


def get_cached_title(admin_id: int, title_key: str) -> str | None:
    return _title_cache.get(admin_id, {}).get(title_key)


def cache_title(admin_id: int, title_key: str, title: str):
    _title_cache.setdefault(admin_id, {})[title_key] = title


def clear_title_cache(admin_id: int, title_key: str):
    """Strip season suffix to clear all seasons of a title after posting."""
    base_key = re.sub(r'_s\d{2}$', '', title_key)
    to_remove = [k for k in _title_cache.get(admin_id, {}) if k.startswith(base_key)]
    for k in to_remove:
        _title_cache.get(admin_id, {}).pop(k, None)


# ─────────────────────────────────────────────────────────────
#  Debounce summary — fires 3s after last file of a batch
# ─────────────────────────────────────────────────────────────

async def _send_batch_summary(client: Client, admin_id: int, chat_id: int):
    """Wait for debounce window, then send one summary message + sticker."""
    await asyncio.sleep(DEBOUNCE_SECONDS)
    state = _debounce.pop(admin_id, {})
    saved  = state.get("saved", [])
    failed = state.get("failed", [])

    if not saved and not failed:
        return

    lines = [f"📦 <b>Batch complete — {len(saved)} file(s) queued/saved</b>\n"]
    for s in saved[:20]:
        lines.append(f"  ✅ <code>{s}</code>")
    if len(saved) > 20:
        lines.append(f"  ... and {len(saved)-20} more")
    for f in failed:
        lines.append(f"  ❌ <code>{f}</code>")

    try:
        await pacing.send(client, chat_id, "\n".join(lines))
    except Exception as e:
        logger.warning(f"Summary send failed: {e}")

    # Always send force post button so admin can post with whatever qualities are ready
    state     = _debounce.get(admin_id, {})
    title_key = state.get("title_key")
    season    = state.get("season", 1)
    if title_key:
        try:
            _fkey = _uuid.uuid4().hex[:8]
            _cb_map[_fkey] = (title_key, season)
            await pacing.send(client, chat_id,
                "📬 <b>Ready to post?</b> Use button below or /pending to review:",
                reply_markup=force_post_keyboard(_fkey),
            )
        except Exception as e:
            logger.warning(f"Force post button failed: {e}")

    # Send sticker in admin PM as visual batch-complete indicator
    from database.db import settings_col
    s       = await settings_col.find_one({"admin_id": admin_id}) or {}
    sticker = s.get("sticker_id")
    if sticker:
        try:
            await pacing.send_sticker(client, chat_id, sticker)
        except Exception as e:
            logger.warning(f"Admin PM sticker failed: {e}")


def _schedule_summary(client: Client, admin_id: int, chat_id: int):
    """Cancel existing debounce task and reschedule."""
    existing = _debounce.get(admin_id, {}).get("task")
    if existing and not existing.done():
        existing.cancel()
    _debounce.setdefault(admin_id, {"saved": [], "failed": [], "task": None})
    task = asyncio.get_running_loop().create_task(
        _send_batch_summary(client, admin_id, chat_id)
    )
    _debounce[admin_id]["task"] = task


def _record_saved(admin_id: int, label: str):
    _debounce.setdefault(admin_id, {"saved": [], "failed": [], "task": None})
    _debounce[admin_id]["saved"].append(label)


def _record_failed(admin_id: int, label: str):
    _debounce.setdefault(admin_id, {"saved": [], "failed": [], "task": None})
    _debounce[admin_id]["failed"].append(label)


# ─────────────────────────────────────────────────────────────
#  Store file — copy to quality's DB channel, save to memory
# ─────────────────────────────────────────────────────────────

async def _store_file(client: Client, chat_id: int, data: dict, title: str, title_key: str):
    """
    Save file reference to memory only.
    DB channel copy happens at post time — this avoids double-copying
    and keeps simple mode from unnecessarily writing to DB channel.
    msg_id stored here = original message ID in admin PM.
    """
    admin_id = data["admin_id"]
    ep_str   = "Movie" if data.get("is_movie") else f"S{data['season']:02d}E{data['episode']:02d}"
    label    = f"{title} {ep_str} {data['quality']}"

    ep = save_file(
        admin_id  = admin_id,
        title     = title,
        title_key = title_key,
        season    = data["season"],
        episode   = data["episode"],
        quality   = data["quality"],
        file_id   = data["file_id"],
        msg_id    = data["msg_id"],          # admin PM msg_id — copied to DB at post time
        file_name = data["file_name"],
        from_chat_id = data["from_chat_id"], # admin PM chat — needed at post time
    )

    have    = list(ep["qualities"].keys())
    missing = [q for q in ["480p", "720p", "1080p"] if q not in have]

    if missing:
        _record_saved(admin_id, f"{label} ⏳ missing: {', '.join(missing)}")
    else:
        from memory_store import get_season_episodes
        all_eps  = get_season_episodes(admin_id, title_key, data["season"])
        all_done = all(
            not [q for q in ["480p", "720p", "1080p"] if q not in list(e.get("qualities", {}).keys())]
            for e in all_eps
        )
        if all_done and len(all_eps) > 1:
            _record_saved(admin_id, f"{label} ✅ all ready — S" + str(data["season"]).zfill(2) + " complete!")
            # Send force-post button immediately (outside debounce)
            try:
                await pacing.send(client, chat_id,
                    f"🎉 <b>Season {data['season']:02d} complete!</b> <code>{title}</code>\n"
                    f"{len(all_eps)} episodes ready to post:",
                    reply_markup=force_post_keyboard(title_key, data["season"]),
                )
            except Exception:
                pass
        else:
            _record_saved(admin_id, f"{label} ✅")

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_confirmed(client, admin_id, title, data["quality"], ep_str, log_ch)


# ─────────────────────────────────────────────────────────────
#  Receive video — silent accumulation with debounce summary
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
    # Quality: filename first, caption fallback, then default 480p
    caption         = message.caption or ""
    quality         = parse_quality(file_name) or parse_quality(caption) or "480p"
    season, episode = parse_episode(file_name)
    # Episode fallback from caption if filename has none
    if season is None or episode is None:
        s_cap, e_cap = parse_episode(caption)
        season  = s_cap
        episode = e_cap
    season          = season  or 1
    episode         = episode or 1
    raw_title       = parse_title(file_name)
    # Season-aware key — S01 and S02 are separate groups
    title_key       = _make_title_key(raw_title, season)
    key             = uuid.uuid4().hex[:8]
    is_movie = (episode == 0)
    ep_str   = "Movie" if is_movie else f"S{season:02d}E{episode:02d}"

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
        "is_movie":      is_movie,
        "editing_title": False,
    }

    # Always reschedule debounce — resets 3s window on each new file
    _schedule_summary(client, admin_id, message.chat.id)

    # ── Quality unknown → ask admin ───────────────────────────
    # ── Title cached → auto-save silently ────────────────────
    cached = get_cached_title(admin_id, title_key)
    if cached:
        await _store_file(client, message.chat.id, data, cached, title_key)
        from database.db import settings_col
        s      = await settings_col.find_one({"admin_id": admin_id}) or {}
        log_ch = s.get("log_channel_id")
        await log_file_received(client, admin_id, cached, quality, ep_str, log_ch)
        return

    # ── New title_key — hold and ask once ────────────────────
    _pending_confirm[key] = data
    group_key      = (admin_id, title_key)
    already_asking = group_key in _waiting_for_title
    # Dedup: only add if not already in queue (prevents duplicate on retry)
    queue = _waiting_for_title.setdefault(group_key, [])
    if key not in queue:
        queue.append(key)

    if not already_asking:
        # Only send confirm for FIRST file of this title+season
        await pacing.reply(message,
            f"📁 <b>New title detected</b>\n\n"
            f"📌 Title   : <code>{raw_title}</code>\n"
            f"📺 Season  : <code>S{season:02d}</code>\n"
            f"📺 Episode : <code>{ep_str}</code>\n"
            f"🎞 Quality : <code>{quality}</code>\n\n"
            f"Confirm title for all <b>S{season:02d}</b> files:",
            reply_markup=confirm_upload(raw_title, season, episode, quality, key),
            quote=True,
        )

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_received(client, admin_id, raw_title, quality, ep_str, log_ch)


# ─────────────────────────────────────────────────────────────
#  Confirm
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

    _slabel = "Movie" if data.get("is_movie") else "S" + str(data["season"]).zfill(2)
    await pacing.edit(cb.message,
        "✅ <b>Title confirmed:</b> <code>" + title + " " + _slabel + "</code>\n"
        "⏳ Saving " + str(len(queued_keys)) + " file(s)..."
    )
    await cb.answer("Saving...")

    # Process all queued files for this title+season
    for qkey in queued_keys:
        qdata = _pending_confirm.pop(qkey, None)
        if qdata:
            await _store_file(client, chat_id, qdata, title, title_key)

    s_label = "Movie" if data.get("is_movie") else "S" + str(data["season"]).zfill(2)
    await pacing.edit(cb.message,
        "✅ <b>" + title + " " + s_label + "</b> — " + str(len(queued_keys)) + " file(s) saved.\n"
        "Title remembered until next post."
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
    s_lbl     = "Movie" if data.get("is_movie") else "S" + str(data["season"]).zfill(2)
    cur_title = data.get("raw_title", "")
    await pacing.edit(cb.message,
        "✏️ <b>Edit Title</b>\n\n"
        "Current: <code>" + cur_title + "</code>\n\n"
        "Send the corrected title\n"
        "Applies to all <b>" + str(queued_count) + "</b> queued " + s_lbl + " file(s):"
    )
    await cb.answer()


@Client.on_message(
    filters.text
    & ~filters.command(["start","settings","pending","log","stats","cancel"])
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

    raw_input = message.text.strip()
    # If admin accidentally sent a filename (has video extension or quality tags),
    # parse the title from it automatically
    import re as _re
    looks_like_filename = bool(_re.search(
        r'\.(mkv|mp4|avi|mov)$|\b(480p|720p|1080p|2160p|HEVC|BluRay|WEB-DL)\b',
        raw_input, _re.IGNORECASE
    ))
    new_title = parse_title(raw_input) if looks_like_filename else raw_input

    for key, data in editing:
        season        = data["season"]
        new_title_key = _make_title_key(new_title, season)
        old_group     = (admin_id, data["title_key"])
        new_group     = (admin_id, new_title_key)

        queued = _waiting_for_title.pop(old_group, [])
        _waiting_for_title[new_group] = queued
        for qkey in queued:
            if qkey in _pending_confirm:
                _pending_confirm[qkey]["title_key"] = new_title_key
                _pending_confirm[qkey]["raw_title"] = new_title
        data["raw_title"]     = new_title
        data["title_key"]     = new_title_key
        data["editing_title"] = False

        s_lbl2 = "Movie" if data.get("is_movie") else "S" + str(season).zfill(2)
        txt    = "✅ Title set: <code>" + new_title + "</code>\nConfirm for all <b>" + str(len(queued)) + "</b> " + s_lbl2 + " file(s)?"
        await pacing.reply(message, txt,
            reply_markup=confirm_upload(new_title, season, data["episode"], data["quality"], key),
        )


# ─────────────────────────────────────────────────────────────
#  Discard
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^qpick_") & filters.user(ADMINS))
async def cb_quality_pick(client: Client, cb: CallbackQuery):
    parts   = cb.data.split("_", 2)   # qpick_{quality}_{key}
    quality = parts[1]
    key     = parts[2]
    data    = _pending_confirm.get(key)
    if not data:
        return await cb.answer("Expired.", show_alert=True)

    data["quality"]  = quality
    data["is_movie"] = (data.get("episode", -1) == 0)
    ep_str = "Movie" if data.get("is_movie") else "S" + str(data["season"]).zfill(2) + "E" + str(data["episode"]).zfill(2)

    await pacing.edit(cb.message,
        "✅ Quality set: <b>" + quality + "</b>\n<code>" + data["raw_title"] + " " + ep_str + " " + quality + "</code>",
    )
    await cb.answer(quality + " selected")

    # Now proceed with normal title confirm flow
    title_key = data["title_key"]
    admin_id  = data["admin_id"]
    cached    = get_cached_title(admin_id, title_key)

    if cached:
        await _store_file(client, cb.message.chat.id, data, cached, title_key)
    else:
        group_key      = (admin_id, title_key)
        already_asking = group_key in _waiting_for_title
        queue = _waiting_for_title.setdefault(group_key, [])
        if key not in queue:
            queue.append(key)
        if not already_asking:
            s_lbl = "Movie" if data.get("is_movie") else "S" + str(data["season"]).zfill(2)
            await pacing.send(client, cb.message.chat.id,
                "📁 <b>Confirm title</b>\n\n"
                "📌 Title   : <code>" + data["raw_title"] + "</code>\n"
                "📺          : <code>" + s_lbl + "</code>\n"
                "🎞 Quality : <code>" + quality + "</code>\n\n"
                "Confirm title for all <b>" + s_lbl + "</b> files:",
                reply_markup=confirm_upload(data["raw_title"], data["season"], data["episode"], quality, key),
            )


@Client.on_callback_query(filters.regex(r"^du:") & filters.user(ADMINS))
async def cb_discard_upload(client: Client, cb: CallbackQuery):
    key  = cb.data.split(":", 1)[1]
    data = _pending_confirm.pop(key, None)
    if data:
        group_key = (data["admin_id"], data["title_key"])
        for qkey in _waiting_for_title.pop(group_key, []):
            _pending_confirm.pop(qkey, None)
    await pacing.edit(cb.message, "🗑 Discarded all queued files for this title.")
    await cb.answer()
