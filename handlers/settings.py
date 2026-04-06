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

# state per admin: what field is being edited
_edit_state: dict[int, str] = {}
# store the settings message to edit it in place
_settings_msg: dict[int, object] = {}


# ── /settings ─────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & _admin_filter)
async def cmd_settings(client: Client, message: Message):
    admin_id = message.from_user.id
    settings = await get_settings(admin_id)
    sent = await pacing.reply(message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    _settings_msg[admin_id] = sent


async def _refresh_settings(client, admin_id: int):
    """Edit the original settings message in-place."""
    settings = await get_settings(admin_id)
    msg      = _settings_msg.get(admin_id)
    if msg:
        try:
            await pacing.edit(msg, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
            return
        except Exception:
            pass
    # fallback: can't edit, do nothing (avoid duplicate)


# ── Close / Back ───────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^close_settings$") & filters.user(ADMINS))
async def cb_close_settings(client: Client, cb: CallbackQuery):
    admin_id = cb.from_user.id
    _edit_state.pop(admin_id, None)
    _settings_msg[admin_id] = cb.message
    settings = await get_settings(admin_id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer()


@Client.on_callback_query(filters.regex("^back_to_settings$") & filters.user(ADMINS))
async def cb_back_to_settings(client: Client, cb: CallbackQuery):
    admin_id = cb.from_user.id
    _settings_msg[admin_id] = cb.message
    settings = await get_settings(admin_id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer()


# ── Post mode ──────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_mode_simple$") & filters.user(ADMINS))
async def cb_mode_simple(client: Client, cb: CallbackQuery):
    await update_settings(cb.from_user.id, post_mode="simple")
    _settings_msg[cb.from_user.id] = cb.message
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer("✅ Simple mode")


@Client.on_callback_query(filters.regex("^set_mode_rich$") & filters.user(ADMINS))
async def cb_mode_rich(client: Client, cb: CallbackQuery):
    await update_settings(cb.from_user.id, post_mode="rich")
    _settings_msg[cb.from_user.id] = cb.message
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "⚙️ <b>Settings</b>", reply_markup=settings_menu(settings))
    await cb.answer("✅ Rich mode")


# ── Text setting prompts ───────────────────────────────────────

def _prompt(cb: CallbackQuery, state: str, text: str):
    _edit_state[cb.from_user.id] = state
    _settings_msg[cb.from_user.id] = cb.message
    return text


@Client.on_callback_query(filters.regex("^set_caption$") & filters.user(ADMINS))
async def cb_set_caption(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("caption_template", "")
    txt = _prompt(cb, "caption", "📝 <b>Caption Template</b>\n\nCurrent:\n<code>" + cur[:300] + "</code>\n\nSend new template:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_btn_label$") & filters.user(ADMINS))
async def cb_set_btn_label(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("button_label", "")
    txt = _prompt(cb, "btn_label", "🎛 <b>Button Label</b>\n\nCurrent: <code>" + cur + "</code>\n\nVariables: <code>{quality}</code> <code>{ep_range}</code>\n\nSend new label:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_btn_layout$") & filters.user(ADMINS))
async def cb_set_btn_layout(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("button_layout", "2,1")
    txt = _prompt(cb, "btn_layout", "⌨️ <b>Button Layout</b>\n\nCurrent: <code>" + cur + "</code>\n\nFormat: <code>2,1</code> or <code>3</code>\n\nSend new layout:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_watermark$") & filters.user(ADMINS))
async def cb_set_watermark(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("watermark", "") or "Not set"
    txt = _prompt(cb, "watermark", "🔖 <b>Watermark</b>\n\nCurrent: <code>" + cur + "</code>\n\nSend text (e.g. <code>@MyChannel</code>)\nSend <code>-</code> to remove:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_audio$") & filters.user(ADMINS))
async def cb_set_audio(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("audio_info", "")
    txt = _prompt(cb, "audio", "🔊 <b>Audio Info</b>\n\nCurrent: <code>" + cur + "</code>\n\nSend new audio info:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_subs$") & filters.user(ADMINS))
async def cb_set_subs(client: Client, cb: CallbackQuery):
    settings = await get_settings(cb.from_user.id)
    cur = settings.get("sub_info", "")
    txt = _prompt(cb, "subs", "📝 <b>Subtitle Info</b>\n\nCurrent: <code>" + cur + "</code>\n\nSend new subtitle info:")
    await pacing.edit(cb.message, txt, reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex("^set_sticker$") & filters.user(ADMINS))
async def cb_set_sticker(client: Client, cb: CallbackQuery):
    _prompt(cb, "sticker", "")
    await pacing.edit(cb.message, "🎴 <b>Sticker</b>\n\nSend a sticker to use between episodes:", reply_markup=close_button())
    await cb.answer()


# ── Sticker input ──────────────────────────────────────────────

@Client.on_message(filters.sticker & _admin_filter)
async def on_sticker_input(client: Client, message: Message):
    admin_id = message.from_user.id
    if _edit_state.get(admin_id) != "sticker":
        return
    _edit_state.pop(admin_id)
    await update_settings(admin_id, sticker_id=message.sticker.file_id)
    await log_settings_changed(client, admin_id, "Sticker", "updated")
    await message.delete()
    await _refresh_settings(client, admin_id)


# ── File store bots ────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_quality_bots$") & filters.user(ADMINS))
async def cb_quality_bots(client: Client, cb: CallbackQuery):
    _settings_msg[cb.from_user.id] = cb.message
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message,
        "🤖 <b>File Store Bots</b>\n\nFormat: <code>@BotUsername -100ChannelID</code>",
        reply_markup=quality_bots_menu(settings.get("quality_bots", {})))
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^set_qbot_") & filters.user(ADMINS))
async def cb_set_qbot(client: Client, cb: CallbackQuery):
    quality  = cb.data.replace("set_qbot_", "")
    settings = await get_settings(cb.from_user.id)
    current  = settings.get("quality_bots", {}).get(quality, {})
    cur_text = "@" + current.get("bot","?") + " " + str(current.get("channel","?")) if current else "Not set"
    _prompt(cb, "qbot_" + quality, "")
    await pacing.edit(cb.message,
        "🤖 <b>" + quality + " File Store Bot</b>\n\nCurrent: <code>" + cur_text + "</code>\n\nSend: <code>@BotUsername -100ChannelID</code>",
        reply_markup=close_button())
    await cb.answer()


# ── Channels ───────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^set_channels$") & filters.user(ADMINS))
async def cb_channels(client: Client, cb: CallbackQuery):
    _settings_msg[cb.from_user.id] = cb.message
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "📢 <b>Post Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])))
    await cb.answer()


@Client.on_callback_query(filters.regex("^add_channel$") & filters.user(ADMINS))
async def cb_add_channel(client: Client, cb: CallbackQuery):
    _prompt(cb, "channel", "")
    await pacing.edit(cb.message,
        "📢 <b>Add Channel</b>\n\nSend channel ID or @username:",
        reply_markup=close_button())
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^del_ch_") & filters.user(ADMINS))
async def cb_del_channel(client: Client, cb: CallbackQuery):
    ch_id = int(cb.data.split("_")[-1])
    await remove_channel(cb.from_user.id, ch_id)
    settings = await get_settings(cb.from_user.id)
    await pacing.edit(cb.message, "📢 <b>Post Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])))
    await cb.answer("Removed")


@Client.on_callback_query(filters.regex(r"^ch_qual_") & filters.user(ADMINS))
async def cb_channel_quality(client: Client, cb: CallbackQuery):
    ch_id    = int(cb.data.split("_")[-1])
    admin_id = cb.from_user.id
    settings = await get_settings(admin_id)
    ch = next((c for c in settings.get("channels",[]) if c["id"] == ch_id), None)
    if not ch:
        return await cb.answer("Not found", show_alert=True)
    selected = ch.get("qualities", ["480p","720p","1080p"])
    await pacing.edit(cb.message, "🎞 <b>Qualities for " + ch["name"] + "</b>",
        reply_markup=channel_quality_picker(ch_id, ch["name"], selected))
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^tq_") & filters.user(ADMINS))
async def cb_toggle_quality(client: Client, cb: CallbackQuery):
    parts    = cb.data.split("_")
    quality  = parts[1]
    ch_id    = int(parts[2])
    admin_id = cb.from_user.id
    settings = await get_settings(admin_id)
    ch = next((c for c in settings.get("channels",[]) if c["id"] == ch_id), None)
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
    await pacing.edit(cb.message, "📢 <b>Post Channels</b>",
        reply_markup=channel_manager(settings.get("channels", [])))
    await cb.answer("Saved ✅")


# ── Text input ─────────────────────────────────────────────────

@Client.on_message(filters.text & _admin_filter, group=2)
async def on_text_input(client: Client, message: Message):
    admin_id = message.from_user.id
    state    = _edit_state.get(admin_id)
    if not state:
        return

    text = message.text.strip()

    async def _save(msg_text: str, parse_mode=ParseMode.HTML):
        _edit_state.pop(admin_id, None)
        await message.delete()            # delete admin's text reply
        settings = await get_settings(admin_id)
        orig = _settings_msg.get(admin_id)
        if orig:
            try:
                await pacing.edit(orig,
                    "⚙️ <b>Settings</b>\n<i>" + msg_text.replace("<b>","").replace("</b>","").replace("<code>","").replace("</code>","") + "</i>",
                    reply_markup=settings_menu(settings))
                return
            except Exception:
                pass
        # fallback
        await pacing.send(client, message.chat.id,
            "⚙️ <b>Settings</b>",
            reply_markup=settings_menu(settings))

    if state == "caption":
        await update_settings(admin_id, caption_template=text)
        await log_settings_changed(client, admin_id, "Caption Template", "updated")
        await _save("Caption template saved")

    elif state == "btn_label":
        await update_settings(admin_id, button_label=text)
        await log_settings_changed(client, admin_id, "Button Label", text)
        await _save("Button label: " + text)

    elif state == "btn_layout":
        try:
            [int(x) for x in text.split(",")]
        except ValueError:
            return await pacing.reply(message, "❌ Invalid. Use e.g. <code>2,1</code>", parse_mode=ParseMode.HTML)
        await update_settings(admin_id, button_layout=text)
        await log_settings_changed(client, admin_id, "Button Layout", text)
        await _save("Layout: " + text)

    elif state == "watermark":
        val = "" if text == "-" else text
        await update_settings(admin_id, watermark=val)
        await log_settings_changed(client, admin_id, "Watermark", val or "removed")
        await _save("Watermark " + ("set: " + val if val else "removed"))

    elif state == "audio":
        await update_settings(admin_id, audio_info=text)
        await log_settings_changed(client, admin_id, "Audio Info", text)
        await _save("Audio: " + text)

    elif state == "subs":
        await update_settings(admin_id, sub_info=text)
        await log_settings_changed(client, admin_id, "Sub Info", text)
        await _save("Subs: " + text)

    elif state == "channel":
        try:
            chat = await client.get_chat(int(text) if text.lstrip("-").isdigit() else text)
        except Exception as e:
            return await pacing.reply(message,
                "❌ Channel not found: <code>" + str(e) + "</code>", parse_mode=ParseMode.HTML)
        _edit_state.pop(admin_id, None)
        await add_channel(admin_id, chat.id, chat.title)
        await message.delete()
        await log_settings_changed(client, admin_id, "Channel Added", chat.title)
        settings = await get_settings(admin_id)
        orig = _settings_msg.get(admin_id)
        if orig:
            try:
                await pacing.edit(orig, "📢 <b>Post Channels</b>",
                    reply_markup=channel_manager(settings.get("channels",[])))
                return
            except Exception:
                pass
        await pacing.send(client, message.chat.id, "📢 <b>Post Channels</b>",
            reply_markup=channel_manager(settings.get("channels",[])))

    elif state and state.startswith("qbot_"):
        quality = state.split("_", 1)[1]
        parts   = text.replace("@","").split()
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            return await pacing.reply(message,
                "❌ Format: <code>@BotUsername -100ChannelID</code>", parse_mode=ParseMode.HTML)
        from database.db import update_quality_bot
        await update_quality_bot(admin_id, quality, parts[0], int(parts[1]))
        await log_settings_changed(client, admin_id, quality + " Bot", "@" + parts[0])
        _edit_state.pop(admin_id, None)
        await message.delete()
        settings = await get_settings(admin_id)
        orig = _settings_msg.get(admin_id)
        if orig:
            try:
                await pacing.edit(orig,
                    "🤖 <b>File Store Bots</b>",
                    reply_markup=quality_bots_menu(settings.get("quality_bots",{})))
                return
            except Exception:
                pass
        await pacing.send(client, message.chat.id,
            "🤖 <b>File Store Bots</b>",
            reply_markup=quality_bots_menu(settings.get("quality_bots",{})))
