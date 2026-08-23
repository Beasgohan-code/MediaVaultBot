#@mediavault
"""
Media Tools Plugin — Trim & Convert audio/video using ffmpeg
Usage:
  Reply to a media message with `/trim 00:00:10 00:00:30`
  Reply to a media message with `/convert mp3` or `/convert mp4`
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import shutil
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import FFMPEG_PATH, MAX_FILE_SIZE_MB
from core.database import db
from core.utils import format_size, progress_bar
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

TMP_TOOLS_DIR = Path("/tmp/mediavault_tools")
TMP_TOOLS_DIR.mkdir(parents=True, exist_ok=True)


def _escape(t: str) -> str:
    return html.escape(t or "")


@Client.on_message(filters.private & filters.command("trim"))
@check_ban
async def trim_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.video or reply.audio or reply.document or reply.voice):
        await message.reply_text(
            "<blockquote>✂️ <b>Media Trimmer</b>\n\n"
            "Reply to a video or audio message with:\n"
            "<code>/trim start_time end_time</code>\n"
            "Example: <code>/trim 00:00:10 00:00:30</code> or <code>/trim 10 30</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "<blockquote>❌ Please specify both start time and end time!\n"
            "Example: <code>/trim 00:00:10 00:00:30</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    start_time, end_time = parts[1].strip(), parts[2].strip()

    media_obj = reply.video or reply.audio or reply.document or reply.voice
    orig_file_name = getattr(media_obj, "file_name", None) or "media.mp4"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(
            f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text(
        f"<blockquote>⏳ <b>Downloading media for trimming…</b></blockquote>",
        parse_mode=ParseMode.HTML,
    )

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name
    out_filepath = work_dir / f"trimmed_{orig_file_name}"

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text("<blockquote>✂️ <b>Trimming media with ffmpeg…</b></blockquote>", parse_mode=ParseMode.HTML)

        cmd = [
            FFMPEG_PATH, "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", str(in_filepath),
            "-c", "copy",
            str(out_filepath),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not out_filepath.exists():
            # Fallback without -c copy (re-encode)
            cmd_reencode = [
                FFMPEG_PATH, "-y",
                "-ss", start_time,
                "-to", end_time,
                "-i", str(in_filepath),
                str(out_filepath),
            ]
            proc2 = await asyncio.create_subprocess_exec(
                *cmd_reencode, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr2 = await proc2.communicate()
            if proc2.returncode != 0 or not out_filepath.exists():
                raise RuntimeError(f"FFmpeg trim error: {stderr2.decode()[:150]}")

        await status.edit_text("<blockquote>📤 <b>Uploading trimmed media…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>✂️ <b>Trimmed Media</b>\n"
            f"⏱ {start_time} ➔ {end_time}\n"
            f"📦 Size: {format_size(os.path.getsize(out_filepath))}</blockquote>"
        )

        ext = out_filepath.suffix.lower()
        if ext in (".mp4", ".mkv", ".webm", ".mov"):
            await client.send_video(message.chat.id, str(out_filepath), caption=caption, parse_mode=ParseMode.HTML)
        else:
            await client.send_audio(message.chat.id, str(out_filepath), caption=caption, parse_mode=ParseMode.HTML)

        await status.delete()

    except Exception as e:
        logger.exception("Trim command error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Trim Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command("convert"))
@check_ban
async def convert_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.video or reply.audio or reply.document or reply.voice):
        await message.reply_text(
            "<blockquote>🔄 <b>Media Format Converter</b>\n\n"
            "Reply to a media message with:\n"
            "<code>/convert target_format</code>\n"
            "Example: <code>/convert mp3</code> or <code>/convert mp4</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>❌ Please specify target format (e.g. <code>mp3</code>, <code>mp4</code>, <code>m4a</code>, <code>mkv</code>)</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_fmt = parts[1].strip().lower().lstrip(".")

    media_obj = reply.video or reply.audio or reply.document or reply.voice
    orig_file_name = getattr(media_obj, "file_name", None) or "media"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(
            f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text("<blockquote>⏳ <b>Downloading media for conversion…</b></blockquote>", parse_mode=ParseMode.HTML)

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name
    out_stem = Path(orig_file_name).stem
    out_filepath = work_dir / f"{out_stem}.{target_fmt}"

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text(f"<blockquote>🔄 <b>Converting to .{target_fmt} with ffmpeg…</b></blockquote>", parse_mode=ParseMode.HTML)

        cmd = [FFMPEG_PATH, "-y", "-i", str(in_filepath), str(out_filepath)]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not out_filepath.exists():
            raise RuntimeError(f"FFmpeg conversion error: {stderr.decode()[:150]}")

        await status.edit_text("<blockquote>📤 <b>Uploading converted file…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>🔄 <b>Converted Media</b>\n"
            f"📄 Format: <code>.{target_fmt}</code>\n"
            f"📦 Size: {format_size(os.path.getsize(out_filepath))}</blockquote>"
        )

        if target_fmt in ("mp3", "m4a", "flac", "wav", "ogg", "opus"):
            await client.send_audio(message.chat.id, str(out_filepath), caption=caption, parse_mode=ParseMode.HTML)
        elif target_fmt in ("mp4", "mkv", "webm", "mov"):
            await client.send_video(message.chat.id, str(out_filepath), caption=caption, parse_mode=ParseMode.HTML)
        else:
            await client.send_document(message.chat.id, str(out_filepath), caption=caption, parse_mode=ParseMode.HTML)

        await status.delete()

    except Exception as e:
        logger.exception("Convert command error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Conversion Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
