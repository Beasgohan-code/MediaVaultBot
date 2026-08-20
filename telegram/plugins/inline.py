#@mediavault
"""
Inline mode — search Drive or show quick actions from any chat.
Usage: @YourBot query
"""
from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ParseMode

from config import BOT_USERNAME, YTDLP_ENABLED
from core.database import db
from core.drive import drive
from core.utils import format_size
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)


@Client.on_inline_query()
async def inline_search(client: Client, query: InlineQuery):
    user = query.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    if await db.is_banned(user.id):
        await query.answer(
            results=[],
            switch_pm_text="You are banned",
            switch_pm_parameter="start",
            cache_time=10,
        )
        return

    q = (query.query or "").strip()
    results = []

    # Empty query → quick actions
    if not q:
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="📖 Help & Commands",
                description="Open bot help",
                input_message_content=InputTextMessageContent(
                    f"Open @{BOT_USERNAME or 'bot'} and send /help"
                ),
            )
        )
        results.append(
            InlineQueryResultArticle(
                id="sites",
                title="🌐 Supported Sites",
                description="YouTube, Reddit, X, TikTok…",
                input_message_content=InputTextMessageContent(
                    "Paste any public URL in the bot chat to download.\n/sites for full list."
                ),
            )
        )
        await query.answer(results, cache_time=30, is_personal=True)
        return

    # URL-looking → offer download tip
    if q.startswith("http://") or q.startswith("https://"):
        results.append(
            InlineQueryResultArticle(
                id="url",
                title="📥 Download this URL",
                description=q[:80],
                input_message_content=InputTextMessageContent(
                    f"Send this link to the bot to download:\n{q}"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Open bot", url=f"https://t.me/{BOT_USERNAME}?start=dl")]
                ]) if BOT_USERNAME else None,
            )
        )
        await query.answer(results, cache_time=10, is_personal=True)
        return

    # Drive search
    try:
        files = await drive.search(q, page_size=15)
    except Exception as e:
        logger.warning("inline drive search failed: %s", e)
        files = []

    for i, f in enumerate(files):
        name = f.get("name", "file")[:60]
        size = format_size(int(f["size"])) if f.get("size") else ""
        mime = f.get("mimeType") or ""
        is_folder = mime == "application/vnd.google-apps.folder"
        icon = "📁" if is_folder else "📄"
        desc = f"{size} • {mime.split('/')[-1]}" if size else mime
        results.append(
            InlineQueryResultArticle(
                id=f"drv_{f['id'][:20]}_{i}",
                title=f"{icon} {name}",
                description=desc[:80],
                input_message_content=InputTextMessageContent(
                    f"Drive file: <b>{name}</b>\nID: <code>{f['id']}</code>\n\nOpen the bot and use /browse or search to send it.",
                    parse_mode=ParseMode.HTML,
                ),
            )
        )

    if not results:
        results.append(
            InlineQueryResultArticle(
                id="none",
                title="No results",
                description=f"Nothing found for “{q}”",
                input_message_content=InputTextMessageContent(f"No Drive results for: {q}"),
            )
        )

    await query.answer(results, cache_time=15, is_personal=True)
