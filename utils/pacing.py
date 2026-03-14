"""
utils/pacing.py — Thin wrappers around Telegram API calls.

Adds automatic sleep after every call to avoid FloodWait and keep the bot safe.

Delays:
    SEND_PAUSE   = 0.3s  — after send_message / reply / send_photo / send_sticker
    EDIT_PAUSE   = 0.2s  — after edit_text / edit_reply_markup (lighter)
    COPY_PAUSE   = 0.1s  — after copy_message (bulk ops use this)

Usage:
    from utils.pacing import send, reply, edit, edit_markup, send_photo, send_sticker

    await send(client, chat_id, "Hello")
    await reply(message, "Got it!")
    await edit(cb.message, "Updated!")
    await edit_markup(cb.message, keyboard)
    await send_photo(client, chat_id, photo=bytes, caption="...")
    await send_sticker(client, chat_id, sticker_id)
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode

logger = logging.getLogger(__name__)

SEND_PAUSE  = 0.3   # send / reply / photo / sticker
EDIT_PAUSE  = 0.2   # edit_text / edit_reply_markup
COPY_PAUSE  = 0.1   # copy_message (set directly in upload/post)


async def _call(coro, pause: float):
    """Execute a Telegram API coroutine with FloodWait retry + pacing sleep."""
    for attempt in range(5):
        try:
            result = await coro
            await asyncio.sleep(pause)
            return result
        except FloodWait as e:
            wait = e.value + 2
            logger.warning(f"FloodWait {wait}s — waiting...")
            await asyncio.sleep(wait)
        except Exception as e:
            raise e
    raise RuntimeError("Failed after 5 FloodWait retries")


# ── Wrappers ─────────────────────────────────────────────────────────────

async def send(
    client: Client,
    chat_id: int,
    text: str,
    reply_markup=None,
    parse_mode=ParseMode.HTML,
    disable_web_page_preview: bool = True,
):
    return await _call(
        client.send_message(
            chat_id                  = chat_id,
            text                     = text,
            reply_markup             = reply_markup,
            parse_mode               = parse_mode,
            disable_web_page_preview = disable_web_page_preview,
        ),
        SEND_PAUSE,
    )


async def reply(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode=ParseMode.HTML,
    quote: bool = True,
):
    return await _call(
        message.reply(
            text         = text,
            reply_markup = reply_markup,
            parse_mode   = parse_mode,
            quote        = quote,
        ),
        SEND_PAUSE,
    )


async def edit(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode=ParseMode.HTML,
):
    return await _call(
        message.edit_text(
            text         = text,
            reply_markup = reply_markup,
            parse_mode   = parse_mode,
        ),
        EDIT_PAUSE,
    )


async def edit_markup(
    message: Message,
    reply_markup: InlineKeyboardMarkup,
):
    return await _call(
        message.edit_reply_markup(reply_markup=reply_markup),
        EDIT_PAUSE,
    )


async def send_photo(
    client: Client,
    chat_id: int,
    photo,
    caption: str = "",
    reply_markup=None,
    parse_mode=ParseMode.HTML,
):
    return await _call(
        client.send_photo(
            chat_id      = chat_id,
            photo        = photo,
            caption      = caption,
            reply_markup = reply_markup,
            parse_mode   = parse_mode,
        ),
        SEND_PAUSE,
    )


async def send_sticker(
    client: Client,
    chat_id: int,
    sticker: str,
):
    return await _call(
        client.send_sticker(chat_id=chat_id, sticker=sticker),
        SEND_PAUSE,
    )


async def copy_message(
    client: Client,
    chat_id: int,
    from_chat_id: int,
    message_id: int,
    disable_notification: bool = True,
):
    """copy_message with FloodWait retry + 0.1s pacing."""
    for attempt in range(5):
        try:
            result = await client.copy_message(
                chat_id              = chat_id,
                from_chat_id         = from_chat_id,
                message_id           = message_id,
                disable_notification = disable_notification,
            )
            await asyncio.sleep(COPY_PAUSE)
            return result
        except FloodWait as e:
            wait = e.value + 2
            logger.warning(f"FloodWait {wait}s on copy_message — waiting...")
            await asyncio.sleep(wait)
        except Exception as e:
            raise e
    raise RuntimeError("copy_message failed after 5 retries")
