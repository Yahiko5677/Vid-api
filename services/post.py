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
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper_func import encode
from services.tmdb import download_poster
from config import FILE_STORE_MAP, DEFAULT_CAPTION_TEMPLATE, DEFAULT_BUTTON_LABEL, DEFAULT_BUTTON_LAYOUT

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
    Priority: admin's per-quality override → global config.py fallback
    """
    override = quality_bots.get(quality, {})
    if override.get("bot") and override.get("channel"):
        return override["bot"], override["channel"]
    fallback = FILE_STORE_MAP.get(quality, ("", 0))
    return fallback[0], fallback[1]


async def _get_link(msg_id: int, bot_username: str, channel_id: int) -> str:
    string = f"get-{msg_id * abs(channel_id)}"
    b64    = await encode(string)
    return f"https://t.me/{bot_username}?start={b64}"


async def _get_batch_link(start_id: int, end_id: int, bot_username: str, channel_id: int) -> str:
    string = f"get-{start_id * abs(channel_id)}-{end_id * abs(channel_id)}"
    b64    = await encode(string)
    return f"https://t.me/{bot_username}?start={b64}"


def _render_caption(template: str, meta: dict | None, ep_range: str, season: int,
                    audio_info: str, sub_info: str) -> str:
    year       = (meta.get("year") or "N/A")               if meta else "N/A"
    genres     = " • ".join((meta.get("genres") or [])[:3]) if meta else ""
    score      = str(meta.get("score") or "N/A")            if meta else "N/A"
    episodes   = str(meta.get("episodes") or "?")           if meta else "?"
    studio     = (meta.get("studio") or "N/A")              if meta else "N/A"
    synopsis   = (meta.get("synopsis") or meta.get("overview") or "") if meta else ""
    title      = (meta.get("title") or "")                  if meta else ""

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
    ch_qualities: list,          # qualities assigned to this channel
):
    for i, ep in enumerate(_episodes_sorted(episodes)):
        season    = ep["season"]
        episode   = ep["episode"]
        qualities = ep.get("qualities", {})

        label = f"Episode {episode:02d}"
        if season > 1:
            label = f"Season {season} • Episode {episode:02d}"

        await client.send_message(channel_id, f"**{label}**")
        await asyncio.sleep(0.3)

        for quality, qdata in _sorted_qualities(qualities):
            if quality not in ch_qualities:
                continue
            bot_name, db_ch = _get_bot_and_channel(quality, {})
            for attempt in range(5):
                try:
                    await client.copy_message(
                        chat_id             = channel_id,
                        from_chat_id        = db_ch,
                        message_id          = qdata["msg_id"],
                    )
                    await asyncio.sleep(0.1)
                    break
                except FloodWait as e:
                    await asyncio.sleep(e.value + 2)
                except Exception as ex:
                    logger.error(f"Simple forward failed {quality} ep{episode}: {ex}")
                    break

        # Sticker between episodes (last = end-of-season sticker)
        if sticker_id:
            try:
                await client.send_sticker(channel_id, sticker_id)
                await asyncio.sleep(0.1)
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
) -> dict[str, str]:
    """
    For each quality assigned to this channel:
      1. Re-copy all episodes in order to that quality's DB channel
      2. Get first + last msg_id → batch link pointing to correct File Store Bot
    """
    quality_links: dict[str, str] = {}

    for quality in [q for q in QUALITY_ORDER if q in ch_qualities]:
        bot_name, db_ch = _get_bot_and_channel(quality, quality_bots)
        if not bot_name or not db_ch:
            logger.warning(f"No File Store Bot configured for {quality} — skipping")
            continue

        msg_ids = []
        for ep in _episodes_sorted(episodes):
            qdata = ep.get("qualities", {}).get(quality)
            if not qdata:
                continue
            for attempt in range(5):
                try:
                    sent = await client.copy_message(
                        chat_id             = db_ch,
                        from_chat_id        = db_ch,
                        message_id          = qdata["msg_id"],
                        disable_notification= True,
                    )
                    msg_ids.append(sent.id)
                    await asyncio.sleep(0.1)
                    break
                except FloodWait as e:
                    logger.warning(f"FloodWait {e.value+2}s on batch copy...")
                    await asyncio.sleep(e.value + 2)
                except Exception as ex:
                    logger.error(f"Batch copy {quality} ep{ep['episode']}: {ex}")
                    break

        if len(msg_ids) >= 2:
            link = await _get_batch_link(msg_ids[0], msg_ids[-1], bot_name, db_ch)
        elif len(msg_ids) == 1:
            link = await _get_link(msg_ids[0], bot_name, db_ch)
        else:
            continue

        quality_links[quality] = link
        logger.info(f"✅ {quality} batch link: {len(msg_ids)} ep(s) → @{bot_name}")

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

    season    = episodes[0]["season"]
    ep_count  = len(episodes)
    ep_range  = f"E01-E{ep_count:02d}" if ep_count > 1 else "E01"
    audio     = settings.get("audio_info", "Hindi + English")
    subs      = settings.get("sub_info", "English")
    template  = settings.get("caption_template", DEFAULT_CAPTION_TEMPLATE)
    btn_label = settings.get("button_label", DEFAULT_BUTTON_LABEL)
    layout    = settings.get("button_layout", DEFAULT_BUTTON_LAYOUT)
    q_bots    = settings.get("quality_bots", {})
    sticker   = settings.get("sticker_id")
    poster_url = meta.get("poster_url") if meta else None

    # Build caption
    try:
        caption = _render_caption(template, meta, ep_range, season, audio, subs)
    except KeyError as e:
        caption = f"❌ Caption template error — unknown variable {e}"
        logger.error(f"Caption render error: {e}")

    # Build batch links
    quality_links = await _build_quality_batch_links(client, episodes, ch_qualities, q_bots)

    # Build buttons via keyboard builder
    from keyboards import quality_buttons
    markup = quality_buttons(quality_links, btn_label, layout, ep_range)

    # Send with poster or text fallback
    sent = False
    if poster_url:
        poster_bytes = await download_poster(poster_url)
        if poster_bytes:
            try:
                await client.send_photo(
                    chat_id      = channel_id,
                    photo        = io.BytesIO(poster_bytes),
                    caption      = caption,
                    reply_markup = markup,
                )
                sent = True
            except Exception as e:
                logger.warning(f"Poster send failed: {e}")

    if not sent:
        await client.send_message(
            chat_id      = channel_id,
            text         = caption,
            reply_markup = markup,
        )

    # Sticker at end of season
    if sticker:
        await asyncio.sleep(0.5)
        try:
            await client.send_sticker(channel_id, sticker)
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
    mode       = settings.get("post_mode", "simple")
    sticker_id = settings.get("sticker_id")
    all_channels = settings.get("channels", [])

    for ch_id in channel_ids:
        # Get quality assignment for this specific channel
        ch_cfg       = next((c for c in all_channels if c["id"] == ch_id), {})
        ch_qualities = ch_cfg.get("qualities", ["480p","720p","1080p"])

        if mode == "simple":
            await post_simple_mode(client, ch_id, episodes, sticker_id, ch_qualities)
        else:
            await post_rich_mode(client, ch_id, episodes, meta, settings, ch_qualities)

        await asyncio.sleep(0.5)
