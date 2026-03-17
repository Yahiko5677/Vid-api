"""
All keyboard builders for the bot.
"""
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p"]


# ═══════════════════════════════════════════════════════
#  SETTINGS MAIN MENU
# ═══════════════════════════════════════════════════════

def settings_menu(settings: dict) -> InlineKeyboardMarkup:
    mode       = settings.get("post_mode", "simple")
    s_icon     = "✅" if mode == "simple" else "☑️"
    r_icon     = "✅" if mode == "rich"   else "☑️"
    sticker    = "✅" if settings.get("sticker_id") else "❌"
    ch_count   = len(settings.get("channels", []))
    audio      = settings.get("audio_info", "—")[:12]
    subs       = settings.get("sub_info",   "—")[:12]
    layout     = settings.get("button_layout", "2,1")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{s_icon} Simple", callback_data="set_mode_simple"),
            InlineKeyboardButton(f"{r_icon} Rich",   callback_data="set_mode_rich"),
        ],
        [InlineKeyboardButton("📝 Caption Template",  callback_data="set_caption")],
        [InlineKeyboardButton(f"🔖 Watermark: {settings.get("watermark","") or "Not set"}", callback_data="set_watermark")],
        [
            InlineKeyboardButton("🏷 Button Label",   callback_data="set_btn_label"),
            InlineKeyboardButton(f"⌨️ Layout: {layout}", callback_data="set_btn_layout"),
        ],
        [
            InlineKeyboardButton(f"🔊 {audio}",       callback_data="set_audio"),
            InlineKeyboardButton(f"📝 {subs}",        callback_data="set_subs"),
        ],
        [InlineKeyboardButton(f"🎴 Sticker ({sticker})", callback_data="set_sticker")],
    [InlineKeyboardButton(f"💧 Watermark",             callback_data="set_watermark")],
        [InlineKeyboardButton("🤖 File Store Bots",   callback_data="set_quality_bots")],
        [InlineKeyboardButton(f"📢 Channels ({ch_count})", callback_data="set_channels")],
        [InlineKeyboardButton("❌ Close",             callback_data="close_settings")],
    ])


# ═══════════════════════════════════════════════════════
#  QUALITY BOTS MENU
# ═══════════════════════════════════════════════════════

def quality_bots_menu(quality_bots: dict) -> InlineKeyboardMarkup:
    rows = []
    for q in ["480p", "720p", "1080p"]:
        qb   = quality_bots.get(q, {})
        bot  = qb.get("bot", "❌ Not set")
        rows.append([InlineKeyboardButton(
            f"{'✅' if qb else '❌'} {q} → @{bot}" if qb else f"❌ {q} → Not set",
            callback_data=f"set_qbot_{q}"
        )])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="back_settings")])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════
#  CHANNEL MANAGER
# ═══════════════════════════════════════════════════════

