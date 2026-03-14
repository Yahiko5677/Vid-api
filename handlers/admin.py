import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from pyrogram import Client
from config import ADMINS
from utils import pacing
from memory_store import get_all_pending, get_season_episodes, remove_episode, count_pending, clear_all_pending, clear_pending_season
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

@Client.on_message(filters.command("start") & _admin_filter)
async def cmd_start(client: Client, message: Message):
    await pacing.reply(message,
        "👋 <b>VideoSequenceBot</b>\n\n"
        "Send <code>.mkv</code> or <code>.mp4</code> files.\n\n"
        "<b>Commands:</b>\n"
        "/settings     — configure your bot\n"
        "/pending      — view pending episodes\n"
        "/clearpending — clear cached pending files\n"
        "/log          — recent activity log\n"
        "/stats        — view stats\n"
        "/cancel       — cancel current action",
        parse_mode=ParseMode.HTML,
        reply_markup=close_button(),
    )


# ─────────────────────────────────────────────────────────────
#  /pending
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("pending") & _admin_filter)
async def cmd_pending(client: Client, message: Message):
    admin_id = message.from_user.id
    docs     = get_all_pending(admin_id)

    if not docs:
        return await pacing.reply(message, "No pending episodes in memory.")

    groups: dict[str, list] = {}
    for doc in docs:
        key = doc["title_key"] + "__S" + str(doc["season"]).zfill(2)
        groups.setdefault(key, []).append(doc)

    lines   = ["<b>Pending Episodes</b>\n"]
    buttons = []

    for key, eps in groups.items():
        title  = eps[0]["title"]
        season = eps[0]["season"]
        lines.append("• <b>" + title + "</b> S" + str(season).zfill(2))
        for ep in sorted(eps, key=lambda x: x["episode"]):
            q_have   = list(ep.get("qualities", {}).keys())
            q_miss   = [q for q in ["480p", "720p", "1080p"] if q not in q_have]
            miss_str = " Missing: " + ", ".join(q_miss) if q_miss else " Ready"
            lines.append("  E" + str(ep["episode"]).zfill(2) + " " + miss_str)
        tk = eps[0]["title_key"]
        buttons.append([InlineKeyboardButton(
            "Post " + title + " S" + str(season).zfill(2),
            callback_data="force_post_" + tk + "_" + str(season)
        )])

    buttons.append([InlineKeyboardButton("Close", callback_data="close")])
    await pacing.reply(message,
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─────────────────────────────────────────────────────────────
#  /clearpending
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("clearpending") & _admin_filter)
async def cmd_clearpending(client: Client, message: Message):
    admin_id = message.from_user.id
    docs     = get_all_pending(admin_id)

    if not docs:
        return await pacing.reply(message, "No pending episodes to clear.")

    groups: dict[str, list] = {}
    for doc in docs:
        gkey = doc["title_key"] + "__S" + str(doc["season"]).zfill(2)
        groups.setdefault(gkey, []).append(doc)

    lines_out = ["<b>Clear Pending</b>\n"]
    buttons   = []
    for gkey, eps in groups.items():
        title  = eps[0]["title"]
        season = eps[0]["season"]
        tk     = eps[0]["title_key"]
        count  = len(eps)
        lines_out.append("• <b>" + title + "</b> S" + str(season).zfill(2) + " — " + str(count) + " ep(s)")
        buttons.append([InlineKeyboardButton(
            "🗑 " + title + " S" + str(season).zfill(2) + " (" + str(count) + " eps)",
            callback_data="clr_s_" + tk + "_" + str(season)
        )])

    buttons.append([InlineKeyboardButton(
        "🗑 Clear ALL (" + str(len(docs)) + " episodes)",
        callback_data="clr_all"
    )])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="close")])
    await pacing.reply(message, "\n".join(lines_out), reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^clr_all$") & filters.user(ADMINS))
async def cb_clear_all_pending(client: Client, cb: CallbackQuery):
    count = clear_all_pending(cb.from_user.id)
    await pacing.edit(cb.message, "Cleared <b>" + str(count) + "</b> pending episode(s) from memory + DB.")
    await cb.answer("Cleared!")


@Client.on_callback_query(filters.regex(r"^clr_s_") & filters.user(ADMINS))
async def cb_clear_pending_season(client: Client, cb: CallbackQuery):
    parts     = cb.data.split("_")
    season    = int(parts[-1])
    title_key = "_".join(parts[2:-1])
    count     = clear_pending_season(cb.from_user.id, title_key, season)
    await pacing.edit(cb.message,
        "Cleared <b>" + str(count) + "</b> ep(s) for S" + str(season).zfill(2) + " from memory + DB."
    )
    await cb.answer("Cleared!")


# ─────────────────────────────────────────────────────────────
#  /log
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("log") & _admin_filter)
async def cmd_log(client: Client, message: Message):
    await send_log_summary(client, message, message.from_user.id)


