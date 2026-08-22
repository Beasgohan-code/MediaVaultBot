#@mediavault
"""
Multi-site web search (YouTube + SoundCloud + tabs).
Paginated buttons → tap to download. Premium domains still gated on download.
"""
from __future__ import annotations

import html
import logging
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from core.database import db
from core.emoji import ce
from core.utils import human_duration
from core.ytdlp import web_search, SEARCH_BACKENDS
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

_search_cache: Dict[int, List[dict]] = {}
_query_cache: Dict[int, dict] = {}  # uid -> {q, source}
PAGE_SIZE = 5


def _esc(s: str) -> str:
    return html.escape(s or "")


def _source_kb(active: str) -> list:
    row = []
    for key, (_, label) in [("all", (None, "All")), *SEARCH_BACKENDS.items()]:
        mark = "•" if active == key else ""
        row.append(InlineKeyboardButton(f"{mark}{label}{mark}", callback_data=f"ws:src:{key}"))
    return row


def _page_kb(user_id: int, page: int) -> InlineKeyboardMarkup:
    items = _search_cache.get(user_id) or []
    meta = _query_cache.get(user_id) or {"q": "?", "source": "all"}
    total = len(items)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    page = max(0, min(page, pages - 1))
    start = page * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]

    rows = [_source_kb(meta.get("source", "all"))]
    for i, it in enumerate(chunk):
        idx = start + i
        title = (it.get("title") or "?")[:40]
        src = it.get("source") or ""
        dur = human_duration(it.get("duration"))
        extra = f" · {dur}" if dur and dur != "?" else ""
        label = f"{idx + 1}. [{src}] {title}{extra}"
        rows.append([InlineKeyboardButton(label[:64], callback_data=f"ws:dl:{idx}")])

    if not chunk and total == 0:
        rows.append([InlineKeyboardButton("No results", callback_data="ws:noop")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"ws:pg:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ws:noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"ws:pg:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("🎬 DL #1", callback_data="ws:dl:0"),
        InlineKeyboardButton("🎵 Audio #1", callback_data="ws:aud:0"),
        InlineKeyboardButton("❌", callback_data="close"),
    ])
    return InlineKeyboardMarkup(rows)


def _page_text(meta: dict, total: int, page: int) -> str:
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    page = max(0, min(page, pages - 1))
    src = meta.get("source", "all")
    return (
        f"<blockquote>{ce('crystal', '🔮')} <b>Web search</b>\n"
        f"Query: <code>{_esc(meta.get('q', ''))}</code>\n"
        f"Source: <code>{_esc(src)}</code> · Hits: <code>{total}</code> · "
        f"Page <code>{page + 1}/{pages}</code>\n\n"
        f"Sites with search: YouTube, SoundCloud.\n"
        f"Other sites (Reddit, X, TikTok…): paste the link.\n"
        f"Premium domains need /premium to download.</blockquote>"
    )


async def _run_search(status_msg, uid: int, query: str, source: str = "all"):
    try:
        results = await web_search(query, limit=15, source=source)
    except Exception as e:
        logger.exception("search")
        await status_msg.edit_text(
            f"<blockquote>❌ Search failed\n<code>{_esc(str(e)[:200])}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    _search_cache[uid] = results
    _query_cache[uid] = {"q": query, "source": source}
    await status_msg.edit_text(
        _page_text(_query_cache[uid], len(results), 0),
        reply_markup=_page_kb(uid, 0),
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("search"), group=2)
@check_ban
async def search_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        sites = ", ".join(v[1] for v in SEARCH_BACKENDS.values())
        await message.reply_text(
            f"<blockquote>{ce('crystal', '🔮')} <b>Search</b>\n\n"
            f"<code>/search lo-fi beats</code>\n"
            f"Sources: {sites} (tabs on results).\n\n"
            f"Reddit / X / TikTok / Instagram: paste URL.\n"
            f"Premium domains: unlock with /premium.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    query = parts[1].strip()
    if query.startswith("http://") or query.startswith("https://"):
        await message.reply_text(
            "<blockquote>Paste the link alone (or /video) to download.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    status = await message.reply_text(
        f"<blockquote>🔎 Searching <b>{_esc(query)}</b>…</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    await _run_search(status, message.from_user.id, query, "all")


@Client.on_callback_query(filters.regex(r"^ws:noop$"))
async def ws_noop(client: Client, query: CallbackQuery):
    await query.answer()


@Client.on_callback_query(filters.regex(r"^ws:src:(\w+)$"))
@check_ban
async def ws_source(client: Client, query: CallbackQuery):
    source = query.data.split(":")[2]
    uid = query.from_user.id
    meta = _query_cache.get(uid)
    if not meta:
        await query.answer("Search expired — /search again", show_alert=True)
        return
    await query.answer(f"Source: {source}")
    try:
        await query.message.edit_text(
            f"<blockquote>🔎 Searching ({_esc(source)})…</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await _run_search(query.message, uid, meta["q"], source)


@Client.on_callback_query(filters.regex(r"^ws:pg:(\d+)$"))
@check_ban
async def ws_page(client: Client, query: CallbackQuery):
    page = int(query.data.split(":")[2])
    uid = query.from_user.id
    items = _search_cache.get(uid) or []
    meta = _query_cache.get(uid) or {"q": "?", "source": "all"}
    if not items and meta.get("q") == "?":
        await query.answer("Expired", show_alert=True)
        return
    await query.answer()
    try:
        await query.message.edit_text(
            _page_text(meta, len(items), page),
            reply_markup=_page_kb(uid, page),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^ws:dl:(\d+)$"))
@check_ban
async def ws_download(client: Client, query: CallbackQuery):
    idx = int(query.data.split(":")[2])
    uid = query.from_user.id
    items = _search_cache.get(uid) or []
    if idx < 0 or idx >= len(items):
        await query.answer("Expired — /search again", show_alert=True)
        return
    item = items[idx]
    url = item.get("url")
    if not url:
        await query.answer("No URL", show_alert=True)
        return
    await query.answer("Loading…")
    try:
        query.message.from_user = query.from_user
    except Exception:
        pass
    from telegram.plugins.url_download import start_download_flow
    await start_download_flow(client, query.message, url, force_audio=False)


@Client.on_callback_query(filters.regex(r"^ws:aud:(\d+)$"))
@check_ban
async def ws_audio(client: Client, query: CallbackQuery):
    idx = int(query.data.split(":")[2])
    uid = query.from_user.id
    items = _search_cache.get(uid) or []
    if idx < 0 or idx >= len(items):
        await query.answer("Expired", show_alert=True)
        return
    url = items[idx].get("url")
    await query.answer("Audio…")
    try:
        query.message.from_user = query.from_user
    except Exception:
        pass
    from telegram.plugins.url_download import start_download_flow
    await start_download_flow(client, query.message, url, force_audio=True)
