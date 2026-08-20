#@mediavault
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.database import db
from core.ytdlp import is_supported_url
from telegram.decorators import check_ban

# /schedule <hours> <url>   or  /schedule 2h <url>
@Client.on_message(filters.private & filters.command("schedule"))
@check_ban
async def schedule_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply_text(
            "<blockquote>⏰ <b>Schedule download</b>\n\n"
            "Usage:\n<code>/schedule 2h https://…</code>\n"
            "<code>/schedule 30m https://…</code>\n"
            "<code>/schedule 1d https://…</code>\n\n"
            "/schedules — list yours</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    when, url = parts[1], parts[2].strip()
    if not is_supported_url(url):
        await message.reply_text("❌ Unsupported URL")
        return
    m = re.match(r"^(\d+)([mhd])$", when.lower())
    if not m:
        await message.reply_text("Time must be like <code>30m</code>, <code>2h</code>, <code>1d</code>", parse_mode=ParseMode.HTML)
        return
    n, unit = int(m.group(1)), m.group(2)
    delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
    run_at = datetime.now(timezone.utc) + delta
    quality = await db.get_preferred_quality(message.from_user.id) or "best"
    job = await db.schedule_download(message.from_user.id, url, quality, run_at)
    await message.reply_text(
        f"<blockquote>⏰ <b>Scheduled</b>\n"
        f"ID: <code>{job.id}</code>\n"
        f"When: <code>{run_at.strftime('%Y-%m-%d %H:%M')} UTC</code>\n"
        f"Quality: <code>{quality}</code>\n"
        f"URL: <code>{url[:60]}</code></blockquote>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.private & filters.command("schedules"))
@check_ban
async def schedules_list(client: Client, message: Message):
    jobs = await db.user_schedules(message.from_user.id)
    if not jobs:
        await message.reply_text("<blockquote>No scheduled jobs.</blockquote>", parse_mode=ParseMode.HTML)
        return
    lines = []
    for j in jobs:
        lines.append(f"• <code>{j.id}</code> [{j.status}] {j.run_at.strftime('%m-%d %H:%M')} — {j.url[:40]}")
    await message.reply_text(
        "<blockquote>⏰ <b>Your schedules</b>\n\n" + "\n".join(lines) + "</blockquote>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
