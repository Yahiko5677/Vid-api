# v5 - 2026-03-20
"""
post.py — Post engine (simple + rich mode).

Simple mode: channel ← admin PM files directly, episode label + sticker
Rich mode:   files → DB channel → batch link → channel post with thumbnail + buttons

Episode title fetch: TMDB season → Jikan global list → fallback empty
Episode offset: if admin set ep_offset=175 for S07E01, real episode = 176
"""

import asyncio
import io
import logging

from pyrogram import Client
from pyrogram.types import Message

from utils import pacing
from helper_func import encode

logger = logging.getLogger(__name__)

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p"]


# ── Helpers ───────────────────────────────────────────────────

def _episodes_sorted(episodes: list) -> list:
    return sorted(episodes, key=lambda x: x.get("episode", 0))


def _sorted_qualities(qualities: dict) -> list:
    order = {q: i for i, q in enumerate(QUALITY_ORDER)}
    return sorted(qualities.items(), key=lambda kv: order.get(kv[0], 99))


def _get_bot_and_channel(quality: str, quality_bots: dict):
    qb = quality_bots.get(quality, {})
    return qb.get("bot"), qb.get("channel")


async def _get_link(msg_id: int, bot_name: str, ch_id: int) -> str:
    key    = await encode(f"get-{msg_id * abs(ch_id)}")
    return f"https://t.me/{bot_name}?start={key}"


async def _get_batch_link(start_id: int, end_id: int, bot_name: str, ch_id: int) -> str:
    key = await encode(f"get-{start_id * abs(ch_id)}-{end_id * abs(ch_id)}")
    return f"https://t.me/{bot_name}?start={key}"


# ── Episode title fetch ───────────────────────────────────────

async def _fetch_episode_titles(episodes: list, meta: dict | None, ep_offset: int = 0) -> list:
    """
    Enrich each episode dict with ep_title.
    ep_offset: if S07E01 = real episode 176, set ep_offset=175
    TMDB: fetches by season number
    Jikan: fetches all episodes (offset applied for lookup)
    """
    if not meta:
        return episodes

    tmdb_id = meta.get("tmdb_id")
    mal_id  = meta.get("mal_id")
    season  = episodes[0]["season"] if episodes else 1
    ep_titles: dict[int, str] = {}

    try:
        if tmdb_id:
            from services.tmdb import get_episode_titles
            # For dubbed seasons use season number directly
            ep_titles = await get_episode_titles(tmdb_id, season)
            # If empty (dubbed split season), try season 1 with offset
            if not ep_titles and ep_offset == 0:
                ep_titles = await get_episode_titles(tmdb_id, 1)
        if not ep_titles and mal_id:
            from services.jikan import get_episode_titles as jikan_ep_titles
            ep_titles = await jikan_ep_titles(mal_id)
    except Exception as e:
        logger.warning("Episode title fetch failed: " + str(e))

    result = []
    for ep in episodes:
        ep = dict(ep)
        ep_num = ep["episode"]
        # Real episode number for lookup = local ep + offset
        real_ep = ep_num + ep_offset
        ep["ep_title"]  = ep_titles.get(real_ep) or ep_titles.get(ep_num) or ""
        ep["real_ep"]   = real_ep
        result.append(ep)
    return result


# ── Caption render ────────────────────────────────────────────

def _clean(val, fallback="") -> str:
    if not val:
        return fallback
    s = str(val).strip()
    return fallback if s in ("N/A", "None", "?", "0", "0.0") else s