# ─────────────────────────────────────────────────────────────
#  /stats
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("stats") & _admin_filter)
async def cmd_stats(client: Client, message: Message):
    admin_id = message.from_user.id
    pending  = count_pending(admin_id)
    posted   = await pending_col.count_documents({"admin_id": admin_id, "status": "posted"})
    await pacing.reply(message,
        "<b>Your Stats</b>\n\n"
        "In memory (pending): <code>" + str(pending) + "</code>\n"
        "Posted (all time): <code>" + str(posted) + "</code>",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
#  /cancel
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("cancel") & _admin_filter)
async def cmd_cancel(client: Client, message: Message):
    _post_session.pop(message.from_user.id, None)
    await pacing.reply(message, "Action cancelled.")


# ─────────────────────────────────────────────────────────────
#  Force post
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^force_post_") & filters.user(ADMINS))
async def cb_force_post(client: Client, cb: CallbackQuery):
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
        return await pacing.edit(cb.message, "No channels configured. Use /settings to add channels first.")

    if len(channels) == 1:
        _post_session[admin_id]["channels_selected"] = [channels[0]["id"]]
        audio = settings.get("audio_info", "Hindi + English")
        subs  = settings.get("sub_info", "English")
        await pacing.edit(cb.message,
            "Posting to: <b>" + channels[0]["name"] + "</b>\n\n"
            "Audio: <code>" + audio + "</code>\nSubs: <code>" + subs + "</code>\n\nConfirm post?",
            parse_mode=ParseMode.HTML,
            reply_markup=post_confirm(audio, subs),
        )
    else:
        ep_label = title + " S" + str(season).zfill(2)
        await pacing.edit(cb.message,
            "Select channel(s) to post <b>" + ep_label + "</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=channel_picker(channels, []),
        )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Channel picker
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^pick_ch_") & filters.user(ADMINS))
async def cb_pick_channel(client: Client, cb: CallbackQuery):
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
    await pacing.edit_markup(cb.message, channel_picker(settings.get("channels", []), selected))
    await cb.answer()


@Client.on_callback_query(filters.regex("^confirm_channels$") & filters.user(ADMINS))
async def cb_confirm_channels(client: Client, cb: CallbackQuery):
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

    await pacing.edit(cb.message,
        "Posting to: <b>" + ", ".join(names) + "</b>\n\n"
        "Audio: <code>" + audio + "</code>\nSubs: <code>" + subs + "</code>\n\nConfirm post?",
        parse_mode=ParseMode.HTML,
        reply_markup=post_confirm(audio, subs),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Inline audio/subs edit
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^edit_audio$") & filters.user(ADMINS))
async def cb_edit_audio(client: Client, cb: CallbackQuery):
    if cb.from_user.id not in _post_session:
        return await cb.answer("No active session.", show_alert=True)
    _post_session[cb.from_user.id]["editing"] = "audio"
    await pacing.edit(cb.message, "Send the new audio info:", reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^edit_subs$") & filters.user(ADMINS))
async def cb_edit_subs(client: Client, cb: CallbackQuery):
    if cb.from_user.id not in _post_session:
        return await cb.answer("No active session.", show_alert=True)
    _post_session[cb.from_user.id]["editing"] = "subs"
    await pacing.edit(cb.message, "Send the new subtitle info:", reply_markup=close_button())
    await cb.answer()


@Client.on_message(filters.text & _admin_filter, group=3)
async def on_inline_edit_text(client: Client, message: Message):
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
    await pacing.reply(message,
        "Updated!\n\nAudio: <code>" + audio + "</code> | Subs: <code>" + subs + "</code>\n\nConfirm post?",
        parse_mode=ParseMode.HTML,
        reply_markup=post_confirm(audio, subs),
    )


# ─────────────────────────────────────────────────────────────
#  DO POST
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^do_post$") & filters.user(ADMINS))
async def cb_do_post(client: Client, cb: CallbackQuery):
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

    await pacing.edit(cb.message, "Posting...")
    await log_post_triggered(client, admin_id, title, season, len(episodes), ch_names, log_ch)

    try:
        await dispatch_post(client=client, channel_ids=ch_ids, episodes=episodes, settings=settings, meta=meta)

        for ep in episodes:
            remove_episode(admin_id, ep["title_key"], ep["season"], ep["episode"])
            await mark_posted(admin_id, ep["title_key"], ep["season"], ep["episode"])

        from handlers.upload import clear_title_cache
        clear_title_cache(admin_id, session["title_key"])

        await pacing.edit(cb.message,
            "Posted!\n\n" + title + " S" + str(season).zfill(2) + "\n" +
            str(len(episodes)) + " ep(s) to " + str(len(ch_ids)) + " channel(s)",
            parse_mode=ParseMode.HTML,
        )
        await log_post_success(client, admin_id, title, season, len(episodes), ch_names, mode, log_ch)

    except Exception as e:
        logger.error(f"Post failed: {e}")
        await pacing.edit(cb.message, "Post failed:\n<code>" + str(e) + "</code>", parse_mode=ParseMode.HTML)
        await log_post_failed(client, admin_id, title, str(e), log_ch)

    _post_session.pop(admin_id, None)
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Cancel / Close
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^cancel_post$") & filters.user(ADMINS))
async def cb_cancel_post(client: Client, cb: CallbackQuery):
    _post_session.pop(cb.from_user.id, None)
    await pacing.edit(cb.message, "Cancelled.")
    await cb.answer()


@Client.on_callback_query(filters.regex("^close$") & filters.user(ADMINS))
async def cb_close(client: Client, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()
