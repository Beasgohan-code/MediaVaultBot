# MediaVaultBot - Modern Personal Media Bot (2026)
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ───
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# ─── Google Drive ───
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
DRIVE_ROOT_FOLDER_ID = os.environ.get("DRIVE_ROOT_FOLDER_ID", "")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.json")
USE_SERVICE_ACCOUNT = os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE)

# ─── PostgreSQL ───
_raw_db = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/mediavault"
)
# Railway/Render give postgresql:// — SQLAlchemy async needs +asyncpg
if _raw_db.startswith("postgres://"):
    _raw_db = _raw_db.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db.startswith("postgresql://") and "+asyncpg" not in _raw_db:
    _raw_db = _raw_db.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL = _raw_db

# ─── yt-dlp ───
YTDLP_ENABLED = os.environ.get("YTDLP_ENABLED", "true").lower() == "true"
YTDLP_MAX_FILESIZE = os.environ.get("YTDLP_MAX_FILESIZE", "1.5G")
YTDLP_FORMAT = os.environ.get("YTDLP_FORMAT", "bv*+ba/b")
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "")
YTDLP_COOKIES_FROM_BROWSER = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
YTDLP_OUTPUT_TEMPLATE = os.environ.get("YTDLP_OUTPUT_TEMPLATE", "%(title).80s [%(id)s].%(ext)s")
YTDLP_AGE_LIMIT = int(os.environ.get("YTDLP_AGE_LIMIT", 0))
YTDLP_PLAYLIST_MAX = int(os.environ.get("YTDLP_PLAYLIST_MAX", 5))  # 0 = disable playlists

QUALITY_PRESETS = {
    "best": "bv*+ba/b",
    "1080": "bv*[height<=1080]+ba/b[height<=1080]",
    "720": "bv*[height<=720]+ba/b[height<=720]",
    "480": "bv*[height<=480]+ba/b[height<=480]",
    "360": "bv*[height<=360]+ba/b[height<=360]",
    "audio": "ba/b",
}

# ─── Queue ───
QUEUE_MAX_GLOBAL = int(os.environ.get("QUEUE_MAX_GLOBAL", 8))
QUEUE_MAX_PER_USER = int(os.environ.get("QUEUE_MAX_PER_USER", 2))

# ─── Rate limit (URLs per minute) ───
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", 6))

# ─── Quotas ───
QUOTA_DAILY_DOWNLOADS = int(os.environ.get("QUOTA_DAILY_DOWNLOADS", 20))
QUOTA_DAILY_MB = int(os.environ.get("QUOTA_DAILY_MB", 2048))
QUOTA_ADMIN_UNLIMITED = os.environ.get("QUOTA_ADMIN_UNLIMITED", "true").lower() == "true"

# ─── Behaviour ───
AUTO_DELETE_SECONDS = int(os.environ.get("AUTO_DELETE_SECONDS", 3600))
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 2000))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", 300))
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "")
START_PIC = os.environ.get("START_PIC", "https://files.catbox.moe/4b8jvw.jpg")
REQUIRE_TOS_ACCEPT = os.environ.get("REQUIRE_TOS_ACCEPT", "true").lower() == "true"
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", 8080))
SHARE_CHANNEL = os.environ.get("SHARE_CHANNEL", "")  # channel id to offer "Share" button
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
DOWNLOAD_SUBS = os.environ.get("DOWNLOAD_SUBS", "true").lower() == "true"
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_REGION = os.environ.get("TMDB_REGION", "US")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # e.g. https://xxx.com — empty = polling
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/telegram/webhook")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))
INSTANCE_ID = os.environ.get("INSTANCE_ID", "main")  # multi-instance label
FILENAME_TEMPLATE_DEFAULT = os.environ.get("FILENAME_TEMPLATE_DEFAULT", "{title}")

DOWNLOAD_SUBS = os.environ.get("DOWNLOAD_SUBS", "true").lower() == "true"

TEMP_CLEANUP_MINUTES = int(os.environ.get("TEMP_CLEANUP_MINUTES", 30))

CAPTION_TEMPLATE = os.environ.get(
    "CAPTION_TEMPLATE",
    "📁 <b>{name}</b>\n📦 Size: {size}\n🔗 Source: {source}\n\n⚡ MediaVault"
)
PROGRESS_TEMPLATE = """
<blockquote>📥 <b>{filename}</b>
{bar}
⚡ {speed} | 📦 {done} / {total}
⏳ ETA: {eta}</blockquote>
"""

TOS_TEXT = """\
≡ <b>Terms of Use &amp; Risk Disclaimer</b>

By using the download features of this bot you acknowledge and agree that:

1. You will only download content you are <b>legally allowed</b> to access.
2. You accept <b>full personal responsibility</b> for every URL you submit.
3. The bot creator / host is <b>not responsible</b> for the content you request, including any NSFW, age-restricted, or copyrighted material.
4. Cookies (from file or browser) are used solely to access content <b>you already have permission</b> to view in your own browser.
5. Misuse (piracy, redistribution, harassment, illegal content) is strictly forbidden and may result in a permanent ban.
6. All downloads are provided <b>as-is</b>, at your own risk. No warranty.

If you do not agree, do not use the download features.

Tap <b>I Accept</b> to continue.
"""
