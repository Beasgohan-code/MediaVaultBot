#@mediavault
"""
Rename File Plugin — Allows users to rename files/media sent on Telegram.
Usage: Reply to any media or file with `/rename new_filename.ext` or `/rename new_filename`
"""
from __future__ import annotations

import html
import logging
import os
import shutil
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import MAX_FILE_SIZE_MB
from core.database import db
from core.utils import format_size, progress_bar
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

TMP_RENAME_DIR = Path("/tmp/mediavault_rename")
TMP_RENAME_DIR.mkdir(parents=True, exist_ok=True)


def _escape(t: str) -> str:
    return html.escape(t or "")


@Client.on_message(filters.private & filters.command(["rename", "rn"]))
@check_ban
async def rename_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.media or reply.document or reply.video or reply.audio or reply.photo or reply.voice):
        await message.reply_text(
            "<blockquote>✏️ <b>Rename File</b>\n\n"
            "Please <b>reply to a media or file message</b> with:\n"
            "<code>/rename new_filename.ext</code>\n"
            "or <code>/rename new_filename</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "<blockquote>❌ Please specify a new filename!\n"
            "Example: <code>/rename MyVideo.mp4</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    new_name_input = parts[1].strip()

    # Find media details
    media_obj = reply.document or reply.video or reply.audio or reply.photo or reply.voice
    orig_file_name = getattr(media_obj, "file_name", None) or "file"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(
            f"<blockquote>❌ File is too large ({format_size(file_size)}). Max allowed is {MAX_FILE_SIZE_MB}MB.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Preserve extension if not provided
    orig_ext = Path(orig_file_name).suffix
    if not Path(new_name_input).suffix and orig_ext:
        final_filename = new_name_input + orig_ext
    else:
        final_filename = new_name_input

    status = await message.reply_text(
        f"<blockquote>⏳ <b>Downloading file for renaming…</b>\n"
        f"📄 Target: <code>{_escape(final_filename)}</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )

    download_dir = TMP_RENAME_DIR / str(user.id) / str(int(time.time()))
    download_dir.mkdir(parents=True, exist_ok=True)
    temp_filepath = download_dir / orig_file_name

    last_edit = [0.0]

    async def progress_cb(current, total):
        now = time.monotonic()
        if now - last_edit[0] < 2.5:
            return
        last_edit[0] = now
        pct = (current / total * 100) if total else 0
        bar = progress_bar(pct)
        try:
            await status.edit_text(
                f"<blockquote>⏳ <b>Downloading…</b>\n"
                f"<code>[{bar}] {pct:.1f}%</code>\n"
                f"📦 {format_size(current)} / {format_size(total)}</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    target_filepath = download_dir / final_filename

    try:
        downloaded_path = await client.download_media(
            message=reply,
            file_name=str(temp_filepath),
            progress=progress_cb,
        )

        if not downloaded_path or not os.path.exists(downloaded_path):
            raise RuntimeError("Failed to download media file")

        # Rename local file safely across filesystems
        shutil.move(downloaded_path, target_filepath)

        try:
            await status.edit_text(
                f"<blockquote>📤 <b>Uploading renamed file…</b>\n"
                f"📄 <code>{_escape(final_filename)}</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        caption = (
            f"<blockquote>✏️ <b>Renamed File</b>\n"
            f"📄 Name: <code>{_escape(final_filename)}</code>\n"
            f"📦 Size: {format_size(os.path.getsize(target_filepath))}</blockquote>"
        )

        ext = target_filepath.suffix.lower()
        if ext in (".mp4", ".mkv", ".webm", ".mov"):
            await client.send_video(
                chat_id=message.chat.id,
                video=str(target_filepath),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        elif ext in (".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav"):
            await client.send_audio(
                chat_id=message.chat.id,
                audio=str(target_filepath),
                caption=caption,
                title=target_filepath.stem,
                parse_mode=ParseMode.HTML,
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=str(target_filepath),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        try:
            await status.delete()
        except Exception:
            pass

    except Exception as e:
        logger.exception("Rename error")
        try:
            await status.edit_text(
                f"<blockquote>❌ <b>Rename Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    finally:
        if target_filepath.exists():
            try:
                target_filepath.unlink()
            except Exception:
                pass
        if download_dir.exists():
            try:
                import shutil
                shutil.rmtree(download_dir, ignore_errors=True)
            except Exception:
                pass
