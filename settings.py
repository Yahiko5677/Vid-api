"""
/settings handler — per-admin configuration.

Menu options:
  • Switch Simple / Rich mode
  • Set audio + subtitle info
  • Set sticker
  • Manage target channels (add via forward or username/ID)
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from helper_func import admin
from config import ADMINS
from database import get_settings, update_settings, add_channel, remove_channel
from keyboards import settings_menu, channel_manager, close_button

logger = logging.getLogger(__name__)

# In-memory: tracks what each admin is currently editing
# { admin_id: "audio" | "subs" | "sticker" | "channel" }
_edit_state: dict[int, str] = {}


# ─────────────────────────────────────────────────────────────
#  /settings command
# ─────────────────────────────────────────────────────────────

async def cmd_settings(client: Client, message: Message):
    admin_id = message.from_user.id
    settings = await get_settings(admin_id)
    mode     = settings.get("post_mode", "simple").capitalize()
    await message.reply(
        f"⚙️ **Your Settings**\n\nCurrent mode: **{mode}**",
        reply_markup=settings_menu(settings),
    )


# ─────────────────────────────────────────────────────────────
#  Mode toggle
# ─────────────────────────────────────────────────────────────

async def cb_set_mode(client: Client, cb: CallbackQuery):
    mode     = "simple" if "simple" in cb.data else "rich"
    admin_id = cb.from_user.id
    await update_settings(admin_id, post_mode=mode)
    settings = await get_settings(admin_id)
    await cb.message.edit_reply_markup(settings_menu(settings))
    await cb.answer(f"✅ Mode set to {mode.capitalize()}")


# ─────────────────────────────────────────────────────────────
#  Audio/Subs
# ─────────────────────────────────────────────────────────────

async def cb_set_audio(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "audio"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("audio_info", "Hindi + English")
    await cb.message.edit_text(
        f"🔊 Current audio info: `{current}`\n\n"
        f"Send new audio info (e.g. `Hindi + English + Tamil`):",
        reply_markup=close_button(),
    )
    await cb.answer()


async def cb_set_subs(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "subs"
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("sub_info", "English")
    await cb.message.edit_text(
        f"📝 Current subtitle info: `{current}`\n\n"
        f"Send new subtitle info (e.g. `English | Hindi`):",
        reply_markup=close_button(),
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Sticker
# ─────────────────────────────────────────────────────────────

async def cb_set_sticker(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "sticker"
    await cb.message.edit_text(
        "🎴 Send a sticker to set it.\n"
        "This sticker will be sent between episodes and at end of season.",
        reply_markup=close_button(),
    )
    await cb.answer()


async def on_sticker_received(client: Client, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "sticker":
        return
    sticker_id = message.sticker.file_id
    await update_settings(admin_id, sticker_id=sticker_id)
    _edit_state.pop(admin_id, None)
    settings = await get_settings(admin_id)
    await message.reply(
        "✅ Sticker saved!\n\n⚙️ **Your Settings**",
        reply_markup=settings_menu(settings),
    )


# ─────────────────────────────────────────────────────────────
#  Channel management
# ─────────────────────────────────────────────────────────────

async def cb_set_channels(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    channels = settings.get("channels", [])
    await cb.message.edit_text(
        "📢 **Your Target Channels**\n\nAdd or remove channels below:",
        reply_markup=channel_manager(channels),
    )
    await cb.answer()


async def cb_add_channel(client: Client, cb: CallbackQuery):
    _edit_state[cb.from_user.id] = "channel"
    await cb.message.edit_text(
        "📢 **Add a channel**\n\n"
        "Either:\n"
        "• Forward any message from the channel\n"
        "• Send the channel username (e.g. `@MyChannel`)\n"
        "• Send the channel ID (e.g. `-1001234567890`)",
        reply_markup=close_button(),
    )
    await cb.answer()


async def cb_remove_channel(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    await remove_channel(admin_id, ch_id)
    settings = await get_settings(admin_id)
    channels = settings.get("channels", [])
    await cb.message.edit_reply_markup(channel_manager(channels))
    await cb.answer("✅ Channel removed")


async def on_channel_input(client: Client, message: Message):
    """Handle forwarded message OR username/ID text to add a channel."""
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "channel":
        return

    ch_id   = None
    ch_name = None

    # Forwarded from channel
    if message.forward_from_chat:
        ch_id   = message.forward_from_chat.id
        ch_name = message.forward_from_chat.title

    # Text input: username or ID
    elif message.text:
        txt = message.text.strip()
        try:
            if txt.lstrip("-").isdigit():
                ch_id = int(txt)
                chat  = await client.get_chat(ch_id)
            else:
                chat  = await client.get_chat(txt)
                ch_id = chat.id
            ch_name = chat.title
        except Exception as e:
            await message.reply(f"❌ Could not find channel: `{e}`\n\nTry again or /cancel")
            return

    if ch_id and ch_name:
        await add_channel(admin_id, ch_id, ch_name)
        _edit_state.pop(admin_id, None)
        settings = await get_settings(admin_id)
        await message.reply(
            f"✅ Added: **{ch_name}**\n\n📢 **Your Target Channels**",
            reply_markup=channel_manager(settings.get("channels", [])),
        )
    else:
        await message.reply("❌ Could not detect a channel. Please try again.")


# ─────────────────────────────────────────────────────────────
#  Text input dispatcher (audio / subs)
# ─────────────────────────────────────────────────────────────

async def on_text_input(client: Client, message: Message):
    admin_id = message.from_user.id
    state    = _edit_state.get(admin_id)

    if state == "audio":
        await update_settings(admin_id, audio_info=message.text.strip())
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await message.reply("✅ Audio info updated!\n\n⚙️ **Your Settings**",
                            reply_markup=settings_menu(settings))

    elif state == "subs":
        await update_settings(admin_id, sub_info=message.text.strip())
        _edit_state.pop(admin_id)
        settings = await get_settings(admin_id)
        await message.reply("✅ Subtitle info updated!\n\n⚙️ **Your Settings**",
                            reply_markup=settings_menu(settings))

    elif state == "channel":
        await on_channel_input(client, message)


# ─────────────────────────────────────────────────────────────
#  Back / close helpers
# ─────────────────────────────────────────────────────────────

async def cb_back_settings(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    mode = settings.get("post_mode", "simple").capitalize()
    await cb.message.edit_text(
        f"⚙️ **Your Settings**\n\nCurrent mode: **{mode}**",
        reply_markup=settings_menu(settings),
    )
    await cb.answer()


async def cb_close_settings(client: Client, cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()


# ─────────────────────────────────────────────────────────────
#  Register
# ─────────────────────────────────────────────────────────────

def register(app: Client):
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from config import ADMINS as _ADMINS

    _admin_filter = filters.user(_ADMINS)

    app.add_handler(MessageHandler(cmd_settings,     filters.command("settings") & filters.private & _admin_filter))
    app.add_handler(MessageHandler(on_sticker_received, filters.private & _admin_filter & filters.sticker), group=2)
    app.add_handler(MessageHandler(on_text_input,    filters.private & _admin_filter & filters.text), group=2)
    app.add_handler(MessageHandler(on_channel_input, filters.private & _admin_filter & filters.forwarded), group=2)

    app.add_handler(CallbackQueryHandler(cb_set_mode,      filters.regex(r"^set_mode_(simple|rich)$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_set_audio,     filters.regex("^set_audio$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_set_sticker,   filters.regex("^set_sticker$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_set_channels,  filters.regex("^set_channels$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_add_channel,   filters.regex("^add_channel$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_remove_channel,filters.regex(r"^remove_ch_-?\d+$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_back_settings, filters.regex("^back_settings$") & _admin_filter))
    app.add_handler(CallbackQueryHandler(cb_close_settings,filters.regex("^close_settings$") & _admin_filter))
