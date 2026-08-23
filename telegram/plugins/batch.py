#@mediavault
"""
Batch Downloader Plugin — Download multiple links or URLs from a .txt file.
Usage:
  `/batch url1 url2 url3`
  Reply to a .txt file with `/batch`
"""
from __future__ import annotations

import html
import logging
import os
import re
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.database import db
from telegram.decorators import check_ban
from telegram.plugins.url_download import URL_REGEX, start_download_flow, _normalize_url

logger = logging.getLogger(__name__)


def _escape(t: str) -> str:
    return html.escape(t or "")


@Client.on_message(filters.private & filters.command("batch"))
@check_ban
async def batch_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    urls = []

    # Check if replying to a document (.txt)
    reply = message.reply_to_message
    if reply and reply.document and (reply.document.file_name or "").endswith(".txt"):
        if getattr(reply.document, "file_size", 0) > 1 * 1024 * 1024:
            await message.reply_text("<blockquote>❌ Batch file too large! Max allowed is 1MB.</blockquote>", parse_mode=ParseMode.HTML)
            return

        status = await message.reply_text("<blockquote>⏳ Reading URLs from batch file…</blockquote>", parse_mode=ParseMode.HTML)
        downloaded = None
        try:
            downloaded = await client.download_media(message=reply)
            with open(downloaded, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            found = URL_REGEX.findall(content)
            urls = [_normalize_url(m[0] if isinstance(m, tuple) else m) for m in found]
        except Exception as e:
            await status.edit_text(f"<blockquote>❌ Error reading batch file: <code>{_escape(str(e))}</code></blockquote>", parse_mode=ParseMode.HTML)
            return
        finally:
            if downloaded and os.path.exists(downloaded):
                os.unlink(downloaded)
        await status.delete()

    # Otherwise parse URLs from text command
    if not urls:
        text = message.text or ""
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            found = URL_REGEX.findall(parts[1])
            urls = [_normalize_url(m[0] if isinstance(m, tuple) else m) for m in found]

    if not urls:
        await message.reply_text(
            "<blockquote>📦 <b>Batch Downloader</b>\n\n"
            "Usage:\n"
            "<code>/batch url1 url2 url3</code>\n"
            "Or reply to a <code>.txt</code> file containing URLs with <code>/batch</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cap batch size to 10
    urls = urls[:10]
    await message.reply_text(
        f"<blockquote>📦 <b>Starting Batch Download</b>\n"
        f"Processing <code>{len(urls)}</code> URLs sequentially…</blockquote>",
        parse_mode=ParseMode.HTML,
    )

    for i, url in enumerate(urls, 1):
        success = False
        for attempt in range(2):
            try:
                await start_download_flow(client, message, url)
                success = True
                break
            except Exception as e:
                logger.warning("Batch item %s attempt %d failed: %s", url, attempt + 1, e)
                if attempt == 0:
                    import asyncio
                    await asyncio.sleep(10)
        if not success:
            await message.reply_text(
                f"<blockquote>❌ Batch item {i}/{len(urls)} failed after retries: <code>{_escape(url[:80])}</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )
