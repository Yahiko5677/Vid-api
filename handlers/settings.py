"""
/settings handler — full per-admin UX configuration.
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode

from config import ADMINS
from database.db import (
    get_settings, update_settings,
    add_channel, remove_channel, update_channel_qualities,
    set_quality_bot,
)
from keyboards import (
    settings_menu, quality_bots_menu, channel_manager,
    channel_quality_picker, close_button,
)
from services.log import log_settings_changed

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)

# { admin_id: state_string }
_edit_state: dict[int, str] = {}

# Temp quality picker state: { admin_id: { channel_id: int, selected: list } }
_cq_state: dict[int, dict] = {}

# Template variable help text
_CAPTION_VARS = (
    "<b>Available variables:</b>\n"
    "<code>{title}</code> — series title\n"
    "<code>{year}</code> — year\n"
    "<code>{genres}</code> — genres\n"
    "<code>{score}</code> — MAL score\n"
    "<code>{episodes}</code> — total episodes\n"
    "<code>{studio}</code> — studio\n"
    "<code>{synopsis}</code> — synopsis\n"
    "<code>{season}</code> — Season N\n"
    "<code>{ep_range}</code> — E01-E13\n"
    "<code>{audio}</code> — audio info\n"
    "<code>{subs}</code> — subtitle info\n\n"
    "Send your template now:"
)

_BUTTON_VARS = (
    "<b>Button label variables:</b>\n"
    "<code>{quality}</code> — e.g. 480p\n"
    "<code>{ep_range}</code> — e.g. E01-E13\n\n"
    "Example: <code>📥 {quality}  •  {ep_range}</code>\n\n"
    "Send your label template now:"
)

_LAYOUT_HELP = (
    "<b>Button layout</b> — comma-separated row sizes\n\n"
    "Examples:\n"
    "<code>2,1</code>  →  [480p][720p] / [1080p]\n"
    "<code>3</code>    →  [480p][720p][1080p]\n"
    "<code>1,1,1</code> → each on own row\n\n"
    "Send layout string now:"
)


# ─────────────────────────────────────────────────────────────
#  /settings
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & _admin_filter)
async def cmd_settings(client: Client, message: Message):
    settings = await get_settings(message.from_user.id)
    mode     = settings.get("post_mode", "simple").capitalize()
    await message.reply(
        f"⚙️ <b>Your Settings</b>\n\nMode: <b>{mode}</b>",
        reply_markup=settings_menu(settings),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
#  Mode
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^set_mode_(simple|rich)$") & filters.user(ADMINS))
async def cb_set_mode(client: Client, cb: CallbackQuery):
    mode     = "simple" if "simple" in cb.data else "rich"
    admin_id = cb.from_user.id
    await update_settings(admin_id, post_mode=mode)
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(settings_menu(settings))
    await log_settings_changed(client, admin_id, "Post Mode", mode)
    await cb.answer(f"✅ {mode.capitalize()} mode set")


# ─────────────────────────────────────────────────────────────
#  Caption template
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_caption$") & filters.user(ADMINS))
async def cb_set_caption(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "caption"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("caption_template", "")
    await cb.message.edit_text(
        f"📝 <b>Caption Template</b>\n\n"
        f"Current:\n<code>{current[:300]}</code>\n\n"
        f"{_CAPTION_VARS}",
        reply_markup=close_button(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Button label
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_btn_label$") & filters.user(ADMINS))
async def cb_set_btn_label(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "btn_label"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("button_label", "")
    await cb.message.edit_text(
        f"🏷 <b>Button Label</b>\n\nCurrent: <code>{current}</code>\n\n{_BUTTON_VARS}",
        reply_markup=close_button(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Button layout
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_btn_layout$") & filters.user(ADMINS))
async def cb_set_btn_layout(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "btn_layout"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("button_layout", "2,1")
    await cb.message.edit_text(
        f"⌨️ <b>Button Layout</b>\n\nCurrent: <code>{current}</code>\n\n{_LAYOUT_HELP}",
        reply_markup=close_button(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Audio / Subs
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_audio$") & filters.user(ADMINS))
async def cb_set_audio(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "audio"
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        f"🔊 Current: <code>{settings.get('audio_info','')}</code>\n\nSend new audio info:",
        reply_markup=close_button(), parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_subs$") & filters.user(ADMINS))
async def cb_set_subs(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "subs"
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        f"📝 Current: <code>{settings.get('sub_info','')}</code>\n\nSend new subtitle info:",
        reply_markup=close_button(), parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Sticker
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_sticker$") & filters.user(ADMINS))
async def cb_set_sticker(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "sticker"
    await cb.message.edit_text(
        "🎴 Send a sticker — used between episodes and at end of season:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Client.on_message(filters.sticker & _admin_filter)
async def on_sticker_received(client: Client, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "sticker":
        return
    await update_settings(admin_id, sticker_id=message.sticker.file_id)
    _edit_state.pop(admin_id)
    settings = await get_settings(admin_id)
    await log_settings_changed(client, admin_id, "Sticker", "updated")
    await message.reply("✅ Sticker saved!", reply_markup=settings_menu(settings))


# ─────────────────────────────────────────────────────────────
#  Quality Bots
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_quality_bots$") & filters.user(ADMINS))
async def cb_set_quality_bots(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        "🤖 <b>File Store Bots</b>\n\n"
        "Set which File Store Bot handles each quality.\n"
        "Each bot needs its own DB channel.",
        reply_markup=quality_bots_menu(settings.get("quality_bots", {})),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^set_qbot_(480p|720p|1080p)$") & filters.user(ADMINS))
async def cb_set_qbot(client: Client, cb: CallbackQuery):
    quality = cb.data.split("_")[-1]
    _edit_state[cb.from_user.id] = f"qbot_{quality}"
    await cb.message.edit_text(
        f"🤖 <b>Set File Store Bot for {quality}</b>\n\n"
        f"Send in this format:\n"
        f"<code>@BotUsername -100ChannelID</code>\n\n"
        f"Example:\n"
        f"<code>@MyFileBot480 -1001234567890</code>",
        reply_markup=close_button(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Channels
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_channels$") & filters.user(ADMINS))
async def cb_set_channels(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        "📢 <b>Your Channels</b>\n\nEach channel can have specific qualities assigned:",
        reply_markup=channel_manager(settings.get("channels", [])),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^add_channel$") & filters.user(ADMINS))
async def cb_add_channel(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "channel"
    await cb.message.edit_text(
        "📢 <b>Add Channel</b>\n\n"
        "• Forward any message from the channel\n"
        "• Send username: <code>@MyChannel</code>\n"
        "• Send ID: <code>-1001234567890</code>",
        reply_markup=close_button(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^ch_quals_-?\d+$") & filters.user(ADMINS))
async def cb_ch_qualities(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    settings = await get_settings(admin_id)
    channels = settings.get("channels", [])
    ch       = next((c for c in channels if c["id"] == ch_id), None)
    if not ch:
        return await cb.answer("Channel not found.", show_alert=True)

    selected = ch.get("qualities", ["480p","720p","1080p"])
    _cq_state[admin_id] = {"channel_id": ch_id, "selected": list(selected)}

    await cb.message.edit_text(
        f"⚙️ <b>Quality Assignment</b>\n📢 {ch['name']}\n\nToggle which qualities go to this channel:",
        reply_markup=channel_quality_picker(ch_id, ch["name"], selected),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^cqtoggle_-?\d+_(480p|720p|1080p)$") & filters.user(ADMINS))
async def cb_cq_toggle(client: Client, cb: CallbackQuery):
    parts    = cb.data.split("_")
    quality  = parts[-1]
    ch_id    = int(parts[1])
    admin_id = cb.from_user.id
    state    = _cq_state.get(admin_id, {})
    selected = state.get("selected", [])

    if quality in selected:
        selected.remove(quality)
    else:
        selected.append(quality)

    state["selected"] = selected
    _cq_state[admin_id] = state

    settings = await get_settings(admin_id)
    channels = settings.get("channels", [])
    ch       = next((c for c in channels if c["id"] == ch_id), {})
    await cb.message.edit_reply_markup(
        channel_quality_picker(ch_id, ch.get("name",""), selected)
    )
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^cqsave_-?\d+$") & filters.user(ADMINS))
async def cb_cq_save(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    state    = _cq_state.pop(admin_id, {})
    selected = state.get("selected", [])

    await update_channel_qualities(admin_id, ch_id, selected)
    settings = await get_settings(admin_id)
    await cb.message.edit_text(
        "✅ Quality assignment saved!\n\n📢 <b>Your Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer("✅ Saved")


@Client.on_callback_query(filters.regex(r"^remove_ch_-?\d+$") & filters.user(ADMINS))
async def cb_remove_channel(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    await remove_channel(admin_id, ch_id)
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(channel_manager(settings.get("channels", [])))
    await cb.answer("✅ Removed")


@Client.on_callback_query(filters.regex(r"^ch_info_-?\d+$") & filters.user(ADMINS))
async def cb_ch_info(client: Client, cb: CallbackQuery):
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Text input dispatcher
# ─────────────────────────────────────────────────────────────

@Client.on_message(
    filters.text
    & ~filters.command(["start","settings","pending","log","stats","cancel"])
    & _admin_filter,
    group=2
)
async def on_text_input(client: Client, message: Message):
    admin_id = message.from_user.id
    state    = _edit_state.get(admin_id)
    if not state:
        return

    text = message.text.strip()

    if state == "caption":
        await update_settings(admin_id, caption_template=text)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Caption Template", "updated")
        await message.reply("✅ Caption template saved!", reply_markup=settings_menu(settings))

    elif state == "btn_label":
        await update_settings(admin_id, button_label=text)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Button Label", text)
        await message.reply(f"✅ Button label set to: <code>{text}</code>",
                           reply_markup=settings_menu(settings), parse_mode=ParseMode.HTML)

    elif state == "btn_layout":
        # Validate layout format
        try:
            [int(x) for x in text.split(",")]
        except ValueError:
            return await message.reply("❌ Invalid format. Use e.g. <code>2,1</code> or <code>3</code>",
                                      parse_mode=ParseMode.HTML)
        await update_settings(admin_id, button_layout=text)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Button Layout", text)
        await message.reply(f"✅ Layout set to: <code>{text}</code>",
                           reply_markup=settings_menu(settings), parse_mode=ParseMode.HTML)

    elif state == "audio":
        await update_settings(admin_id, audio_info=text)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Audio Info", text)
        await message.reply("✅ Audio info updated!", reply_markup=settings_menu(settings))

    elif state == "subs":
        await update_settings(admin_id, sub_info=text)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Sub Info", text)
        await message.reply("✅ Subtitle info updated!", reply_markup=settings_menu(settings))

    elif state == "channel":
        try:
            chat    = await client.get_chat(int(text) if text.lstrip("-").isdigit() else text)
            ch_id   = chat.id
            ch_name = chat.title
        except Exception as e:
            return await message.reply(f"❌ Could not find channel: <code>{e}</code>",
                                      parse_mode=ParseMode.HTML)
        await add_channel(admin_id, ch_id, ch_name)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Channel Added", ch_name)
        await message.reply(
            f"✅ Added: <b>{ch_name}</b>\n\nDefault qualities: 480p, 720p, 1080p\nChange via ⚙️ Qualities button.",
            reply_markup=channel_manager(settings.get("channels", [])),
            parse_mode=ParseMode.HTML,
        )

    elif state and state.startswith("qbot_"):
        # Format: @BotUsername -100ChannelID
        quality = state.split("_", 1)[1]
        parts   = text.replace("@", "").split()
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            return await message.reply(
                "❌ Invalid format.\nSend: <code>@BotUsername -100ChannelID</code>",
                parse_mode=ParseMode.HTML
            )
        bot_username = parts[0]
        channel_id   = int(parts[1])
        await set_quality_bot(admin_id, quality, bot_username, channel_id)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, f"Bot {quality}", bot_username)
        await message.reply(
            f"✅ <b>{quality}</b> → @{bot_username}\n\n🤖 <b>File Store Bots</b>",
            reply_markup=quality_bots_menu(settings.get("quality_bots", {})),
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────────────────────
#  Forwarded channel message (for add_channel)
# ─────────────────────────────────────────────────────────────

@Client.on_message(filters.forwarded & _admin_filter)
async def on_forwarded_channel(client: Client, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "channel":
        return
    if not message.forward_from_chat:
        return await message.reply("❌ Could not detect a channel from this forward.")
    ch_id   = message.forward_from_chat.id
    ch_name = message.forward_from_chat.title
    await add_channel(admin_id, ch_id, ch_name)
    _edit_state.pop(admin_id)
    settings = await get_settings(admin_id)
    await log_settings_changed(client, admin_id, "Channel Added", ch_name)
    await message.reply(
        f"✅ Added: <b>{ch_name}</b>\n\nDefault qualities: 480p, 720p, 1080p",
        reply_markup=channel_manager(settings.get("channels", [])),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
#  Back / Close
# ─────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^back_settings$") & filters.user(ADMINS))
async def cb_back_settings(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    mode     = settings.get("post_mode", "simple").capitalize()
    await cb.message.edit_text(
        f"⚙️ <b>Your Settings</b>\n\nMode: <b>{mode}</b>",
        reply_markup=settings_menu(settings),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@Client.on_callback_query(filters.regex("^close_settings$") & filters.user(ADMINS))
async def cb_close_settings(client: Client, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()
