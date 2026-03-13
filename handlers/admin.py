import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from bot import Bot
from config import ADMINS
from memory_store import get_all_pending, get_season_episodes, remove_episode, count_pending
from database.db import get_settings, mark_posted, pending_col
from keyboards import channel_picker, post_confirm, force_post_keyboard, close_button
from services.post import dispatch_post
from services.metadata import fetch_metadata
from services.log import (
    send_log_summary, log_post_triggered,
    log_post_success, log_post_failed,
)

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)
_post_session: dict[int, dict] = {}


# ─────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("start") & _admin_filter)
async def cmd_start(client: Bot, message: Message):
    await message.reply(
        "👋 <b>VideoSequenceBot</b>\n\n"
        "Send <code>.mkv</code> or <code>.mp4</code> files — I'll group them by episode and post to your channels.\n\n"
        "<b>Commands:</b>\n"
        "/settings — configure your bot\n"
        "/pending  — view pending episodes\n"
        "/log      — recent activity log\n"
        "/stats    — view stats\n"
        "/cancel   — cancel current action",
        parse_mode=ParseMode.HTML,
        reply_markup=close_button(),
    )


# ─────────────────────────────────────────────────────────────
#  /pending
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("pending") & _admin_filter)
async def cmd_pending(client: Bot, message: Message):
    admin_id = message.from_user.id
    docs     = get_all_pending(admin_id)

    if not docs:
        return await message.reply("✅ No pending episodes in memory.")

    groups: dict[str, list] = {}
    for doc in docs:
        key = f"{doc['title_key']}__S{doc['season']:02d}"
        groups.setdefault(key, []).append(doc)

    lines   = ["📋 <b>Pending Episodes</b>\n"]
    buttons = []

    for key, eps in groups.items():
        title  = eps[0]["title"]
        season = eps[0]["season"]
        lines.append(f"• <b>{title}</b> S{season:02d}")
        for ep in sorted(eps, key=lambda x: x["episode"]):
            q_have   = list(ep.get("qualities", {}).keys())
            q_miss   = [q for q in ["480p", "720p", "1080p"] if q not in q_have]
            miss_str = f" ⚠️ Missing: {', '.join(q_miss)}" if q_miss else " ✅ Ready"
            lines.append(f"  └ E{ep['episode']:02d}{miss_str}")
        tk = eps[0]["title_key"]
        buttons.append([InlineKeyboardButton(
            f"🚀 Post {title} S{season:02d}",
            callback_data=f"force_post_{tk}_{season}"
        )])

    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    await message.reply(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─────────────────────────────────────────────────────────────
#  /log
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("log") & _admin_filter)
async def cmd_log(client: Bot, message: Message):
    await send_log_summary(client, message, message.from_user.id)


# ─────────────────────────────────────────────────────────────
#  /stats
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("stats") & _admin_filter)
async def cmd_stats(client: Bot, message: Message):
    admin_id = message.from_user.id
    pending  = count_pending(admin_id)
    posted   = await pending_col.count_documents({"admin_id": admin_id, "status": "posted"})
    await message.reply(
        f"📊 <b>Your Stats</b>\n\n"
        f"🧠 In memory (pending) : <code>{pending}</code>\n"
        f"✅ Posted (all time)   : <code>{posted}</code>",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
#  /cancel
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("cancel") & _admin_filter)
async def cmd_cancel(client: Bot, message: Message):
    _post_session.pop(message.from_user.id, None)
    await message.reply("❌ Action cancelled.")


# ─────────────────────────────────────────────────────────────
#  Force post
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex(r"^force_post_") & filters.user(ADMINS))
async def cb_force_post(client: Bot, cb: CallbackQuery):
    parts     = cb.data.split("_")
    season    = int(parts[-1])
    title_key = "_".join(parts[2:-1])
    admin_id  = cb.from_user.id
    episodes  = get_season_episodes(admin_id, title_key, season)

    if not episodes:
        return await cb.answer("No episodes found in memory.", show_alert=True)

    title    = episodes[0]["title"]
    settings = await get_settings(admin_id)

    meta = None
    if settings.get("post_mode") == "rich":
        meta = await fetch_metadata(title)

    _post_session[admin_id] = {
        "title_key":         title_key,
        "season":            season,
        "episodes":          episodes,
        "meta":              meta,
        "channels_selected": [],
        "audio_override":    None,
        "subs_override":     None,
    }

    channels = settings.get("channels", [])
    if not channels:
        return await cb.message.edit_text(
            "❌ No channels configured. Use /settings to add channels first."
        )

    if len(channels) == 1:
        _post_session[admin_id]["channels_selected"] = [channels[0]["id"]]
        audio = settings.get("audio_info", "Hindi + English")
        subs  = settings.get("sub_info", "English")
        await cb.message.edit_text(
            f"📢 Posting to: <b>{channels[0]['name']}</b>\n\n"
            f"🔊 Audio: <code>{audio}</code>\n📝 Subs: <code>{subs}</code>\n\nConfirm post?",
            parse_mode=ParseMode.HTML,
            reply_markup=post_confirm(audio, subs),
        )
    else:
        await cb.message.edit_text(
            f"📢 Select channel(s) for <b>{title} S{season:02d}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=channel_picker(channels, []),
        )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Channel picker
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex(r"^pick_ch_") & filters.user(ADMINS))
async def cb_pick_channel(client: Bot, cb: CallbackQuery):
    admin_id = cb.from_user.id
    ch_id    = int(cb.data.split("_")[-1])
    session  = _post_session.get(admin_id, {})
    selected = session.get("channels_selected", [])

    if ch_id in selected:
        selected.remove(ch_id)
    else:
        selected.append(ch_id)

    session["channels_selected"] = selected
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(channel_picker(settings.get("channels", []), selected))
    await cb.answer()


