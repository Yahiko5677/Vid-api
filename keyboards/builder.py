"""
All keyboard builders for the bot.
"""

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─── Settings main menu ──────────────────────────────────────────────────

def settings_menu(settings: dict) -> InlineKeyboardMarkup:
    mode      = settings.get("post_mode", "simple")
    mode_icon = "✅" if mode == "simple" else "☑️"
    rich_icon = "✅" if mode == "rich" else "☑️"
    sticker   = "✅ Set" if settings.get("sticker_id") else "❌ Not set"
    channels  = settings.get("channels", [])
    ch_count  = f"{len(channels)} channel(s)"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{mode_icon} Simple Mode", callback_data="set_mode_simple"),
            InlineKeyboardButton(f"{rich_icon} Rich Mode",   callback_data="set_mode_rich"),
        ],
        [InlineKeyboardButton(f"🔊 Audio/Subs Info",         callback_data="set_audio")],
        [InlineKeyboardButton(f"🎴 Sticker ({sticker})",     callback_data="set_sticker")],
        [InlineKeyboardButton(f"📢 Channels ({ch_count})",   callback_data="set_channels")],
        [InlineKeyboardButton("❌ Close",                    callback_data="close_settings")],
    ])


# ─── Channel manager ─────────────────────────────────────────────────────

def channel_manager(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        rows.append([
            InlineKeyboardButton(f"📢 {ch['name']}", callback_data=f"noop"),
            InlineKeyboardButton("🗑 Remove",        callback_data=f"remove_ch_{ch['id']}"),
        ])
    rows.append([InlineKeyboardButton("➕ Add Channel",  callback_data="add_channel")])
    rows.append([InlineKeyboardButton("🔙 Back",         callback_data="back_settings")])
    return InlineKeyboardMarkup(rows)


# ─── Channel picker (at post time) ───────────────────────────────────────

def channel_picker(channels: list[dict], selected: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        icon = "☑️" if ch["id"] in selected else "⬜️"
        rows.append([InlineKeyboardButton(
            f"{icon} {ch['name']}",
            callback_data=f"pick_ch_{ch['id']}"
        )])
    rows.append([
        InlineKeyboardButton("✅ Confirm",  callback_data="confirm_channels"),
        InlineKeyboardButton("❌ Cancel",   callback_data="cancel_post"),
    ])
    return InlineKeyboardMarkup(rows)


# ─── Upload confirm / edit ───────────────────────────────────────────────

def confirm_upload(title: str, season: int, episode: int, quality: str, confirm_key: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm",    callback_data=f"confirm_upload:{confirm_key}"),
            InlineKeyboardButton("✏️ Edit Title", callback_data=f"edit_title:{confirm_key}"),
        ],
        [InlineKeyboardButton("🗑 Discard",       callback_data=f"discard_upload:{confirm_key}")],
    ])


# ─── Post confirm (before sending to channel) ────────────────────────────

def post_confirm(audio_info: str, sub_info: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Post Now",      callback_data="do_post"),
            InlineKeyboardButton("✏️ Edit Info",     callback_data="edit_post_info"),
        ],
        [
            InlineKeyboardButton(f"🔊 {audio_info}", callback_data="edit_audio"),
            InlineKeyboardButton(f"📝 {sub_info}",   callback_data="edit_subs"),
        ],
        [InlineKeyboardButton("❌ Cancel",           callback_data="cancel_post")],
    ])


# ─── Force post (admin trigger for pending episodes) ─────────────────────

def force_post_keyboard(title_key: str, season: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🚀 Force Post",
                callback_data=f"force_post_{title_key}_{season}"
            ),
            InlineKeyboardButton("❌ Skip", callback_data="cancel_post"),
        ]
    ])


# ─── Misc ────────────────────────────────────────────────────────────────

def close_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close")]])
