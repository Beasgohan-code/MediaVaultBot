#@mediavault
"""Inline mode — quick actions / library (no Drive)."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import BOT_USERNAME
from core.database import db
from core.emoji import ce


@Client.on_inline_query()
async def inline_search(client: Client, query: InlineQuery):
    user = query.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)
    if await db.is_banned(user.id):
        await query.answer(results=[], switch_pm_text="Banned", switch_pm_parameter="start", cache_time=10)
        return

    q = (query.query or "").strip()
    results = []
    if q:
        items = await db.search_library(user.id, q, limit=10)
        for i, it in enumerate(items):
            results.append(
                InlineQueryResultArticle(
                    id=f"lib{i}",
                    title=it.title[:60],
                    description=f"{it.source} · {it.extractor or ''}",
                    input_message_content=InputTextMessageContent(
                        f"📚 {it.title}\n{it.webpage_url or ''}"
                    ),
                )
            )
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="MediaVault — paste a URL in private chat",
                description="YouTube, Reddit, X, TikTok…",
                input_message_content=InputTextMessageContent(
                    f"Open @{BOT_USERNAME or 'bot'} and paste a media link."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Open bot", url=f"https://t.me/{BOT_USERNAME}")]
                ]) if BOT_USERNAME else None,
            )
        )
    await query.answer(results, cache_time=5, is_personal=True)
