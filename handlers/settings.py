# v5 - 2026-03-20
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode

from config import ADMINS
from utils import pacing
from database.db import (
    get_settings, update_settings,
    add_channel, remove_channel, update_channel_qualities,
)
from keyboards import (
    settings_menu, quality_bots_menu, channel_manager,
    channel_quality_picker, close_button,
)
from services.log import log_settings_changed

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)
_edit_state: dict[int, str] = {}


# ─────────────────────────────────────────────────────────────
#  /settings entry
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & _admin_filter)
async def cmd_settings(client: Client, message: Message):
    settings = await get_settings(message.from_user.id)
    await pacing.reply(message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))


# ─────────────────────────────────────────────────────────────
#  Top-level settings buttons
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_mode_simple$") & filters.user(ADMINS))
async def cb_mode_simple(client: Client, cb: CallbackQuery):
    await update_settings(cb.from_user.id, post_mode="simple")
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer("Simple mode ✅")


@Client.on_callback_query(filters.regex("^set_mode_rich$") & filters.user(ADMINS))
async def cb_mode_rich(client: Client, cb: CallbackQuery):
    await update_settings(cb.from_user.id, post_mode="rich")
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer("Rich mode ✅")


@Client.on_callback_query(filters.regex("^set_caption$") & filters.user(ADMINS))
async def cb_set_caption(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "caption"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("caption_template", "")
    await pacing.edit(cb.message,
        "📝 <b>Caption Template</b>\n\nCurrent:\n<code>" + current + "</code>\n\nSend new template:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_btn_label$") & filters.user(ADMINS))
async def cb_set_btn_label(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "btn_label"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("button_label", "")
    await pacing.edit(cb.message,
        "🎛 <b>Button Label</b>\n\nCurrent: <code>" + current + "</code>\n\n"
        "Variables: <code>{quality}</code> <code>{ep_range}</code>\n\nSend new label:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_btn_layout$") & filters.user(ADMINS))
async def cb_set_btn_layout(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "btn_layout"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("button_layout", "2,1")
    await pacing.edit(cb.message,
        "⌨️ <b>Button Layout</b>\n\nCurrent: <code>" + current + "</code>\n\n"
        "Format: comma-separated row sizes e.g. <code>2,1</code> or <code>3</code>\n\nSend new layout:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_watermark$") & filters.user(ADMINS))
