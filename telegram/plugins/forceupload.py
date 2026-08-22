#@mediavault
"""Force re-upload a file left in the temp download directory."""
from __future__ import annotations

import os
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import MAX_FILE_SIZE_MB, OWNER_ID
from core.emoji import ce, ok
from core.ytdlp import TMP_DIR
from telegram.decorators import check_ban


def _all_temp_files():
    files = []
    roots = [TMP_DIR, Path("/tmp/mediavault_ytdlp"), Path("downloads")]
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                files.append(f)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


@Client.on_message(filters.private & filters.command("listfiles"))
@check_ban
async def list_files_cmd(client: Client, message: Message):
    files = _all_temp_files()[:20]
    if not files:
        await message.reply_text(
            f"<blockquote>{ce('ghost', '👻')} No temp files.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = [f"<blockquote>{ce('bookmark', '🔖')} <b>Temp files</b>\n"]
    for f in files:
        mb = f.stat().st_size / (1024 * 1024)
        lines.append(f"• <code>{f.name}</code> — {mb:.1f} MB")
    lines.append("\n<code>/forceupload filename</code></blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("forceupload"))
@check_ban
async def forceupload_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            f"<blockquote>Usage: <code>/forceupload name.mp4</code>\n"
            f"See <code>/listfiles</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    name = parts[1].strip()
    # security: no path traversal
    if "/" in name or "\\" in name or ".." in name:
        await message.reply_text("❌ Invalid name")
        return

    files = _all_temp_files()
    filepath = None
    for f in files:
        if f.name == name or name in f.name:
            # only owner or file under their user_id folder
            if message.from_user.id != OWNER_ID:
                if str(message.from_user.id) not in str(f):
                    continue
            filepath = f
            break
    if not filepath or not filepath.exists():
        await message.reply_text(
            f"<blockquote>File not found: <code>{name}</code>\n/listfiles</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    size = filepath.stat().st_size
    mb = size / (1024 * 1024)
    if mb > MAX_FILE_SIZE_MB:
        await message.reply_text(f"❌ Too big: {mb:.1f} MB (max {MAX_FILE_SIZE_MB})")
        return

    status = await message.reply_text(
        f"<blockquote>📤 Force uploading…\n📦 <code>{mb:.1f} MB</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )
    ext = filepath.suffix.lower()
    cap = f"<blockquote>{ok()} Force uploaded\n<code>{filepath.name}</code>\n📦 {mb:.1f} MB</blockquote>"
    try:
        if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
            await client.send_video(
                message.chat.id, str(filepath), caption=cap,
                supports_streaming=True, parse_mode=ParseMode.HTML,
            )
        elif ext in (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".opus"):
            await client.send_audio(
                message.chat.id, str(filepath), caption=cap, parse_mode=ParseMode.HTML,
            )
        else:
            await client.send_document(
                message.chat.id, str(filepath), caption=cap, parse_mode=ParseMode.HTML,
            )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        await status.edit_text(
            f"<blockquote>❌ Upload failed\n<code>{str(e)[:200]}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )


@Client.on_message(filters.private & filters.command("path"))
@check_ban
async def path_cmd(client: Client, message: Message):
    await message.reply_text(
        f"<blockquote>📂 <code>{TMP_DIR}</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )
