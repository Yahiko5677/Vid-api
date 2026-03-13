import re
import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery

from pyrogram import Client
from config import ADMINS
from helper_func import parse_quality, parse_episode, parse_title
from memory_store import save_file
from keyboards import confirm_upload, force_post_keyboard
from services.log import log_file_received, log_file_confirmed

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)

# { admin_id: parsed_data }
_pending_confirm: dict[int, dict] = {}


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
    title           = parse_title(file_name)

    _pending_confirm[admin_id] = {
        "file_id":   doc.file_id,
        "msg_id":    message.id,
        "file_name": file_name,
        "title":     title,
        "season":    season,
        "episode":   episode,
        "quality":   quality,
    }

    ep_str = f"S{season:02d}E{episode:02d}"
    await message.reply(
        f"📁 <b>File detected</b>\n\n"
        f"📌 Title   : <code>{title}</code>\n"
        f"📺 Episode : <code>{ep_str}</code>\n"
        f"🎞 Quality : <code>{quality}</code>\n"
        f"📄 File    : <code>{file_name}</code>\n\n"
        f"Is this correct?",
        reply_markup=confirm_upload(title, season, episode, quality),
        quote=True,
    )

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_received(client, admin_id, title, quality, ep_str, log_ch)


# ─────────────────────────────────────────────────────────────
#  Confirm
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^confirm_upload$") & filters.user(ADMINS))
async def cb_confirm_upload(client: Client, cb: CallbackQuery):
    admin_id = cb.from_user.id
    data     = _pending_confirm.get(admin_id)
    if not data:
        return await cb.answer("No pending upload.", show_alert=True)

    title_key = re.sub(r'\W+', '_', data["title"].lower()).strip("_")
    ep        = save_file(
        admin_id  = admin_id,
        title     = data["title"],
        title_key = title_key,
        season    = data["season"],
        episode   = data["episode"],
        quality   = data["quality"],
        file_id   = data["file_id"],
        msg_id    = data["msg_id"],
        file_name = data["file_name"],
    )

    have    = list(ep["qualities"].keys())
    missing = [q for q in ["480p", "720p", "1080p"] if q not in have]
    ep_str  = f"S{data['season']:02d}E{data['episode']:02d}"

    from database.db import settings_col
    s      = await settings_col.find_one({"admin_id": admin_id}) or {}
    log_ch = s.get("log_channel_id")
    await log_file_confirmed(client, admin_id, data["title"], data["quality"], ep_str, log_ch)

    if missing:
        await cb.message.edit_text(
            f"✅ <b>Saved!</b> <code>{data['title']} {ep_str} {data['quality']}</code>\n\n"
            f"⏳ Still waiting for: <code>{', '.join(missing)}</code>",
        )
    else:
        await cb.message.edit_text(
            f"✅ <b>All qualities ready!</b> <code>{data['title']} {ep_str}</code>\n\nReady to post:",
            reply_markup=force_post_keyboard(title_key, data["season"]),
        )

    _pending_confirm.pop(admin_id, None)
    await cb.answer("Saved!")


# ─────────────────────────────────────────────────────────────
#  Edit title
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^edit_title$") & filters.user(ADMINS))
async def cb_edit_title(client: Client, cb: CallbackQuery):
    if cb.from_user.id not in _pending_confirm:
        return await cb.answer("No pending upload.", show_alert=True)
    await cb.message.edit_text("✏️ Send the <b>corrected title</b> now:")
    await cb.answer()


@Client.on_message(filters.text & _admin_filter, group=1)
async def on_title_edit_reply(client: Client, message: Message):
    admin_id = message.from_user.id
    if admin_id not in _pending_confirm:
        return
    data          = _pending_confirm[admin_id]
    data["title"] = message.text.strip()
    ep_str        = f"S{data['season']:02d}E{data['episode']:02d}"
    await message.reply(
        f"✅ Title updated!\n\n"
        f"📌 <code>{data['title']}</code> · <code>{ep_str}</code> · <code>{data['quality']}</code>\n\nConfirm?",
        reply_markup=confirm_upload(data["title"], data["season"], data["episode"], data["quality"]),
    )


# ─────────────────────────────────────────────────────────────
#  Discard
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^discard_upload$") & filters.user(ADMINS))
async def cb_discard_upload(client: Client, cb: CallbackQuery):
    _pending_confirm.pop(cb.from_user.id, None)
    await cb.message.edit_text("🗑 Discarded.")
    await cb.answer()