def channel_manager(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        quals    = ch.get("qualities", [])
        q_icons  = " ".join(
            f"{'✅' if q in quals else '❌'}{q}" for q in ["480p","720p","1080p"]
        )
        rows.append([
            InlineKeyboardButton(f"📢 {ch['name']}", callback_data=f"ch_info_{ch['id']}"),
            InlineKeyboardButton("⚙️ Qualities",     callback_data=f"ch_quals_{ch['id']}"),
            InlineKeyboardButton("🗑",               callback_data=f"remove_ch_{ch['id']}"),
        ])
        rows.append([InlineKeyboardButton(q_icons,   callback_data=f"ch_info_{ch['id']}")])
    rows.append([InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")])
    rows.append([InlineKeyboardButton("🔙 Back",        callback_data="back_settings")])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════
#  CHANNEL QUALITY PICKER
# ═══════════════════════════════════════════════════════

def channel_quality_picker(channel_id: int, channel_name: str, selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for q in ["480p", "720p", "1080p"]:
        icon = "✅" if q in selected else "☑️"
        rows.append([InlineKeyboardButton(
            f"{icon} {q}",
            callback_data=f"cqtoggle_{channel_id}_{q}"
        )])
    rows.append([
        InlineKeyboardButton("✅ Save",  callback_data=f"cqsave_{channel_id}"),
        InlineKeyboardButton("🔙 Back",  callback_data="set_channels"),
    ])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════
#  CHANNEL PICKER (at post time)
# ═══════════════════════════════════════════════════════

def channel_picker(channels: list[dict], selected: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        icon  = "☑️" if ch["id"] in selected else "⬜️"
        quals = ", ".join(ch.get("qualities", []))
        rows.append([InlineKeyboardButton(
            f"{icon} {ch['name']}  [{quals}]",
            callback_data=f"pick_ch_{ch['id']}"
        )])
    rows.append([
        InlineKeyboardButton("✅ Confirm", callback_data="confirm_channels"),
        InlineKeyboardButton("❌ Cancel",  callback_data="cancel_post"),
    ])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════
#  POST QUALITY BUTTONS  (channel post)
# ═══════════════════════════════════════════════════════

def quality_buttons(
    quality_links: dict[str, str],   # { "480p": url, "720p": url, ... }
    label_template: str,             # e.g. "📥 {quality}  •  {ep_range}"
    layout: str,                     # e.g. "2,1" or "3" or "1,1,1"
    ep_range: str,                   # e.g. "E01-E13"
) -> InlineKeyboardMarkup:
    # Build ordered button list
    btns = []
    for q in QUALITY_ORDER:
        if q not in quality_links:
            continue
        label = label_template.replace("{quality}", q).replace("{ep_range}", ep_range)
        btns.append(InlineKeyboardButton(label, url=quality_links[q]))

    # Parse layout string into row sizes
    try:
        row_sizes = [int(x) for x in layout.split(",")]
    except Exception:
        row_sizes = [2, 1]  # fallback

    rows  = []
    idx   = 0
    for size in row_sizes:
        row = btns[idx:idx + size]
        if row:
            rows.append(row)
        idx += size
        if idx >= len(btns):
            break

    # Any remaining buttons not covered by layout go in last row
    if idx < len(btns):
        rows.append(btns[idx:])

    return InlineKeyboardMarkup(rows) if rows else None


# ═══════════════════════════════════════════════════════
#  CONTENT TYPE SELECTOR
# ═══════════════════════════════════════════════════════

def content_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎌 Anime",     callback_data="ctype_anime"),
            InlineKeyboardButton("🎬 Movie",     callback_data="ctype_movie"),
            InlineKeyboardButton("📺 TV Series", callback_data="ctype_tv"),
        ],
        [InlineKeyboardButton("❌ Cancel",       callback_data="cancel_post")],
    ])


# ═══════════════════════════════════════════════════════
#  POST PREVIEW KEYBOARD
# ═══════════════════════════════════════════════════════

def post_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Change Thumbnail", callback_data="preview_change_thumb"),
            InlineKeyboardButton("✅ Post Now",         callback_data="preview_post"),
        ],
        [
            InlineKeyboardButton("📝 Edit Caption",     callback_data="preview_edit_caption"),
            InlineKeyboardButton("❌ Cancel",            callback_data="cancel_post"),
        ],
    ])


# ═══════════════════════════════════════════════════════
#  CONTENT TYPE PICKER
# ═══════════════════════════════════════════════════════

def content_type_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎌 Anime",   callback_data="ctype_anime"),
            InlineKeyboardButton("📺 TV Show", callback_data="ctype_tv"),
            InlineKeyboardButton("🎬 Movie",   callback_data="ctype_movie"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")],
    ])


# ═══════════════════════════════════════════════════════
#  METADATA PICKER (rich mode)
# ═══════════════════════════════════════════════════════

def metadata_picker(results: list[dict]) -> InlineKeyboardMarkup:
    from services.metadata import _label
    rows = []
    for i, r in enumerate(results):
        title = r.get("title", "Unknown")[:28]
        label = _label(r)
        rows.append([InlineKeyboardButton(
            f"{i+1}. {title} {label}",
            callback_data=f"meta_pick_{i}"
        )])
    rows.append([
        InlineKeyboardButton("🔍 Search Again", callback_data="meta_search"),
        InlineKeyboardButton("⏭ Skip Meta",    callback_data="meta_skip"),
    ])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════════
#  UPLOAD CONFIRM
# ═══════════════════════════════════════════════════════

def confirm_upload(title: str, season: int, episode: int, quality: str, key: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm",    callback_data=f"cu:{key}"),
            InlineKeyboardButton("✏️ Edit Title", callback_data=f"et:{key}"),
        ],
        [InlineKeyboardButton("🗑 Discard All",   callback_data=f"du:{key}")],
    ])


# ═══════════════════════════════════════════════════════
#  POST CONFIRM (before sending)
# ═══════════════════════════════════════════════════════

def post_confirm(audio_info: str, sub_info: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Post Now", callback_data="do_post"),
            InlineKeyboardButton("❌ Cancel",   callback_data="cancel_post"),
        ],
        [
            InlineKeyboardButton(f"🔊 {audio_info}", callback_data="edit_audio"),
            InlineKeyboardButton(f"📝 {sub_info}",   callback_data="edit_subs"),
        ],
    ])


# ═══════════════════════════════════════════════════════
#  FORCE POST
# ═══════════════════════════════════════════════════════

def force_post_keyboard(title_key: str, season: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Force Post", callback_data=f"force_post_{title_key}_{season}"),
        InlineKeyboardButton("❌ Skip",       callback_data="cancel_post"),
    ]])


# ═══════════════════════════════════════════════════════
#  MISC
# ═══════════════════════════════════════════════════════

def close_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close_settings")]])
