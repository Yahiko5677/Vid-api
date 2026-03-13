import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery

from bot import Bot
from config import ADMINS
from database.db import get_settings, update_settings, add_channel, remove_channel
from keyboards import settings_menu, channel_manager, close_button
from services.log import log_settings_changed

logger        = logging.getLogger(__name__)
_admin_filter = filters.private & filters.user(ADMINS)

# { admin_id: "audio" | "subs" | "sticker" | "channel" }
_edit_state: dict[int, str] = {}


# ─────────────────────────────────────────────────────────────
#  /settings
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.command("settings") & _admin_filter)
async def cmd_settings(client: Bot, message: Message):
    settings = await get_settings(message.from_user.id)
    mode     = settings.get("post_mode", "simple").capitalize()
    await message.reply(
        f"⚙️ <b>Your Settings</b>\n\nCurrent mode: <b>{mode}</b>",
        reply_markup=settings_menu(settings),
    )


# ─────────────────────────────────────────────────────────────
#  Mode toggle
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex(r"^set_mode_(simple|rich)$") & filters.user(ADMINS))
async def cb_set_mode(client: Bot, cb: CallbackQuery):
    mode     = "simple" if "simple" in cb.data else "rich"
    admin_id = cb.from_user.id
    await update_settings(admin_id, post_mode=mode)
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(settings_menu(settings))
    await log_settings_changed(client, admin_id, "Post Mode", mode)
    await cb.answer(f"✅ Mode set to {mode.capitalize()}")


# ─────────────────────────────────────────────────────────────
#  Audio / Subs
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^set_audio$") & filters.user(ADMINS))
async def cb_set_audio(client: Bot, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "audio"
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        f"🔊 Current: <code>{settings.get('audio_info', 'Hindi + English')}</code>\n\nSend new audio info:",
        reply_markup=close_button(),
    )
    await cb.answer()


@Bot.on_callback_query(filters.regex("^set_subs$") & filters.user(ADMINS))
async def cb_set_subs(client: Bot, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "subs"
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        f"📝 Current: <code>{settings.get('sub_info', 'English')}</code>\n\nSend new subtitle info:",
        reply_markup=close_button(),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Sticker
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^set_sticker$") & filters.user(ADMINS))
async def cb_set_sticker(client: Bot, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "sticker"
    await cb.message.edit_text(
        "🎴 Send a sticker to set it.\nSent between episodes and at end of season.",
        reply_markup=close_button(),
    )
    await cb.answer()


@Bot.on_message(filters.sticker & _admin_filter)
async def on_sticker_received(client: Bot, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "sticker":
        return
    await update_settings(admin_id, sticker_id=message.sticker.file_id)
    _edit_state.pop(admin_id)
    settings = await get_settings(admin_id)
    await log_settings_changed(client, admin_id, "Sticker", "updated")
    await message.reply("✅ Sticker saved!", reply_markup=settings_menu(settings))


# ─────────────────────────────────────────────────────────────
#  Channels
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^set_channels$") & filters.user(ADMINS))
async def cb_set_channels(client: Bot, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    await cb.message.edit_text(
        "📢 <b>Your Target Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])),
    )
    await cb.answer()


@Bot.on_callback_query(filters.regex("^add_channel$") & filters.user(ADMINS))
async def cb_add_channel(client: Bot, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "channel"
    await cb.message.edit_text(
        "📢 <b>Add a channel</b>\n\n"
        "• Forward any message from the channel\n"
        "• Send channel username (e.g. <code>@MyChannel</code>)\n"
        "• Send channel ID (e.g. <code>-1001234567890</code>)",
        reply_markup=close_button(),
    )
    await cb.answer()


@Bot.on_callback_query(filters.regex(r"^remove_ch_-?\d+$") & filters.user(ADMINS))
async def cb_remove_channel(client: Bot, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    await remove_channel(admin_id, ch_id)
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(channel_manager(settings.get("channels", [])))
    await cb.answer("✅ Channel removed")


# ─────────────────────────────────────────────────────────────
#  Text input dispatcher (audio / subs / channel)
# ─────────────────────────────────────────────────────────────

@Bot.on_message(filters.text & _admin_filter, group=2)
async def on_text_input(client: Bot, message: Message):
    admin_id = message.from_user.id
    state    = _edit_state.get(admin_id)

    if state == "audio":
        await update_settings(admin_id, audio_info=message.text.strip())
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Audio Info", message.text.strip())
        await message.reply("✅ Audio info updated!", reply_markup=settings_menu(settings))

    elif state == "subs":
        await update_settings(admin_id, sub_info=message.text.strip())
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Sub Info", message.text.strip())
        await message.reply("✅ Subtitle info updated!", reply_markup=settings_menu(settings))

    elif state == "channel":
        txt    = message.text.strip()
        ch_id  = None
        ch_name = None
        try:
            chat    = await client.get_chat(int(txt) if txt.lstrip("-").isdigit() else txt)
            ch_id   = chat.id
            ch_name = chat.title
        except Exception as e:
            return await message.reply(f"❌ Could not find channel: <code>{e}</code>")

        await add_channel(admin_id, ch_id, ch_name)
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await log_settings_changed(client, admin_id, "Channel Added", ch_name)
        await message.reply(f"✅ Added: <b>{ch_name}</b>", reply_markup=channel_manager(settings.get("channels", [])))


@Bot.on_message(filters.forwarded & _admin_filter)
async def on_forwarded_channel(client: Bot, message: Message):
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
    await message.reply(f"✅ Added: <b>{ch_name}</b>", reply_markup=channel_manager(settings.get("channels", [])))


# ─────────────────────────────────────────────────────────────
#  Back / Close
# ─────────────────────────────────────────────────────────────

@Bot.on_callback_query(filters.regex("^back_settings$") & filters.user(ADMINS))
async def cb_back_settings(client: Bot, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    mode     = settings.get("post_mode", "simple").capitalize()
    await cb.message.edit_text(
        f"⚙️ <b>Your Settings</b>\n\nCurrent mode: <b>{mode}</b>",
        reply_markup=settings_menu(settings),
    )
    await cb.answer()


@Bot.on_callback_query(filters.regex("^close_settings$") & filters.user(ADMINS))
async def cb_close_settings(client: Bot, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()
