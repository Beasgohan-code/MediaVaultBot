#@mediavault
"""Plain text /search → library history (no Google Drive)."""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.database import db
from core.emoji import ce
from core.ytdlp import is_supported_url
from telegram.decorators import check_ban

# Commands handled elsewhere — exclude so URL handler & others win
_EXCLUDE = [
    "start", "help", "about", "search", "library", "settings", "me", "ping",
    "tos", "sites", "quota", "cookies", "queue", "schedule", "schedules",
    "collections", "watchlater", "colnew", "coladd", "recent", "export",
    "retry", "where", "tmdb", "stats", "autodel", "ban", "unban", "admins",
    "broadcast", "logs", "backup", "fname",
]


@Client.on_message(filters.private & filters.command("search"))
@check_ban
async def search_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            f"<blockquote>{ce('crystal', '🔮')} <b>Search</b>\n"
            f"<code>/search query</code> — your download history\n"
            f"Or paste a media URL to download.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    await _lib_search(message, parts[1].strip())


@Client.on_message(
    filters.private
    & filters.text
    & ~filters.reply
    & ~filters.command(_EXCLUDE)
)
@check_ban
async def text_router(client: Client, message: Message):
    """Non-command text: URL → ignore here (url_download handles it); else library hint."""
    text = (message.text or "").strip()
    if len(text) < 2:
        return
    # Let url_download plugin handle links
    if text.startswith("http://") or text.startswith("https://") or is_supported_url(text):
        return
    # Short queries → search library
    if len(text) <= 80:
        await _lib_search(message, text)


async def _lib_search(message: Message, query: str):
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    items = await db.search_library(message.from_user.id, query, limit=15)
    if not items:
        await message.reply_text(
            f"<blockquote>{ce('ghost', '👻')} No history for <b>{query}</b>\n"
            f"Paste a public URL to download.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = [f"<blockquote>{ce('bookmark', '🔖')} <b>History</b> — {query}\n"]
    for it in items:
        lines.append(f"• {it.title[:55]}")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
