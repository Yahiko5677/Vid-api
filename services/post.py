"""
Post sender service.

Simple Mode:
    Episode 01
    [file 480p forwarded]
    [file 720p forwarded]
    [file 1080p forwarded]
    [sticker]

Rich Mode — Option B (one season post, batch link per quality):
    [poster]
    🎬 Title (Year)
    🎭 Genre | ⭐ Score
    📊 Episodes | 🎙 Studio
    🔊 Audio | 📝 Subs

    [📥 480p E01-E13]
    [📥 720p E01-E13]
    [📥 1080p E01-E13]
"""

import asyncio
import logging
import io
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper_func import get_batch_link
from services.tmdb import download_poster
from config import FILE_STORE_CHANNEL

logger = logging.getLogger(__name__)

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p"]


def _sorted_qualities(qualities: dict) -> list:
    return sorted(
        qualities.items(),
        key=lambda x: QUALITY_ORDER.index(x[0]) if x[0] in QUALITY_ORDER else 99
    )


def _episodes_sorted(episodes: list) -> list:
    return sorted(episodes, key=lambda x: x["episode"])


# ─────────────────────────────────────────────────────────────
#  SIMPLE MODE — forward files per episode in sequence
# ─────────────────────────────────────────────────────────────

async def post_simple_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    sticker_id: str | None,
):
    for ep in _episodes_sorted(episodes):
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
                    chat_id             = channel_id,
                    from_chat_id        = FILE_STORE_CHANNEL,
                    message_id          = qdata["msg_id"],
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Failed to forward {quality} ep{episode}: {e}")

        # Sticker between every episode (last ep = end of season sticker too)
        if sticker_id:
            try:
                await client.send_sticker(channel_id, sticker_id)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"Sticker send failed: {e}")


# ─────────────────────────────────────────────────────────────
#  RICH MODE — one season post, batch link per quality
# ─────────────────────────────────────────────────────────────

async def _build_quality_batch_links(
    client: Client,
    episodes: list,
) -> dict[str, str]:
    """
    For each quality:
      1. Re-copy all episodes IN ORDER to FILE_STORE_CHANNEL
      2. Record first + last msg_id
      3. Generate batch link covering all episodes of that quality

    Returns { "480p": link, "720p": link, "1080p": link }
    """
    # Collect all available qualities across all episodes
    all_qualities: set[str] = set()
    for ep in episodes:
        all_qualities.update(ep.get("qualities", {}).keys())

    quality_links: dict[str, str] = {}

    for quality in sorted(all_qualities, key=lambda x: QUALITY_ORDER.index(x) if x in QUALITY_ORDER else 99):
        msg_ids = []

        # Copy episodes in order for this quality
        for ep in _episodes_sorted(episodes):
            qdata = ep.get("qualities", {}).get(quality)
            if not qdata:
                continue
            for attempt in range(5):
                try:
                    sent = await client.copy_message(
                        chat_id             = FILE_STORE_CHANNEL,
                        from_chat_id        = FILE_STORE_CHANNEL,
                        message_id          = qdata["msg_id"],
                        disable_notification= True,
                    )
                    msg_ids.append(sent.id)
                    await asyncio.sleep(0.1)
                    break
                except FloodWait as e:
                    wait = e.value + 2
                    logger.warning(f"FloodWait {wait}s on batch copy — waiting...")
                    await asyncio.sleep(wait)
                except Exception as e:
                    logger.error(f"Batch copy failed {quality} ep{ep['episode']}: {e}")
                    break

        if len(msg_ids) >= 2:
            link = await get_batch_link(msg_ids[0], msg_ids[-1])
        elif len(msg_ids) == 1:
            from helper_func import get_link
            link = await get_link(msg_ids[0])
        else:
            continue

        quality_links[quality] = link
        logger.info(f"✅ Batch link built for {quality}: {len(msg_ids)} ep(s)")

    return quality_links