def _render_caption(
    template: str, meta: dict | None, ep_range: str,
    season: int, audio_info: str, sub_info: str,
) -> str:
    import re as _re
    m        = meta or {}
    title    = _clean(m.get("title"),    "Unknown Title")
    year     = _clean(m.get("year"),     "")
    genres   = " • ".join(g for g in (m.get("genres") or [])[:3] if g)
    score    = _clean(m.get("score"),    "")
    episodes = _clean(m.get("episodes"), "")
    studio   = _clean(m.get("studio"),   "")
    synopsis = _clean(m.get("synopsis") or m.get("overview"), "")

    def _esc(s): return str(s).replace("{", "{{").replace("}", "}}")

    # Escape braces in template itself (handles custom templates with stray braces)
    safe_tpl = template.replace("{", "{{").replace("}", "}}")
    for var in ("title","year","genres","score","episodes","studio","synopsis",
                "season","ep_range","audio","subs"):
        safe_tpl = safe_tpl.replace("{{" + var + "}}", "{" + var + "}")

    try:
        rendered = safe_tpl.format(
            title    = _esc(title),
            year     = _esc(year),
            genres   = _esc(genres),
            score    = _esc(score),
            episodes = _esc(episodes),
            studio   = _esc(studio),
            synopsis = _esc(synopsis),
            season   = "Season " + str(season),
            ep_range = ep_range,
            audio    = _esc(audio_info),
            subs     = _esc(sub_info),
        )
    except (KeyError, ValueError):
        rendered = (
            "<b>" + title + "</b>\n"
            + "Season " + str(season) + " • " + ep_range + "\n"
            + "🔊 " + audio_info + " | 📝 " + sub_info
        )

    # Remove lines that are all symbols with no real text
    lines  = rendered.split("\n")
    result, prev_blank = [], False
    for line in lines:
        import re as _re2
        text_only = _re2.sub(r'[^\w]', '', line.strip())
        is_blank  = not line.strip()
        if is_blank:
            if not prev_blank:
                result.append("")
            prev_blank = True
        elif text_only:
            result.append(line)
            prev_blank = False

    return "\n".join(result).strip()


# ── Simple mode ───────────────────────────────────────────────

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
        real_ep   = ep.get("real_ep", episode)
        qualities = ep.get("qualities", {})
        ep_title  = ep.get("ep_title", "")

        # Episode header
        if season > 1:
            label = f"Season {season:02d} • Episode {episode:02d}"
        else:
            label = f"Episode {episode:02d}"

        # If real ep differs from local ep, show both
        if real_ep != episode:
            label += f"  <code>(#{real_ep})</code>"

        msg_text = "<b>" + label + "</b>"
        if ep_title:
            msg_text += "\n<blockquote>" + ep_title + "</blockquote>"

        await pacing.send(client, channel_id, msg_text)

        for quality, qdata in _sorted_qualities(qualities):
            if quality not in ch_qualities:
                continue
            from_chat = qdata.get("from_chat_id", 0)
            if not from_chat:
                logger.warning(f"No source chat for {quality} ep{episode}")
                continue
            try:
                await pacing.raw_copy_message(
                    client,
                    chat_id              = channel_id,
                    from_chat_id         = from_chat,
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


# ── Rich mode ─────────────────────────────────────────────────

async def _build_quality_batch_links(
    client: Client,
    episodes: list,
    ch_qualities: list,
    quality_bots: dict,
    sticker_id: str | None = None,
    notify_chat_id: int | None = None,
) -> dict[str, str]:
    quality_links: dict[str, str] = {}

    for quality in [q for q in QUALITY_ORDER if q in ch_qualities]:
        bot_name, db_ch = _get_bot_and_channel(quality, quality_bots)
        if not bot_name or not db_ch:
            logger.warning(f"No File Store Bot for {quality} — set via /settings")
            continue

        msg_ids = []
        for ep in _episodes_sorted(episodes):
            qdata = ep.get("qualities", {}).get(quality)
            if not qdata:
                continue
            from_chat = qdata.get("from_chat_id", 0)
            if not from_chat:
                continue
            try:
                stored = await pacing.raw_copy_message(
                    client,
                    chat_id              = db_ch,
                    from_chat_id         = from_chat,
                    message_id           = qdata["msg_id"],
                    disable_notification = True,
                )
                msg_ids.append(stored.id)
            except Exception as ex:
                logger.error(f"Batch copy {quality} ep{ep['episode']}: {ex}")

        if not msg_ids:
            continue

        sticker_msg_id = None
        if sticker_id:
            try:
                sent           = await client.send_sticker(chat_id=db_ch, sticker=sticker_id)
                sticker_msg_id = sent.id
                await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"Sticker failed {quality} DB channel: {e}")

        end_id = sticker_msg_id if sticker_msg_id else msg_ids[-1]
        if len(msg_ids) >= 2 or sticker_msg_id:
            link = await _get_batch_link(msg_ids[0], end_id, bot_name, db_ch)
        else:
            link = await _get_link(msg_ids[0], bot_name, db_ch)

        quality_links[quality] = link

    return quality_links


