"""
Post sender service.

Simple Mode — forward files per episode in sequence + sticker between/end
Rich Mode   — one season post with:
  • Custom caption template
  • Per-quality batch links (each quality → its own File Store Bot)
  • Custom button label + layout
  • Sticker at end of season
  • Only sends qualities assigned to each channel
"""

import asyncio
import logging
import io
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper_func import encode
from services.tmdb import download_poster
from utils import pacing
from config import DEFAULT_CAPTION_TEMPLATE, DEFAULT_BUTTON_LABEL, DEFAULT_BUTTON_LAYOUT

logger = logging.getLogger(__name__)

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p"]


def _sorted_qualities(qualities: dict) -> list:
    return sorted(
        qualities.items(),
        key=lambda x: QUALITY_ORDER.index(x[0]) if x[0] in QUALITY_ORDER else 99
    )


def _episodes_sorted(episodes: list) -> list:
    return sorted(episodes, key=lambda x: x["episode"])


def _get_bot_and_channel(quality: str, quality_bots: dict) -> tuple[str, int]:
    """
    Get File Store Bot username + DB channel for a quality.
    Configured entirely from /settings → stored in quality_bots dict in MongoDB.
    """
    qb = quality_bots.get(quality, {})
    return qb.get("bot", ""), qb.get("channel", 0)


async def _get_link(msg_id: int, bot_username: str, channel_id: int) -> str:
    string = f"get-{msg_id * abs(channel_id)}"
    b64    = await encode(string)
    return f"https://t.me/{bot_username}?start={b64}"


async def _get_batch_link(start_id: int, end_id: int, bot_username: str, channel_id: int) -> str:
    string = f"get-{start_id * abs(channel_id)}-{end_id * abs(channel_id)}"
    b64    = await encode(string)
    return f"https://t.me/{bot_username}?start={b64}"


def _render_caption(
    template: str, meta: dict | None, ep_range: str,
    season: int, audio_info: str, sub_info: str,
) -> str:
    year     = (meta.get("year")     or "N/A")              if meta else "N/A"
    genres   = " • ".join((meta.get("genres") or [])[:3])   if meta else ""
    score    = str(meta.get("score") or "N/A")              if meta else "N/A"
    episodes = str(meta.get("episodes") or "?")             if meta else "?"
    studio   = (meta.get("studio")   or "N/A")              if meta else "N/A"
    synopsis = (meta.get("synopsis") or meta.get("overview") or "") if meta else ""
    title    = (meta.get("title")    or "")                 if meta else ""

    return template.format(
        title    = title,
        year     = year,
        genres   = genres,
        score    = score,
        episodes = episodes,
        studio   = studio,
        synopsis = synopsis,
        season   = f"Season {season}",
        ep_range = ep_range,
        audio    = audio_info,
        subs     = sub_info,
    )


# ─────────────────────────────────────────────────────────────
#  SIMPLE MODE
# ─────────────────────────────────────────────────────────────

async def post_simple_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    sticker_id: str | None,
    ch_qualities: list,
    quality_bots: dict,
):
    for ep in _episodes_sorted(episodes):
        season    = ep["season"]
        episode   = ep["episode"]
        qualities = ep.get("qualities", {})

        label = f"Episode {episode:02d}"
        if season > 1:
            label = f"Season {season} \u2022 Episode {episode:02d}"

        await pacing.send(client, channel_id, f"**{label}**")

        for quality, qdata in _sorted_qualities(qualities):
            if quality not in ch_qualities:
                continue

            # Source = quality's DB channel, Destination = post channel
            bot_name, db_ch = _get_bot_and_channel(quality, quality_bots)
            if not db_ch:
                logger.warning(f"No DB channel for {quality} — set via /settings")
                continue

            try:
                await pacing.copy_message(
                    client,
                    chat_id              = channel_id,
                    from_chat_id         = db_ch,
                    message_id           = qdata["msg_id"],
                    disable_notification = True,
                )
            except Exception as ex:
                logger.error(f"Simple forward {quality} ep{episode}: {ex}")

        if sticker_id:
            try:
                await pacing.send_sticker(client, channel_id, sticker_id)
            except Exception as e:
                logger.warning(f"Sticker failed: {e}")


# ─────────────────────────────────────────────────────────────
#  RICH MODE — batch links per quality, custom caption/buttons
# ─────────────────────────────────────────────────────────────