async def post_rich_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    meta: dict | None,
    audio_info: str,
    sub_info: str,
):
    """One season post with batch link per quality."""
    if not episodes:
        return

    title  = episodes[0].get("title", "Unknown")
    season = episodes[0]["season"]
    ep_count = len(episodes)

    # Meta fields
    year       = (meta.get("year") or "")            if meta else ""
    genres     = " • ".join((meta.get("genres") or [])[:3]) if meta else ""
    overview   = (meta.get("synopsis") or meta.get("overview") or "") if meta else ""
    poster_url = meta.get("poster_url")               if meta else None
    score      = meta.get("score")                    if meta else None
    episodes_total = meta.get("episodes")             if meta else None
    studio     = meta.get("studio")                   if meta else None

    # ── Build batch links per quality ────────────────────────
    quality_links = await _build_quality_batch_links(client, episodes)

    # ── Caption ───────────────────────────────────────────────
    year_str  = f" ({year})" if year and year not in ("N/A", "") else ""
    ep_range  = f"E01-E{ep_count:02d}" if ep_count > 1 else "E01"
    season_str = f"Season {season}"

    caption  = f"🎬 <b>{title}{year_str}</b>\n"
    caption += f"📺 {season_str} · <code>{ep_range}</code>\n"
    if genres:
        caption += f"🎭 {genres}\n"
    if score and str(score) not in ("N/A", "None", ""):
        caption += f"⭐ MAL Score: <b>{score}</b>\n"
    if episodes_total and str(episodes_total) not in ("?", "None", ""):
        caption += f"📊 Total Episodes: <code>{episodes_total}</code>\n"
    if studio and studio not in ("N/A", "None", ""):
        caption += f"🎙 Studio: <code>{studio}</code>\n"
    caption += f"\n🔊 {audio_info}  |  📝 {sub_info}\n"
    if overview:
        caption += f"\n<i>{overview}</i>\n"

    # ── Quality buttons (one per quality, batch link) ─────────
    buttons = []
    for quality in sorted(quality_links.keys(), key=lambda x: QUALITY_ORDER.index(x) if x in QUALITY_ORDER else 99):
        link = quality_links[quality]
        buttons.append([InlineKeyboardButton(
            f"📥 {quality}  •  {ep_range}",
            url=link
        )])

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # ── Send with poster or text fallback ─────────────────────
    if poster_url:
        poster_bytes = await download_poster(poster_url)
        if poster_bytes:
            try:
                await client.send_photo(
                    chat_id    = channel_id,
                    photo      = io.BytesIO(poster_bytes),
                    caption    = caption,
                    reply_markup = markup,
                )
                return
            except Exception as e:
                logger.warning(f"Poster send failed, falling back to text: {e}")

    await client.send_message(
        chat_id    = channel_id,
        text       = caption,
        reply_markup = markup,
    )


# ─────────────────────────────────────────────────────────────
#  DISPATCHER
# ─────────────────────────────────────────────────────────────

async def dispatch_post(
    client: Client,
    channel_ids: list,
    episodes: list,
    settings: dict,
    meta: dict | None = None,
):
    mode       = settings.get("post_mode", "simple")
    sticker_id = settings.get("sticker_id")
    audio_info = settings.get("audio_info", "Hindi + English")
    sub_info   = settings.get("sub_info", "English")

    for ch_id in channel_ids:
        if mode == "simple":
            await post_simple_mode(client, ch_id, episodes, sticker_id)
        else:
            await post_rich_mode(client, ch_id, episodes, meta, audio_info, sub_info)
            # Fix #4 — sticker after season post in rich mode too
            if sticker_id:
                try:
                    await asyncio.sleep(0.5)
                    await client.send_sticker(ch_id, sticker_id)
                except Exception as e:
                    logger.warning(f"Sticker send failed: {e}")

        await asyncio.sleep(0.5)
