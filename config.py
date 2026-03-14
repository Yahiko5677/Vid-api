import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

# ── Bot Credentials ───────────────────────────────────────────────────────
API_ID              = int(os.environ.get("API_ID", 0))
API_HASH            = os.environ.get("API_HASH", "")
BOT_TOKEN           = os.environ.get("BOT_TOKEN", "")

# ── MongoDB ───────────────────────────────────────────────────────────────
MONGO_URI           = os.environ.get("MONGO_URI", "")
DB_NAME             = os.environ.get("DB_NAME", "video_seq_bot")

# ── File Store Bots ──────────────────────────────────────────────────────
# Configured per-admin via /settings → stored in MongoDB
# No hardcoded bots here — all dynamic
FILE_STORE_MAP: dict = {}   # empty — filled from DB at runtime

# ── TMDB ──────────────────────────────────────────────────────────────────
TMDB_API_KEY        = os.environ.get("TMDB_API_KEY", "")

# ── Admins ────────────────────────────────────────────────────────────────
ADMINS              = list(map(int, filter(None, os.environ.get("ADMINS", "").split(","))))

# ── Log Channel ───────────────────────────────────────────────────────────
LOG_CHANNEL         = int(os.environ.get("LOG_CHANNEL", 0))

# ── Render ────────────────────────────────────────────────────────────────
PORT                = int(os.environ.get("PORT", 8080))

# ── Default caption template ──────────────────────────────────────────────
DEFAULT_CAPTION_TEMPLATE = (
    "🎬 <b>{title}</b> ({year})\n"
    "🎭 {genres}\n"
    "⭐ {score}  |  📊 {episodes} eps\n"
    "🎙 {studio}\n"
    "📺 {season}  •  {ep_range}\n"
    "🔊 {audio}  |  📝 {subs}\n\n"
    "<i>{synopsis}</i>"
)

# ── Default button label template ─────────────────────────────────────────
DEFAULT_BUTTON_LABEL = "📥 {quality}  •  {ep_range}"

# ── Default button layout (e.g. "2,1" = row1: 2 buttons, row2: 1 button) ─
DEFAULT_BUTTON_LAYOUT = "2,1"
