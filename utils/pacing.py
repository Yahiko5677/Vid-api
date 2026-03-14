"""
utils/pacing.py — Thin wrappers around Telegram API calls.

Adds automatic sleep + FloodWait retry after every call.

KEY FIX: All wrappers use lambda factories so each retry creates
a FRESH coroutine — avoids "cannot reuse already awaited coroutine".

Delays:
    SEND_PAUSE = 0.3s  — send / reply / photo / sticker
    EDIT_PAUSE = 0.2s  — edit_text / edit_reply_markup
    COPY_PAUSE = 2.0s  — copy_message
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode

logger = logging.getLogger(__name__)

SEND_PAUSE = 1.5
EDIT_PAUSE = 0.2
COPY_PAUSE = 1.0


async def _call(make_coro, pause: float):
    """
    Execute a Telegram API call with FloodWait retry + pacing sleep.

    IMPORTANT: accepts a FACTORY (lambda/callable), not a coroutine.
    This allows creating a fresh coroutine on each retry attempt.
    Passing a coroutine directly causes 'cannot reuse already awaited coroutine'.
    """
    for attempt in range(5):
        try:
            result = await make_coro()   # fresh coroutine each attempt
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
        lambda: client.send_message(
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
        lambda: message.reply(
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
        lambda: message.edit_text(
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
        lambda: message.edit_reply_markup(reply_markup=reply_markup),
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
        lambda: client.send_photo(
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
        lambda: client.send_sticker(chat_id=chat_id, sticker=sticker),
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
    return await _call(
        lambda: client.copy_message(
            chat_id              = chat_id,
            from_chat_id         = from_chat_id,
            message_id           = message_id,
            disable_notification = disable_notification,
        ),
        COPY_PAUSE,
    )
