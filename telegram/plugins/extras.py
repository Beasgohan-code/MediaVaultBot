#@mediavault
"""Extra QoL: /status, /cancelall, multi-link tip, cleaner captions helpers."""
from __future__ import annotations

import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import YTDLP_ENABLED, OWNER_ID, INSTANCE_ID
from core.database import db
from core.emoji import ce, ok, fire
from core.queue import queue
from core.ytdlp import TMP_DIR
from telegram.decorators import check_ban


_BOT_START = time.time()


@Client.on_message(filters.private & filters.command("status"))
@check_ban
async def status_cmd(client: Client, message: Message):
    up = int(time.time() - _BOT_START)
    h, rem = divmod(up, 3600)
    m, s = divmod(rem, 60)
    q = queue.user_jobs(message.from_user.id) if hasattr(queue, "user_jobs") else []
    stars = await db.get_stars(message.from_user.id)
    prem = await db.get_premium(message.from_user.id)
    disk = "?"
    try:
        import shutil
        free = shutil.disk_usage("/").free / (1024**3)
        disk = f"{free:.1f} GB free"
    except Exception:
        pass
    await message.reply_text(
        f"<blockquote>{fire()} <b>Status</b>\n"
        f"⏱ Uptime: <code>{h}h {m}m {s}s</code>\n"
        f"🆔 Instance: <code>{INSTANCE_ID}</code>\n"
        f"📥 yt-dlp: <code>{'on' if YTDLP_ENABLED else 'off'}</code>\n"
        f"📋 Your queue: <code>{len(q)}</code>\n"
        f"⭐ Stars: <code>{stars}</code> · Premium: <code>{'yes' if prem.get('active') else 'no'}</code>\n"
        f"💾 {disk}</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("cancelall"))
@check_ban
async def cancel_all_cmd(client: Client, message: Message):
    jobs = queue.user_jobs(message.from_user.id) if hasattr(queue, "user_jobs") else []
    n = 0
    for j in list(jobs):
        try:
            if hasattr(queue, "cancel"):
                queue.cancel(j.id)
                n += 1
            elif hasattr(j, "cancel"):
                j.cancel()
                n += 1
        except Exception:
            pass
    await message.reply_text(
        f"<blockquote>{ok()} Cancelled <code>{n}</code> job(s).</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("clean"))
@check_ban
async def clean_cmd(client: Client, message: Message):
    """Delete user's temp download files."""
    removed = 0
    roots = [TMP_DIR / str(message.from_user.id), Path("/tmp/mediavault_ytdlp") / str(message.from_user.id)]
    if message.from_user.id == OWNER_ID:
        roots.append(TMP_DIR)
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
    await message.reply_text(
        f"<blockquote>{ok()} Cleaned <code>{removed}</code> temp file(s).</blockquote>",
        parse_mode=ParseMode.HTML,
    )