async def post_rich_mode(
    client: Client,
    channel_id: int,
    episodes: list,
    meta: dict | None,
    settings: dict,
    ch_qualities: list,
):
    quality_bots = settings.get("quality_bots", {})
    sticker_id   = settings.get("sticker_id")
    audio        = settings.get("audio_info", "Hindi + English")
    subs         = settings.get("sub_info", "English")
    template     = settings.get("caption_template", "")
    btn_label    = settings.get("button_label", "📥 {quality}  •  {ep_range}")
    layout       = settings.get("button_layout", "2,1")
    watermark    = settings.get("watermark", "")
    content_type = settings.get("content_type", "anime")
    is_movie     = (content_type == "movie")

    season   = episodes[0]["season"]
    ep_count = len(episodes)
    ep_range = "E01-E" + str(ep_count).zfill(2) if ep_count > 1 else "E01"

    quality_links = await _build_quality_batch_links(
        client, episodes, ch_qualities, quality_bots,
        sticker_id=sticker_id, notify_chat_id=channel_id
    )

    if not quality_links:
        raise RuntimeError(
            "❌ No File Store Bot links generated.\n\n"
            "Rich mode requires at least one File Store Bot configured.\n"
            "Go to /settings → 🤖 File Store Bots and set a bot + DB channel for each quality."
        )

    caption = settings.get("caption_override") or _render_caption(
        template, meta, ep_range, season, audio, subs
    )

    from keyboards import quality_buttons
    markup = quality_buttons(quality_links, btn_label, layout, ep_range)

    sent        = False
    thumb_bytes = settings.get("custom_thumb_bytes")
    poster_url  = meta.get("poster_url") if meta else None

    if not thumb_bytes and poster_url:
        from services.tmdb import download_poster
        from services.thumbnail import process_thumbnail, build_thumbnail
        backdrop_url = meta.get("backdrop_url") if meta else None
        thumb_meta   = {
            "title":    meta.get("title","") if meta else "",
            "synopsis": (meta.get("synopsis") or meta.get("overview","")) if meta else "",
            "genres":   meta.get("genres",[]) if meta else [],
            "score":    meta.get("score","") if meta else "",
            "year":     meta.get("year","") if meta else "",
        }
        if not is_movie:
            ep_range_short           = "01-" + str(ep_count).zfill(2) if ep_count > 1 else "01"
            thumb_meta["episode"]    = ep_range_short
            thumb_meta["season"]     = str(season)

        thumb_bytes = await build_thumbnail(
            poster_url   = poster_url,
            backdrop_url = backdrop_url,
            watermark    = watermark,
            meta         = thumb_meta,
            is_movie     = is_movie,
        )
        if not thumb_bytes:
            raw = await download_poster(poster_url)
            if raw:
                thumb_bytes = process_thumbnail(raw)

    if thumb_bytes:
        try:
            await pacing.send_photo(
                client,
                chat_id      = channel_id,
                photo        = io.BytesIO(thumb_bytes),
                caption      = caption,
                reply_markup = markup,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Photo send failed, falling back: {e}")

    if not sent:
        await pacing.send(client, channel_id, caption, reply_markup=markup)


# ── Dispatch ──────────────────────────────────────────────────

async def dispatch_post(
    client:      Client,
    channel_ids: list[int],
    episodes:    list,
    settings:    dict,
    meta:        dict | None = None,
) -> None:
    mode         = settings.get("post_mode", "simple")
    quality_bots = settings.get("quality_bots", {})
    sticker_id   = settings.get("sticker_id")
    ep_offset    = settings.get("ep_offset", 0)

    # Enrich episodes with real episode numbers + titles
    enriched = await _fetch_episode_titles(episodes, meta, ep_offset)

    for ch_id in channel_ids:
        from database.db import get_settings
        admin_id    = episodes[0].get("admin_id") if episodes else None
        all_ch      = settings.get("channels", [])
        ch          = next((c for c in all_ch if c["id"] == ch_id), {})
        ch_qualities= ch.get("qualities", ["480p","720p","1080p"])

        if mode == "simple":
            await post_simple_mode(
                client, ch_id, enriched, sticker_id, ch_qualities, quality_bots
            )
        else:
            await post_rich_mode(
                client, ch_id, enriched, meta, settings, ch_qualities
            )
