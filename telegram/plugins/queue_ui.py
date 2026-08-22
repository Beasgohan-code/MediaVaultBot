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


@Client.on_callback_query(filters.regex(r"^qcancel:(.+)$"))
@check_ban
async def queue_cancel_cb(client: Client, query):
    from pyrogram.enums import ParseMode
    jid = query.data.split(":", 1)[1]
    ok = False
    try:
        if hasattr(queue, "cancel"):
            ok = queue.cancel(jid)
    except Exception:
        pass
    await query.answer("Cancelled" if ok else "Not found")
    try:
        await query.message.edit_text(
            f"<blockquote>{'🗑 Cancelled' if ok else 'Job gone'}: <code>{jid}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
