"""
Post sender service.

Simple Mode:
    Episode 01
    [file 480p]
    [file 720p]
    [file 1080p]
    [sticker]   ← between eps + end of season

Rich Mode (uses unified meta from Jikan or TMDB):
    [poster image]
    🎬 Title (Year)
    🎭 Genre
    ⭐ MAL Score
    📊 Episodes
    🎙 Studio
    🔊 Audio | 📝 Subs
    ───────────────────
    [📥 480p]  [📥 720p]  [📥 1080p]
"""

import asyncio
import logging
import io
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper_func import get_link
from services.tmdb import download_poster

logger = logging.getLogger(__name__)

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p"]


def _sorted_qualities(qualities: dict) -> list:
    return sorted(
        qualities.items(),
        key=lambda x: QUALITY_ORDER.index(x[0]) if x[0] in QUALITY_ORDER else 99
    )


# ─────────────────────────────────────────────────────────────
#  SIMPLE MODE
# ─────────────────────────────────────────────────────────────

async def post_simple_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    sticker_id: str | None,
):
    for i, ep in enumerate(episodes):
        season   = ep["season"]
        episode  = ep["episode"]
        qualities = ep.get("qualities", {})

        label = f"Episode {episode:02d}"
        if season > 1:
            label = f"Season {season} • Episode {episode:02d}"

        await client.send_message(channel_id, f"**{label}**")
        await asyncio.sleep(0.5)

        for quality, qdata in _sorted_qualities(qualities):
            try:
                await client.copy_message(
                    chat_id=channel_id,
                    from_chat_id=client.db_channel_id,
                    message_id=qdata["msg_id"],
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Failed to forward {quality} ep{episode}: {e}")

        # Sticker between every episode (including after last = end-of-season)
        if sticker_id:
            try:
                await client.send_sticker(channel_id, sticker_id)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"Sticker send failed: {e}")


# ─────────────────────────────────────────────────────────────
#  RICH MODE
# ─────────────────────────────────────────────────────────────

async def post_rich_mode(
    client: Client,
    channel_id: int,
    episode: dict,
    meta: dict | None,          # unified meta from metadata.py
    audio_info: str,
    sub_info: str,
):
    title     = episode.get("title", "Unknown")
    season    = episode["season"]
    ep_num    = episode["episode"]
    qualities = episode.get("qualities", {})

    # Unified meta fields (works for both Jikan and TMDB)
    year       = (meta.get("year") or "")       if meta else ""
    genres     = " • ".join((meta.get("genres") or [])[:3]) if meta else ""
    overview   = (meta.get("synopsis") or meta.get("overview") or "") if meta else ""
    poster_url = meta.get("poster_url")         if meta else None
    score      = meta.get("score")              if meta else None
    episodes   = meta.get("episodes")           if meta else None
    studio     = meta.get("studio")             if meta else None

    ep_label = f"S{season:02d}E{ep_num:02d}"

    # ── Caption ──────────────────────────────────────────────
    year_str = f" ({year})" if year and year not in ("N/A", "") else ""
    caption  = f"🎬 **{title}{year_str}**\n"
    caption += f"📺 `{ep_label}`\n"

    if genres:
        caption += f"🎭 {genres}\n"
    if score and str(score) not in ("N/A", "None", ""):
        caption += f"⭐ MAL Score: **{score}**\n"
    if episodes and str(episodes) not in ("?", "None", ""):
        caption += f"📊 Total Episodes: `{episodes}`\n"
    if studio and studio not in ("N/A", "None", ""):
        caption += f"🎙 Studio: `{studio}`\n"

    caption += f"\n🔊 {audio_info}  |  📝 {sub_info}\n"

    if overview:
        caption += f"\n_{overview}_\n"

    # ── Quality buttons ───────────────────────────────────────
    buttons = []
    row     = []
    for quality, qdata in _sorted_qualities(qualities):
        link = await get_link(qdata["msg_id"])
        row.append(InlineKeyboardButton(f"📥 {quality}", url=link))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # ── Send with poster or text fallback ─────────────────────
    if poster_url:
        poster_bytes = await download_poster(poster_url)
        if poster_bytes:
            try:
                await client.send_photo(
                    chat_id=channel_id,
                    photo=io.BytesIO(poster_bytes),
                    caption=caption,
                    reply_markup=markup,
                )
                return
            except Exception as e:
                logger.warning(f"Poster send failed, falling back to text: {e}")

    await client.send_message(
        chat_id=channel_id,
        text=caption,
        reply_markup=markup,
    )


# ─────────────────────────────────────────────────────────────
#  DISPATCHER
# ─────────────────────────────────────────────────────────────

async def dispatch_post(
    client: Client,
    channel_ids: list,
    episodes: list,
    settings: dict,
    meta: dict | None = None,   # unified meta (replaces old tmdb_meta)
):
    mode       = settings.get("post_mode", "simple")
    sticker_id = settings.get("sticker_id")
    audio_info = settings.get("audio_info", "Hindi + English")
    sub_info   = settings.get("sub_info", "English")

    for ch_id in channel_ids:
        if mode == "simple":
            await post_simple_mode(client, ch_id, episodes, sticker_id)
        else:
            for ep in episodes:
                await post_rich_mode(client, ch_id, ep, meta, audio_info, sub_info)
                await asyncio.sleep(0.5)
            # End-of-season sticker after all episodes
            if sticker_id:
                try:
                    await client.send_sticker(ch_id, sticker_id)
                except Exception:
                    pass
