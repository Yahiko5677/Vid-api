"""
Log service — sends structured logs to a Telegram log channel.

Log channel is set per-admin via /settings or LOG_CHANNEL in .env (global fallback).

Log events:
    📥 FILE_RECEIVED   — admin uploaded a file
    ✅ FILE_CONFIRMED   — admin confirmed title/episode
    🚀 POST_TRIGGERED  — admin triggered post
    📢 POST_SUCCESS    — post delivered to channel(s)
    ❌ POST_FAILED     — post failed
    ⚙️ SETTINGS_CHANGED — admin changed a setting
    🔄 BOT_STARTED     — bot came online (restart recovery info)
"""

import logging
from datetime import datetime, timezone
from pyrogram import Client
from pyrogram.enums import ParseMode

logger = logging.getLogger(__name__)

# In-memory log buffer per admin (last 50 events)
# { admin_id: [ log_entry, ... ] }
_log_buffer: dict[int, list] = {}
MAX_BUFFER = 50


# ═══════════════════════════════════════════════════════
#  Core logger
# ═══════════════════════════════════════════════════════

async def log_event(
    client: Client,
    admin_id: int,
    event: str,
    details: str = "",
    log_channel_id: int | None = None,
):
    """
    Log an event to:
      1. In-memory buffer (always)
      2. Log channel (if configured)
    """
    now     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry   = {"time": now, "event": event, "details": details}

    # ── 1. Memory buffer ─────────────────────────────────
    buf = _log_buffer.setdefault(admin_id, [])
    buf.append(entry)
    if len(buf) > MAX_BUFFER:
        buf.pop(0)

    # ── 2. Log channel ───────────────────────────────────
    if not log_channel_id:
        from config import LOG_CHANNEL
        log_channel_id = LOG_CHANNEL

    if log_channel_id:
        text = _format_log(admin_id, event, details, now)
        try:
            await client.send_message(
                chat_id    = log_channel_id,
                text       = text,
                parse_mode = ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Log channel send failed: {e}")


def _format_log(admin_id: int, event: str, details: str, time: str) -> str:
    lines = [
        f"<b>{event}</b>",
        f"👤 Admin: <code>{admin_id}</code>",
        f"🕐 {time}",
    ]
    if details:
        lines.append(f"📝 {details}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
#  Shorthand helpers
# ═══════════════════════════════════════════════════════

async def log_file_received(client, admin_id, title, quality, ep_str, ch_id=None):
    await log_event(
        client, admin_id,
        "📥 FILE RECEIVED",
        f"<b>{title}</b> · {ep_str} · <code>{quality}</code>",
        ch_id,
    )

async def log_file_confirmed(client, admin_id, title, quality, ep_str, ch_id=None):
    await log_event(
        client, admin_id,
        "✅ FILE CONFIRMED",
        f"<b>{title}</b> · {ep_str} · <code>{quality}</code>",
        ch_id,
    )

async def log_post_triggered(client, admin_id, title, season, ep_count, channels, ch_id=None):
    ch_names = ", ".join(channels)
    await log_event(
        client, admin_id,
        "🚀 POST TRIGGERED",
        f"<b>{title}</b> S{season:02d} · {ep_count} ep(s) → {ch_names}",
        ch_id,
    )

async def log_post_success(client, admin_id, title, season, ep_count, channels, mode, ch_id=None):
    ch_names = ", ".join(channels)
    await log_event(
        client, admin_id,
        "📢 POST SUCCESS",
        f"<b>{title}</b> S{season:02d} · {ep_count} ep(s) → {ch_names} [{mode.upper()} mode]",
        ch_id,
    )

async def log_post_failed(client, admin_id, title, error, ch_id=None):
    await log_event(
        client, admin_id,
        "❌ POST FAILED",
        f"<b>{title}</b> — <code>{error}</code>",
        ch_id,
    )

async def log_settings_changed(client, admin_id, what, value, ch_id=None):
    await log_event(
        client, admin_id,
        "⚙️ SETTINGS CHANGED",
        f"{what} → <code>{value}</code>",
        ch_id,
    )

async def log_bot_started(client, admin_id, recovered: int, ch_id=None):
    await log_event(
        client, admin_id,
        "🔄 BOT STARTED",
        f"Recovered <b>{recovered}</b> pending episode(s) from DB",
        ch_id,
    )


# ═══════════════════════════════════════════════════════
#  /log command — show buffer to admin in PM
# ═══════════════════════════════════════════════════════

async def send_log_summary(client: Client, message, admin_id: int):
    buf = _log_buffer.get(admin_id, [])

    if not buf:
        return await message.reply("📋 No log entries yet.")

    lines = [f"<b>📋 Last {len(buf)} Events</b>\n"]
    for entry in reversed(buf):   # most recent first
        lines.append(
            f"<b>{entry['event']}</b>\n"
            f"  🕐 {entry['time']}\n"
            f"  📝 {entry['details']}\n" if entry['details'] else
            f"<b>{entry['event']}</b>\n"
            f"  🕐 {entry['time']}\n"
        )

    text = "\n".join(lines)

    # Telegram max 4096 chars — split if needed
    if len(text) <= 4096:
        await message.reply(text, parse_mode=ParseMode.HTML)
    else:
        # Send last 20 only
        lines_short = [f"<b>📋 Last 20 Events</b>\n"]
        for entry in list(reversed(buf))[:20]:
            lines_short.append(
                f"<b>{entry['event']}</b>\n"
                f"  🕐 {entry['time']}\n"
                + (f"  📝 {entry['details']}\n" if entry['details'] else "")
            )
        await message.reply("\n".join(lines_short), parse_mode=ParseMode.HTML)
