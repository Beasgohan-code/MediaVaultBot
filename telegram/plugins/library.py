#@mediavault
"""Unified library search, collections, watch-later."""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from core.database import db
from core.drive import drive
from core.utils import format_size
from telegram.decorators import check_ban


@Client.on_message(filters.private & filters.command("library"))
@check_ban
async def library_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>📚 <b>Library</b>\n\n"
            "<code>/library query</code> — search download history\n"
            "<code>/collections</code> — your lists\n"
            "<code>/watchlater</code> — quick list</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    q = parts[1].strip()
    items = await db.search_library(message.from_user.id, q)
    # also try Drive
    drive_hits = []
    try:
        drive_hits = await drive.search(q, page_size=8)
    except Exception:
        pass

    lines = ["<blockquote>📚 <b>Results</b>"]
    if items:
        lines.append("\n<b>History</b>")
        for it in items[:10]:
            lines.append(f"• {it.title[:50]} ({it.source})")
    if drive_hits:
        lines.append("\n<b>Drive</b>")
        for f in drive_hits[:8]:
            lines.append(f"• {f.get('name','?')[:50]}")
    if len(lines) == 1:
        lines.append("\nNothing found.")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command(["collections", "watchlater"]))
@check_ban
async def collections_cmd(client: Client, message: Message):
    cols = await db.list_collections(message.from_user.id)
    # ensure default Watch Later
    if not any(c.name.lower() == "watch later" for c in cols):
        await db.create_collection(message.from_user.id, "Watch Later")
        cols = await db.list_collections(message.from_user.id)

    if message.command[0] == "watchlater":
        wl = next((c for c in cols if c.name.lower() == "watch later"), None)
        if not wl:
            await message.reply_text("No Watch Later list.")
            return
        items = await db.collection_items(wl.id)
        if not items:
            await message.reply_text("<blockquote>⭐ Watch Later is empty.</blockquote>", parse_mode=ParseMode.HTML)
            return
        lines = ["<blockquote>⭐ <b>Watch Later</b>\n"]
        for it in items[:20]:
            lines.append(f"• {it.title[:55]}")
        lines.append("</blockquote>")
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    lines = ["<blockquote>📂 <b>Collections</b>\n"]
    for c in cols:
        lines.append(f"• <code>{c.id}</code> {c.name}")
    lines.append("\n<code>/colnew Name</code> create\n<code>/coladd ID title|url</code></blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("colnew"))
@check_ban
async def col_new(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("Usage: <code>/colnew My List</code>", parse_mode=ParseMode.HTML)
        return
    c = await db.create_collection(message.from_user.id, parts[1].strip()[:100])
    await message.reply_text(f"<blockquote>✅ Created <b>{c.name}</b> (id <code>{c.id}</code>)</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("coladd"))
@check_ban
async def col_add(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.reply_text("Usage: <code>/coladd 1 https://… or Title</code>", parse_mode=ParseMode.HTML)
        return
    cid = int(parts[1])
    payload = parts[2].strip()
    title = payload[:200]
    url = payload if payload.startswith("http") else None
    await db.add_to_collection(cid, title=title, url=url)
    await message.reply_text("<blockquote>✅ Added to collection.</blockquote>", parse_mode=ParseMode.HTML)
