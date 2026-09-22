"""
handlers/scraper_handler.py

Telegram Bot handler for Toonworld4all & GDFlix URL scraping and shortener bypasses.
Commands:
  /scrape <url> — Scrapes episode or redirect link to resolve GDFlix direct downloads.
Auto-detection:
  Automatically intercepts toonworld4all.me / gdflix links sent in chat by admins.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from config import ADMINS
from services.scraper import process_toonworld_url

logger = logging.getLogger(__name__)
_admin_filter = filters.user(ADMINS)


async def handle_scrape_url(client: Client, message: Message, url: str):
    """Core logic to process URL and send formatted response."""
    status_msg = await message.reply(
        "🔎 <b>Processing URL...</b>\n"
        "• Extracting Toonworld4all metadata & encodes\n"
        "• Bypassing shortener gateways (exeygo / cutty / gplinks)\n"
        "• Resolving GDFlix direct download links...",
        parse_mode=ParseMode.HTML,
        quote=True
    )

    try:
        res = await process_toonworld_url(url)

        if res.get("status") == "error":
            return await status_msg.edit_text(
                f"❌ <b>Scraping Failed</b>\n\n<code>{res.get('error')}</code>",
                parse_mode=ParseMode.HTML
            )

        encodes   = res.get("encodes", [])
        gd_link   = res.get("gdflix_link", "")
        gd_info   = res.get("gdflix_info", {})
        title     = gd_info.get("title") or "Toonworld4all Episode"

        lines = [f"🎬 <b>{title}</b>\n"]

        buttons = []

        if encodes:
            lines.append("🎞 <b>Available Qualities & Hosts:</b>\n")
            for enc in encodes:
                q_label = enc.get("quality", "Unknown")
                q_size  = enc.get("size", "")
                size_str = f" ({q_size})" if q_size else ""
                lines.append(f"<b>• {q_label}{size_str}:</b>")
                for f in enc.get("files", []):
                    host  = f.get("host", "Host")
                    link  = f.get("link", "")
                    short = f.get("short", "")
                    lines.append(f"  └ <b>{host}</b> ({short}): <a href='{link}'>Redirect Link</a>")

        if gd_link:
            lines.append(f"\n🚀 <b>GDFlix Resolved Link:</b>\n<code>{gd_link}</code>")
            buttons.append([InlineKeyboardButton("🔗 Open GDFlix Page", url=gd_link)])

        dl_links = gd_info.get("download_links", [])
        if dl_links:
            lines.append("\n📥 <b>Direct Download Links:</b>")
            for idx, item in enumerate(dl_links, 1):
                lines.append(f"  {idx}. <a href='{item['url']}'>{item['label']}</a>")

        buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])

        await status_msg.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Error handling scrape URL: {e}")
        await status_msg.edit_text(
            f"❌ <b>An error occurred:</b>\n<code>{e}</code>",
            parse_mode=ParseMode.HTML
        )


async def cmd_scrape(client: Client, message: Message):
    """Command: /scrape <url>"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚠️ <b>Usage:</b> <code>/scrape <toonworld4all_or_redirect_url></code>", parse_mode=ParseMode.HTML)

    url = parts[1].strip()
    await handle_scrape_url(client, message, url)


async def on_auto_detect_url(client: Client, message: Message):
    """Auto-detect toonworld4all / gdflix / redirect URLs sent in chat."""
    text = message.text or ""
    if any(k in text for k in ["toonworld4all.me", "/redirect/", "gdflix"]):
        words = text.split()
        for w in words:
            if w.startswith("http://") or w.startswith("https://"):
                await handle_scrape_url(client, message, w.strip())
                break


def register(app: Client):
    from pyrogram.handlers import MessageHandler

    app.add_handler(MessageHandler(cmd_scrape, filters.command("scrape") & filters.private & _admin_filter))
    app.add_handler(MessageHandler(on_auto_detect_url, filters.private & _admin_filter & filters.text & ~filters.command(["start", "settings", "pending", "log", "stats", "cancel", "scrape"])), group=10)