@Bot.on_callback_query(filters.regex("^confirm_channels$") & filters.user(ADMINS))
async def cb_confirm_channels(client: Bot, cb: CallbackQuery):
    admin_id = cb.from_user.id
    session  = _post_session.get(admin_id, {})
    selected = session.get("channels_selected", [])

    if not selected:
        return await cb.answer("Select at least one channel.", show_alert=True)

    settings     = await get_settings(admin_id)
    audio        = settings.get("audio_info", "Hindi + English")
    subs         = settings.get("sub_info", "English")
    all_channels = settings.get("channels", [])
    names        = [c["name"] for c in all_channels if c["id"] in selected]

    await cb.message.edit_text(
        f"📢 Posting to: <b>{', '.join(names)}</b>\n\n"
        f"🔊 Audio: <code>{audio}</code>\n📝 Subs: <code>{subs}</code>\n\nConfirm post?",
        parse_mode=ParseMode.HTML,
        reply_markup=post_confirm(audio, subs),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Inline audio/subs edit
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^edit_audio$") & filters.user(ADMINS))
async def cb_edit_audio(client: Bot, cb: CallbackQuery):
    if cb.from_user.id not in _post_session:
        return await cb.answer("No active session.", show_alert=True)
    _post_session[cb.from_user.id]["editing"] = "audio"
    await cb.message.edit_text("🔊 Send the new audio info:", reply_markup=close_button())
    await cb.answer()


@Bot.on_callback_query(filters.regex("^edit_subs$") & filters.user(ADMINS))
async def cb_edit_subs(client: Bot, cb: CallbackQuery):
    if cb.from_user.id not in _post_session:
        return await cb.answer("No active session.", show_alert=True)
    _post_session[cb.from_user.id]["editing"] = "subs"
    await cb.message.edit_text("📝 Send the new subtitle info:", reply_markup=close_button())
    await cb.answer()


@Bot.on_message(filters.text & _admin_filter, group=3)
async def on_inline_edit_text(client: Bot, message: Message):
    admin_id = message.from_user.id
    session  = _post_session.get(admin_id, {})
    editing  = session.get("editing")
    if not editing:
        return

    settings = await get_settings(admin_id)
    if editing == "audio":
        session["audio_override"] = message.text.strip()
        audio = message.text.strip()
        subs  = session.get("subs_override") or settings.get("sub_info", "English")
    else:
        session["subs_override"] = message.text.strip()
        subs  = message.text.strip()
        audio = session.get("audio_override") or settings.get("audio_info", "Hindi + English")

    session.pop("editing", None)
    await message.reply(
        f"✅ Updated!\n\n🔊 <code>{audio}</code> | 📝 <code>{subs}</code>\n\nConfirm post?",
        parse_mode=ParseMode.HTML,
        reply_markup=post_confirm(audio, subs),
    )


# ─────────────────────────────────────────────────────────────
#  DO POST
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^do_post$") & filters.user(ADMINS))
async def cb_do_post(client: Bot, cb: CallbackQuery):
    admin_id = cb.from_user.id
    session  = _post_session.get(admin_id)
    if not session:
        return await cb.answer("No active post session.", show_alert=True)

    settings     = await get_settings(admin_id)
    ch_ids       = session["channels_selected"]
    episodes     = session["episodes"]
    meta         = session.get("meta")
    title        = episodes[0]["title"]
    season       = episodes[0]["season"]
    mode         = settings.get("post_mode", "simple")
    all_channels = settings.get("channels", [])
    ch_names     = [c["name"] for c in all_channels if c["id"] in ch_ids]
    log_ch       = settings.get("log_channel_id")

    if session.get("audio_override"):
        settings["audio_info"] = session["audio_override"]
    if session.get("subs_override"):
        settings["sub_info"] = session["subs_override"]

    await cb.message.edit_text("⏳ Posting...")
    await log_post_triggered(client, admin_id, title, season, len(episodes), ch_names, log_ch)

    try:
        await dispatch_post(client=client, channel_ids=ch_ids, episodes=episodes, settings=settings, meta=meta)

        for ep in episodes:
            remove_episode(admin_id, ep["title_key"], ep["season"], ep["episode"])
            await mark_posted(admin_id, ep["title_key"], ep["season"], ep["episode"])

        await cb.message.edit_text(
            f"✅ <b>Posted!</b>\n\n📺 {title} S{season:02d}\n"
            f"📊 {len(episodes)} ep(s) → {len(ch_ids)} channel(s)",
            parse_mode=ParseMode.HTML,
        )
        await log_post_success(client, admin_id, title, season, len(episodes), ch_names, mode, log_ch)

    except Exception as e:
        logger.error(f"Post failed: {e}")
        await cb.message.edit_text(f"❌ Post failed:\n<code>{e}</code>", parse_mode=ParseMode.HTML)
        await log_post_failed(client, admin_id, title, str(e), log_ch)

    _post_session.pop(admin_id, None)
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Cancel / Close
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^cancel_post$") & filters.user(ADMINS))
async def cb_cancel_post(client: Bot, cb: CallbackQuery):
    _post_session.pop(cb.from_user.id, None)
    await cb.message.edit_text("❌ Cancelled.")
    await cb.answer()


@Bot.on_callback_query(filters.regex("^close$") & filters.user(ADMINS))
async def cb_close(client: Bot, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()