async def _build_quality_batch_links(
    client: Client,
    episodes: list,
    ch_qualities: list,
    quality_bots: dict,
    sticker_id: str | None = None,
    notify_chat_id: int | None = None,   # admin chat to notify on sticker errors
) -> dict[str, str]:
    """
    For each quality assigned to this channel:
      1. Re-copy all episodes in order to that quality's DB channel
      2. Send sticker to DB channel after all episodes (appears at end of delivery)
      3. Get first + last msg_id → batch link pointing to correct File Store Bot
    """
    quality_links: dict[str, str] = {}

    for quality in [q for q in QUALITY_ORDER if q in ch_qualities]:
        bot_name, db_ch = _get_bot_and_channel(quality, quality_bots)
        if not bot_name or not db_ch:
            logger.warning(f"No File Store Bot for {quality} — skipping. Set via /settings → 🤖 File Store Bots")
            continue

        msg_ids = []
        for ep in _episodes_sorted(episodes):
            qdata = ep.get("qualities", {}).get(quality)
            if not qdata:
                continue
            try:
                # Fix #3 + #4 — pacing handles FloodWait + 0.1s sleep already
                sent = await pacing.copy_message(
                    client,
                    chat_id              = db_ch,
                    from_chat_id         = db_ch,
                    message_id           = qdata["msg_id"],
                    disable_notification = True,
                )
                msg_ids.append(sent.id)
            except Exception as ex:
                logger.error(f"Batch copy {quality} ep{ep['episode']}: {ex}")

        if len(msg_ids) >= 2:
            link = await _get_batch_link(msg_ids[0], msg_ids[-1], bot_name, db_ch)
        elif len(msg_ids) == 1:
            link = await _get_link(msg_ids[0], bot_name, db_ch)
        else:
            continue

        quality_links[quality] = link
        logger.info(f"✅ {quality} batch link: {len(msg_ids)} ep(s) → @{bot_name}")

        # Send sticker to DB channel after all episodes of this quality
        # So when File Store Bot delivers the batch, sticker appears at the end
        if sticker_id:
            try:
                await pacing.send_sticker(client, db_ch, sticker_id)
                logger.info(f"🎴 Sticker sent to DB channel for {quality}")
            except Exception as e:
                logger.warning(f"Sticker to DB channel failed for {quality}: {e}")
                # Surface error — bot may not have send permission in DB channel
                if notify_chat_id:
                    try:
                        await pacing.send(client, notify_chat_id,
                            f"⚠️ Sticker failed for <code>{quality}</code> DB channel\n"
                            f"Make sure bot is admin in that channel.\n<code>{e}</code>"
                        )
                    except Exception:
                        pass

    return quality_links


async def post_rich_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    meta: dict | None,
    settings: dict,
    ch_qualities: list,
):
    if not episodes:
        return

    season     = episodes[0]["season"]
    ep_count   = len(episodes)
    ep_range   = f"E01-E{ep_count:02d}" if ep_count > 1 else "E01"
    audio      = settings.get("audio_info", "Hindi + English")
    subs       = settings.get("sub_info", "English")
    template   = settings.get("caption_template", DEFAULT_CAPTION_TEMPLATE)
    btn_label  = settings.get("button_label", DEFAULT_BUTTON_LABEL)
    layout     = settings.get("button_layout", DEFAULT_BUTTON_LAYOUT)
    q_bots     = settings.get("quality_bots", {})
    sticker    = settings.get("sticker_id")
    poster_url = meta.get("poster_url") if meta else None

    # Caption
    try:
        caption = _render_caption(template, meta, ep_range, season, audio, subs)
    except KeyError as e:
        caption = f"❌ Caption template error — unknown variable {e}"
        logger.error(f"Caption render error: {e}")

    # Batch links
    quality_links = await _build_quality_batch_links(client, episodes, ch_qualities, q_bots, sticker, notify_chat_id=channel_id)

    # Buttons
    from keyboards import quality_buttons
    markup = quality_buttons(quality_links, btn_label, layout, ep_range)

    # Send with poster or text fallback
    sent = False
    if poster_url:
        poster_bytes = await download_poster(poster_url)
        if poster_bytes:
            try:
                await pacing.send_photo(
                    client,
                    chat_id      = channel_id,
                    photo        = io.BytesIO(poster_bytes),
                    caption      = caption,
                    reply_markup = markup,
                )
                sent = True
            except Exception as e:
                logger.warning(f"Poster send failed, falling back to text: {e}")

    if not sent:
        await pacing.send(
            client,
            chat_id      = channel_id,
            text         = caption,
            reply_markup = markup,
        )

    # Fix #1 — correct indentation for sticker block
    if sticker:
        try:
            await pacing.send_sticker(client, channel_id, sticker)
        except Exception as e:
            logger.warning(f"End sticker failed: {e}")


# ─────────────────────────────────────────────────────────────
#  DISPATCHER
# ─────────────────────────────────────────────────────────────

async def dispatch_post(
    client: Client,
    channel_ids: list[int],
    episodes: list,
    settings: dict,
    meta: dict | None = None,
):
    mode         = settings.get("post_mode", "simple")
    sticker_id   = settings.get("sticker_id")
    quality_bots = settings.get("quality_bots", {})
    all_channels = settings.get("channels", [])

    for ch_id in channel_ids:
        ch_cfg       = next((c for c in all_channels if c["id"] == ch_id), {})
        ch_qualities = ch_cfg.get("qualities", ["480p", "720p", "1080p"])

        if mode == "simple":
            # Fix #2 — pass quality_bots into simple mode
            await post_simple_mode(client, ch_id, episodes, sticker_id, ch_qualities, quality_bots)
        else:
            await post_rich_mode(client, ch_id, episodes, meta, settings, ch_qualities)

        await asyncio.sleep(0.3)
