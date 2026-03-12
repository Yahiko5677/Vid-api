import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot Credentials ───────────────────────────────────────────────────────
API_ID              = int(os.environ.get("API_ID", 0))
API_HASH            = os.environ.get("API_HASH", "")
BOT_TOKEN           = os.environ.get("BOT_TOKEN", "")

# ── MongoDB ───────────────────────────────────────────────────────────────
MONGO_URI           = os.environ.get("MONGO_URI", "")
DB_NAME             = os.environ.get("DB_NAME", "video_seq_bot")

# ── File Store Bot ────────────────────────────────────────────────────────
# The separate bot that stores/serves files
# e.g.  FILE_STORE_BOT = "MyFileStoreBot"  (no @)
FILE_STORE_BOT      = os.environ.get("FILE_STORE_BOT", "")
# The private DB channel used by File Store Bot (negative ID)
FILE_STORE_CHANNEL  = int(os.environ.get("FILE_STORE_CHANNEL", 0))

# ── TMDB ─────────────────────────────────────────────────────────────────
TMDB_API_KEY        = os.environ.get("TMDB_API_KEY", "")

# ── Admins (comma-separated Telegram user IDs) ────────────────────────────
ADMINS              = list(map(int, filter(None, os.environ.get("ADMINS", "").split(","))))

# ── Log Channel (global fallback; per-admin override in /settings) ────────
# Set to your log channel ID (negative int) or leave 0 to disable globally
LOG_CHANNEL         = int(os.environ.get("LOG_CHANNEL", 0))

# ── Render / Server ───────────────────────────────────────────────────────
PORT                = int(os.environ.get("PORT", 8080))
