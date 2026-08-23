#@mediavault
"""
Media Tools Plugin — Trim, Convert, Compress, Split & Tag audio/video using FFmpeg with
concurrency limits, file size guards, execution timeouts, and quota enforcement.
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

# Global Semaphore: max 2 concurrent FFmpeg operations to avoid CPU overload
FFMPEG_SEMAPHORE = asyncio.Semaphore(2)
CONVERT_ALLOWLIST = {"mp3", "mp4", "m4a", "flac", "wav", "ogg", "opus", "mkv", "webm", "mov"}


def _escape(t: str) -> str:
    return html.escape(t or "")


def _check_ffmpeg_installed() -> bool:
    return shutil.which(FFMPEG_PATH) is not None


async def _extract_video_frame(in_filepath: Path, work_dir: Path) -> str | None:
    thumb_path = work_dir / "auto_frame_thumb.jpg"
    try:
        cmd = [
            FFMPEG_PATH, "-y",
            "-ss", "00:00:03",
            "-i", str(in_filepath),
            "-vframes", "1",
            "-q:v", "2",
            str(thumb_path),
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(proc.communicate(), timeout=30)
        if thumb_path.exists() and os.path.getsize(thumb_path) > 0:
            return str(thumb_path)
    except Exception:
        pass
    return None


@Client.on_message(filters.private & filters.command("trim"))
@check_ban
async def trim_cmd(client: Client, message: Message):
    if not _check_ffmpeg_installed():
        await message.reply_text("<blockquote>❌ FFmpeg is not installed on the server. Media tools are offline.</blockquote>", parse_mode=ParseMode.HTML)
        return

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
            f"<blockquote>❌ File too large ({format_size(file_size)}). Max allowed is {MAX_FILE_SIZE_MB}MB.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    allowed, qmsg = await db.check_quota(user.id)
    if not allowed:
        await message.reply_text(f"<blockquote>🚫 Quota: {_escape(qmsg)}</blockquote>", parse_mode=ParseMode.HTML)
        return

    status = await message.reply_text("<blockquote>⏳ <b>Downloading media for trimming…</b></blockquote>", parse_mode=ParseMode.HTML)

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name
    out_filepath = work_dir / f"trimmed_{orig_file_name}"

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text("<blockquote>✂️ <b>Trimming media with FFmpeg…</b></blockquote>", parse_mode=ParseMode.HTML)

        async with FFMPEG_SEMAPHORE:
            cmd = [
                FFMPEG_PATH, "-y",
                "-ss", start_time,
                "-to", end_time,
                "-i", str(in_filepath),
                "-c", "copy",
                str(out_filepath),
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0 or not out_filepath.exists() or os.path.getsize(out_filepath) == 0:
                cmd_reencode = [
                    FFMPEG_PATH, "-y",
                    "-ss", start_time,
                    "-to", end_time,
                    "-i", str(in_filepath),
                    str(out_filepath),
                ]
                proc2 = await asyncio.create_subprocess_exec(*cmd_reencode, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await asyncio.wait_for(proc2.communicate(), timeout=300)
                if proc2.returncode != 0 or not out_filepath.exists() or os.path.getsize(out_filepath) == 0:
                    raise RuntimeError("FFmpeg trim failed")

        out_size = os.path.getsize(out_filepath)
        await db.log_download(user.id, f"trim:{orig_file_name}", orig_file_name, out_size)

        await status.edit_text("<blockquote>📤 <b>Uploading trimmed media…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>✂️ <b>Trimmed Media</b>\n"
            f"⏱ {start_time} ➔ {end_time}\n"
            f"📦 Size: {format_size(out_size)}</blockquote>"
        )

        ext = out_filepath.suffix.lower()
        from telegram.plugins.thumbnails import get_user_thumb
        thumb = get_user_thumb(user.id) or (await _extract_video_frame(out_filepath, work_dir) if ext in (".mp4", ".mkv", ".webm", ".mov") else None)

        if ext in (".mp4", ".mkv", ".webm", ".mov"):
            await client.send_video(message.chat.id, str(out_filepath), caption=caption, thumb=thumb, supports_streaming=True, parse_mode=ParseMode.HTML)
        else:
            await client.send_audio(message.chat.id, str(out_filepath), caption=caption, thumb=thumb, parse_mode=ParseMode.HTML)

        await status.delete()

    except Exception as e:
        logger.exception("Trim command error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Trim Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command("compress"))
@check_ban
async def compress_cmd(client: Client, message: Message):
    if not _check_ffmpeg_installed():
        await message.reply_text("<blockquote>❌ FFmpeg is not installed on the server. Media tools are offline.</blockquote>", parse_mode=ParseMode.HTML)
        return

    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.video or reply.document):
        await message.reply_text(
            "<blockquote>⚡ <b>Video Compressor</b>\n\n"
            "Reply to a video with <code>/compress</code> or <code>/compress heavy</code> / <code>/compress light</code> to reduce file size!</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    crf = "28"
    parts = (message.text or "").split()
    if len(parts) > 1:
        mode = parts[1].lower()
        if mode == "light":
            crf = "23"
        elif mode == "heavy":
            crf = "32"

    media_obj = reply.video or reply.document
    orig_file_name = getattr(media_obj, "file_name", None) or "video.mp4"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>", parse_mode=ParseMode.HTML)
        return

    allowed, qmsg = await db.check_quota(user.id)
    if not allowed:
        await message.reply_text(f"<blockquote>🚫 Quota: {_escape(qmsg)}</blockquote>", parse_mode=ParseMode.HTML)
        return

    status = await message.reply_text("<blockquote>⏳ <b>Downloading video for compression…</b></blockquote>", parse_mode=ParseMode.HTML)

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name
    out_filepath = work_dir / f"compressed_{orig_file_name}"

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text(f"<blockquote>⚡ <b>Compressing video with FFmpeg (CRF {crf})…</b></blockquote>", parse_mode=ParseMode.HTML)

        async with FFMPEG_SEMAPHORE:
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", str(in_filepath),
                "-vcodec", "libx264",
                "-crf", crf,
                "-preset", "faster",
                "-acodec", "aac",
                str(out_filepath),
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0 or not out_filepath.exists() or os.path.getsize(out_filepath) == 0:
            raise RuntimeError("FFmpeg compression failed")

        new_size = os.path.getsize(out_filepath)
        if new_size >= file_size:
            await status.edit_text("<blockquote>⚠️ Compression did not reduce file size. Original kept.</blockquote>", parse_mode=ParseMode.HTML)
            return

        reduction = (1 - (new_size / file_size)) * 100 if file_size else 0
        await db.log_download(user.id, f"compress:{orig_file_name}", orig_file_name, new_size)

        await status.edit_text("<blockquote>📤 <b>Uploading compressed video…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>⚡ <b>Compressed Video</b>\n"
            f"📦 Original: {format_size(file_size)}\n"
            f"📉 New Size: {format_size(new_size)} (-{reduction:.1f}%)</blockquote>"
        )

        from telegram.plugins.thumbnails import get_user_thumb
        thumb = get_user_thumb(user.id) or await _extract_video_frame(out_filepath, work_dir)

        await client.send_video(
            message.chat.id,
            str(out_filepath),
            caption=caption,
            thumb=thumb,
            supports_streaming=True,
            parse_mode=ParseMode.HTML,
        )

        await status.delete()

    except Exception as e:
        logger.exception("Compress error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Compress Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command("split"))
@check_ban
async def split_cmd(client: Client, message: Message):
    if not _check_ffmpeg_installed():
        await message.reply_text("<blockquote>❌ FFmpeg is not installed on the server. Media tools are offline.</blockquote>", parse_mode=ParseMode.HTML)
        return

    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.video or reply.document):
        await message.reply_text(
            "<blockquote>✂️ <b>Video Splitter</b>\n\n"
            "Reply to a video with <code>/split</code> or <code>/split 10m</code> (max 120m segment duration).</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    seg_sec = 600
    parts = (message.text or "").split()
    if len(parts) > 1:
        val = parts[1].lower().rstrip("ms")
        if val.isdigit():
            seg_sec = min(7200, max(60, int(val) * 60))  # capped at 120m max

    media_obj = reply.video or reply.document
    orig_file_name = getattr(media_obj, "file_name", None) or "video.mp4"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>", parse_mode=ParseMode.HTML)
        return

    allowed, qmsg = await db.check_quota(user.id)
    if not allowed:
        await message.reply_text(f"<blockquote>🚫 Quota: {_escape(qmsg)}</blockquote>", parse_mode=ParseMode.HTML)
        return

    status = await message.reply_text("<blockquote>⏳ <b>Downloading video for splitting…</b></blockquote>", parse_mode=ParseMode.HTML)

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text(f"<blockquote>✂️ <b>Splitting video into {seg_sec // 60}m segments…</b></blockquote>", parse_mode=ParseMode.HTML)

        out_pattern = str(work_dir / f"part_%03d_{orig_file_name}")
        async with FFMPEG_SEMAPHORE:
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", str(in_filepath),
                "-c", "copy",
                "-map", "0",
                "-segment_time", str(seg_sec),
                "-f", "segment",
                "-reset_timestamps", "1",
                out_pattern,
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), timeout=300)

        split_files = sorted(list(work_dir.glob(f"part_*_{orig_file_name}")))
        if proc.returncode != 0 or not split_files:
            raise RuntimeError("FFmpeg split failed")

        await status.edit_text(f"<blockquote>📤 <b>Uploading {len(split_files)} split video parts…</b></blockquote>", parse_mode=ParseMode.HTML)

        from telegram.plugins.thumbnails import get_user_thumb
        thumb = get_user_thumb(user.id)

        for idx, sf in enumerate(split_files, 1):
            sf_size = os.path.getsize(sf)
            await db.log_download(user.id, f"split:{sf.name}", sf.name, sf_size)
            caption = f"<blockquote>✂️ <b>Part {idx}/{len(split_files)}</b>\n📦 Size: {format_size(sf_size)}</blockquote>"
            await client.send_video(
                message.chat.id,
                str(sf),
                caption=caption,
                thumb=thumb,
                supports_streaming=True,
                parse_mode=ParseMode.HTML,
            )

        await status.delete()

    except Exception as e:
        logger.exception("Split error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Split Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command("tag"))
@check_ban
async def tag_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    if not reply or not (reply.audio or reply.document or reply.voice):
        await message.reply_text(
            "<blockquote>🏷 <b>Audio ID3 Tag Editor</b>\n\n"
            "Reply to an audio file with:\n"
            "<code>/tag title | artist | album</code>\n"
            "Example: <code>/tag Song Name | Artist Name | Album Name</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or "|" not in parts[1]:
        await message.reply_text(
            "<blockquote>❌ Format error! Use <code>title | artist | album</code>\n"
            "Example: <code>/tag My Song | DJ X | Hits 2026</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    tag_parts = [p.strip() for p in parts[1].split("|")]
    title = tag_parts[0] if len(tag_parts) > 0 else ""
    artist = tag_parts[1] if len(tag_parts) > 1 else ""
    album = tag_parts[2] if len(tag_parts) > 2 else ""

    media_obj = reply.audio or reply.document or reply.voice
    orig_file_name = getattr(media_obj, "file_name", None) or "audio.mp3"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>", parse_mode=ParseMode.HTML)
        return

    allowed, qmsg = await db.check_quota(user.id)
    if not allowed:
        await message.reply_text(f"<blockquote>🚫 Quota: {_escape(qmsg)}</blockquote>", parse_mode=ParseMode.HTML)
        return

    status = await message.reply_text("<blockquote>⏳ <b>Downloading audio for tagging…</b></blockquote>", parse_mode=ParseMode.HTML)

    work_dir = TMP_TOOLS_DIR / str(user.id) / str(int(time.time()))
    work_dir.mkdir(parents=True, exist_ok=True)
    in_filepath = work_dir / orig_file_name

    try:
        downloaded = await client.download_media(message=reply, file_name=str(in_filepath))
        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError("Download failed")

        await status.edit_text("<blockquote>🏷 <b>Updating ID3 tags with mutagen…</b></blockquote>", parse_mode=ParseMode.HTML)

        import mutagen
        try:
            audio_file = mutagen.File(str(in_filepath), easy=True)
            if audio_file is not None:
                if title:
                    audio_file["title"] = title
                if artist:
                    audio_file["artist"] = artist
                if album:
                    audio_file["album"] = album
                audio_file.save()
        except Exception as ex:
            logger.warning("mutagen tag edit error: %s", ex)

        out_size = os.path.getsize(in_filepath)
        await db.log_download(user.id, f"tag:{orig_file_name}", orig_file_name, out_size)

        await status.edit_text("<blockquote>📤 <b>Uploading tagged audio file…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>🏷 <b>Tagged Audio File</b>\n"
            f"🎵 Title: <code>{_escape(title or '—')}</code>\n"
            f"👤 Artist: <code>{_escape(artist or '—')}</code>\n"
            f"💿 Album: <code>{_escape(album or '—')}</code></blockquote>"
        )

        from telegram.plugins.thumbnails import get_user_thumb
        thumb = get_user_thumb(user.id)

        await client.send_audio(
            message.chat.id,
            str(in_filepath),
            caption=caption,
            title=title or None,
            performer=artist or None,
            thumb=thumb,
            parse_mode=ParseMode.HTML,
        )

        await status.delete()

    except Exception as e:
        logger.exception("Tag command error")
        try:
            await status.edit_text(f"<blockquote>❌ <b>Tag Edit Failed</b>\n<code>{_escape(str(e)[:250])}</code></blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command("convert"))
@check_ban
async def convert_cmd(client: Client, message: Message):
    if not _check_ffmpeg_installed():
        await message.reply_text("<blockquote>❌ FFmpeg is not installed on the server. Media tools are offline.</blockquote>", parse_mode=ParseMode.HTML)
        return

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
    if target_fmt not in CONVERT_ALLOWLIST:
        await message.reply_text(
            f"<blockquote>❌ Unsupported format <code>{_escape(target_fmt)}</code>.\n"
            f"Allowed: <code>{', '.join(sorted(CONVERT_ALLOWLIST))}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    media_obj = reply.video or reply.audio or reply.document or reply.voice
    orig_file_name = getattr(media_obj, "file_name", None) or "media"
    file_size = getattr(media_obj, "file_size", 0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text(f"<blockquote>❌ File too large ({format_size(file_size)})</blockquote>", parse_mode=ParseMode.HTML)
        return

    allowed, qmsg = await db.check_quota(user.id)
    if not allowed:
        await message.reply_text(f"<blockquote>🚫 Quota: {_escape(qmsg)}</blockquote>", parse_mode=ParseMode.HTML)
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

        await status.edit_text(f"<blockquote>🔄 <b>Converting to .{target_fmt} with FFmpeg…</b></blockquote>", parse_mode=ParseMode.HTML)

        async with FFMPEG_SEMAPHORE:
            cmd = [FFMPEG_PATH, "-y", "-i", str(in_filepath), str(out_filepath)]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0 or not out_filepath.exists() or os.path.getsize(out_filepath) == 0:
            raise RuntimeError("FFmpeg conversion failed")

        out_size = os.path.getsize(out_filepath)
        await db.log_download(user.id, f"convert:{orig_file_name}", orig_file_name, out_size)

        await status.edit_text("<blockquote>📤 <b>Uploading converted file…</b></blockquote>", parse_mode=ParseMode.HTML)

        caption = (
            f"<blockquote>🔄 <b>Converted Media</b>\n"
            f"📄 Format: <code>.{target_fmt}</code>\n"
            f"📦 Size: {format_size(out_size)}</blockquote>"
        )

        from telegram.plugins.thumbnails import get_user_thumb
        thumb = get_user_thumb(user.id) or (await _extract_video_frame(out_filepath, work_dir) if target_fmt in ("mp4", "mkv", "webm", "mov") else None)

        if target_fmt in ("mp3", "m4a", "flac", "wav", "ogg", "opus"):
            await client.send_audio(message.chat.id, str(out_filepath), caption=caption, thumb=thumb, parse_mode=ParseMode.HTML)
        elif target_fmt in ("mp4", "mkv", "webm", "mov"):
            await client.send_video(message.chat.id, str(out_filepath), caption=caption, thumb=thumb, supports_streaming=True, parse_mode=ParseMode.HTML)
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