async def cb_set_watermark(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "watermark"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("watermark", "")
    text = (
        "🔖 <b>Thumbnail Watermark</b>\n\n"
        "Current: <code>" + (current or "Not set") + "</code>\n\n"
        "Send watermark text (e.g. <code>@MyChannel</code>)\n"
        "Send <code>-</code> to remove:"
    )
    await pacing.edit(cb.message, text, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_audio$") & filters.user(ADMINS))
async def cb_set_audio(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "audio"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("audio_info", "")
    await pacing.edit(cb.message,
        "🔊 <b>Audio Info</b>\n\nCurrent: <code>" + current + "</code>\n\nSend new audio info:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_subs$") & filters.user(ADMINS))
async def cb_set_subs(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "subs"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("sub_info", "")
    await pacing.edit(cb.message,
        "📝 <b>Subtitle Info</b>\n\nCurrent: <code>" + current + "</code>\n\nSend new subtitle info:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_sticker$") & filters.user(ADMINS))
async def cb_set_sticker(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "sticker"
    await pacing.edit(cb.message,
        "🎴 <b>Sticker</b>\n\nSend a sticker to use between episodes:",
        reply_markup=close_button(),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Sticker input
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.sticker & _admin_filter)
async def on_sticker_input(client: Client, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "sticker":
        return
    await update_settings(admin_id, sticker_id=message.sticker.file_id)
    _edit_state.pop(admin_id)
    settings = await get_settings(admin_id)
    await log_settings_changed(client, admin_id, "Sticker", "updated")
    await pacing.reply(message, "✅ Sticker saved!", reply_markup=settings_menu(settings))


# ─────────────────────────────────────────────────────────────
#  File store bots
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_quality_bots$") & filters.user(ADMINS))
async def cb_quality_bots(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message,
        "🤖 <b>File Store Bots</b>\n\nSet bot + DB channel per quality.\nFormat: <code>@BotUsername -100ChannelID</code>",
        reply_markup=quality_bots_menu(settings.get("quality_bots", {})),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^set_qbot_") & filters.user(ADMINS))
async def cb_set_qbot(client: Client, cb: CallbackQuery):
    quality = cb.data.replace("set_qbot_", "")
    _edit_state[cb.from_user.id] = "qbot_" + quality
    settings = await get_settings(cb.from_user.id)
    qbots    = settings.get("quality_bots", {})
    current  = qbots.get(quality, {})
    cur_text = "@" + current.get("bot","?") + " " + str(current.get("channel","?")) if current else "Not set"
    await pacing.edit(cb.message,
        "🤖 <b>" + quality + " File Store Bot</b>\n\nCurrent: <code>" + cur_text + "</code>\n\n"
        "Send: <code>@BotUsername -100ChannelID</code>",
        reply_markup=close_button(),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Channels
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_channels$") & filters.user(ADMINS))
async def cb_channels(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message,
        "📢 <b>Post Channels</b>\n\nAdd channels to post content to:",
        reply_markup=channel_manager(settings.get("channels", [])),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^add_channel$") & filters.user(ADMINS))
async def cb_add_channel(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "channel"
    await pacing.edit(cb.message,
        "📢 <b>Add Channel</b>\n\nSend channel ID or @username:\n<code>-1001234567890</code> or <code>@mychannel</code>",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^del_ch_") & filters.user(ADMINS))
async def cb_del_channel(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    await remove_channel(admin_id, ch_id)
    settings = await get_settings(admin_id)
    await pacing.edit(cb.message,
        "📢 <b>Post Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])),
    )
    await cb.answer("Channel removed")


@Client.on_callback_query(filters.regex(r"^ch_qual_") & filters.user(ADMINS))
async def cb_channel_quality(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    settings = await get_settings(admin_id)
    channels = settings.get("channels", [])
    ch       = next((c for c in channels if c["id"] == ch_id), None)
    if not ch:
        return await cb.answer("Channel not found", show_alert=True)
    selected = ch.get("qualities", ["480p","720p","1080p"])
    await pacing.edit(cb.message,
        "🎞 <b>Qualities for " + ch["name"] + "</b>\n\nSelect which qualities to post:",
        reply_markup=channel_quality_picker(ch_id, ch["name"], selected),
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^tq_") & filters.user(ADMINS))
async def cb_toggle_quality(client: Client, cb: CallbackQuery):
    parts    = cb.data.split("_")   # tq_{quality}_{ch_id}
    quality  = parts[1]
    ch_id    = int(parts[2])
    admin_id = cb.from_user.id
    settings = await get_settings(admin_id)
    channels = settings.get("channels", [])
    ch       = next((c for c in channels if c["id"] == ch_id), None)
    if not ch:
        return await cb.answer("Not found", show_alert=True)
    selected = ch.get("qualities", ["480p","720p","1080p"])
    if quality in selected:
        selected.remove(quality)
    else:
        selected.append(quality)
    await update_channel_qualities(admin_id, ch_id, selected)
    await pacing.edit_markup(cb.message, channel_quality_picker(ch_id, ch["name"], selected))
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^done_ch_qual_") & filters.user(ADMINS))
async def cb_done_channel_quality(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message,
        "📢 <b>Post Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])),
    )
    await cb.answer("Saved ✅")


@Client.on_callback_query(filters.regex("^back_to_settings$") & filters.user(ADMINS))
async def cb_back_to_settings(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Text input handler
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.text & _admin_filter, group=2)
async def on_text_input(client: Client, message: Message):
    admin_id = message.from_user.id
    state    = _edit_state.get(admin_id)
    if not state:
        return

    text = message.text.strip()

    async def _done(msg: str, **kwargs):
        _edit_state.pop(admin_id, None)
        settings = await get_settings(admin_id)
        await pacing.reply(message, msg, reply_markup=settings_menu(settings), **kwargs)

    if state == "caption":
        await update_settings(admin_id, caption_template=text)
        await log_settings_changed(client, admin_id, "Caption Template", "updated")
        await _done("✅ Caption template saved!")

    elif state == "btn_label":
        await update_settings(admin_id, button_label=text)
        await log_settings_changed(client, admin_id, "Button Label", text)
        await _done("✅ Button label set to: <code>" + text + "</code>", parse_mode=ParseMode.HTML)

    elif state == "btn_layout":
        try:
            [int(x) for x in text.split(",")]
        except ValueError:
            return await pacing.reply(message, "❌ Invalid format. Use e.g. <code>2,1</code> or <code>3</code>", parse_mode=ParseMode.HTML)
        await update_settings(admin_id, button_layout=text)
        await log_settings_changed(client, admin_id, "Button Layout", text)
        await _done("✅ Layout set to: <code>" + text + "</code>", parse_mode=ParseMode.HTML)

    elif state == "watermark":
        val = "" if text == "-" else text
        await update_settings(admin_id, watermark=val)
        await log_settings_changed(client, admin_id, "Watermark", val or "removed")
        await _done("✅ Watermark " + ("set to <code>" + val + "</code>" if val else "removed!"), parse_mode=ParseMode.HTML)

    elif state == "audio":
        await update_settings(admin_id, audio_info=text)
        await log_settings_changed(client, admin_id, "Audio Info", text)
        await _done("✅ Audio info: <code>" + text + "</code>", parse_mode=ParseMode.HTML)

    elif state == "subs":
        await update_settings(admin_id, sub_info=text)
        await log_settings_changed(client, admin_id, "Sub Info", text)
        await _done("✅ Subtitle info: <code>" + text + "</code>", parse_mode=ParseMode.HTML)

    elif state == "channel":
        try:
            chat    = await client.get_chat(int(text) if text.lstrip("-").isdigit() else text)
            ch_id   = chat.id
            ch_name = chat.title
        except Exception as e:
            return await pacing.reply(message, "❌ Could not find channel: <code>" + str(e) + "</code>", parse_mode=ParseMode.HTML)
        await add_channel(admin_id, ch_id, ch_name)
        _edit_state.pop(admin_id, None)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Channel Added", ch_name)
        await pacing.reply(message,
            "✅ Added: <b>" + ch_name + "</b>\n\nDefault qualities: 480p, 720p, 1080p",
            reply_markup=channel_manager(settings.get("channels", [])),
            parse_mode=ParseMode.HTML,
        )

    elif state and state.startswith("qbot_"):
        quality = state.split("_", 1)[1]
        parts   = text.replace("@", "").split()
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            return await pacing.reply(message,
                "❌ Invalid format.\nSend: <code>@BotUsername -100ChannelID</code>",
                parse_mode=ParseMode.HTML,
            )
        bot_username = parts[0]
        ch_id        = int(parts[1])
        from database.db import update_quality_bot
        await update_quality_bot(admin_id, quality, bot_username, ch_id)
        await log_settings_changed(client, admin_id, quality + " Bot", "@" + bot_username)
        _edit_state.pop(admin_id, None)
        settings = await get_settings(admin_id)
        await pacing.reply(message,
            "✅ <b>" + quality + "</b> → @" + bot_username + "\nDB Channel: <code>" + str(ch_id) + "</code>",
            reply_markup=quality_bots_menu(settings.get("quality_bots", {})),
            parse_mode=ParseMode.HTML,
        )
