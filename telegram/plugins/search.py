#@mediavault
from __future__ import annotations

import logging
from typing import List, Dict

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from core.database import db
from core.drive import drive
from core.state import search_state
from core.utils import format_size
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"


@Client.on_message(filters.private & filters.command("search"))
@check_ban
async def search_cmd(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("Usage: <code>/search attack on titan</code>", parse_mode=ParseMode.HTML)
        return
    query = parts[1].strip()
    await do_search(client, message, query)


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help", "browse", "search", "favs", "stats", "ping", "autodel", "ban", "unban", "admins"]))
@check_ban
async def text_search(client: Client, message: Message):
    # Treat plain text as search
    query = message.text.strip()
    if len(query) < 2:
        return
    await do_search(client, message, query)


async def do_search(client: Client, message: Message, query: str):
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    search_state[message.from_user.id] = query
    status = await message.reply_text(f"🔍 Searching for <b>{query}</b>…", parse_mode=ParseMode.HTML)
    try:
        files = await drive.search(query, page_size=25)
    except Exception as e:
        await status.edit_text(f"❌ Search failed: <code>{e}</code>", parse_mode=ParseMode.HTML)
        return

    if not files:
        await status.edit_text(f"No results for <b>{query}</b>", parse_mode=ParseMode.HTML)
        return

    rows = []
    for f in files:
        name = f.get("name", "?")[:42]
        fid = f["id"]
        icon = "📁" if f.get("mimeType") == FOLDER_MIME else "📄"
        size = format_size(int(f["size"])) if f.get("size") else ""
        label = f"{icon} {name}" + (f" ({size})" if size else "")
        rows.append([InlineKeyboardButton(label, callback_data=f"file:{fid}")])

    rows.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    kb = InlineKeyboardMarkup(rows)
    await status.edit_text(
        f"🔍 <b>Results for</b> <code>{query}</code>\n<code>{len(files)} items</code>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^search:prompt$"))
@check_ban
async def search_prompt(client: Client, query: CallbackQuery):
    await query.answer()
    await query.message.reply_text("Send me the name of the media you want to find 🔍")
