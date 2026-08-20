#@mediavault
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from core.queue import queue
from telegram.decorators import check_ban


@Client.on_message(filters.private & filters.command("queue"))
@check_ban
async def queue_cmd(client: Client, message: Message):
    jobs = queue.user_jobs(message.from_user.id)
    if not jobs:
        await message.reply_text(
            "<blockquote>📭 <b>Your queue is empty</b>\nPaste a URL to start a download.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = []
    rows = []
    for j in jobs:
        icon = "⏳" if j.status == "queued" else "⬇️"
        lines.append(f"{icon} <code>{j.id}</code> [{j.status}] {j.label[:40]}")
        if j.status in ("queued", "running"):
            rows.append([InlineKeyboardButton(f"🗑 Cancel {j.id}", callback_data=f"qcancel:{j.id}")])
    text = "<blockquote>📋 <b>Your download queue</b>\n\n" + "\n".join(lines) + "</blockquote>"
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows) if rows else None, parse_mode=ParseMode.HTML)
