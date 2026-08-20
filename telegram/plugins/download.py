#@mediavault
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from config import CAPTION_TEMPLATE, PROGRESS_TEMPLATE, AUTO_DELETE_SECONDS, MAX_FILE_SIZE_MB
from core.database import db
from core.drive import drive
from core.utils import format_size, ProgressTracker
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"
TMP_DIR = Path(tempfile.gettempdir()) / "mediavault"
TMP_DIR.mkdir(exist_ok=True)


@Client.on_callback_query(filters.regex(r"^file:(.+)$"))
@check_ban
async def file_cb(client: Client, query: CallbackQuery):
    file_id = query.data.split(":", 1)[1]
    await query.answer("Preparing…")
    meta = await drive.get_file(file_id)
    if not meta:
        await query.message.reply_text("❌ File not found or inaccessible.")
        return

    if meta.get("mimeType") == FOLDER_MIME:
        # redirect to browse
        from telegram.plugins.browse import _send_folder
        await _send_folder(client, query, file_id, edit=True)
        return

    name = meta.get("name", "file")
    size = int(meta.get("size") or 0)
    mime = meta.get("mimeType") or "application/octet-stream"

    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await query.message.reply_text(
            f"❌ File too large ({format_size(size)}). Limit is {MAX_FILE_SIZE_MB} MB."
        )
        return

    # Action buttons
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Send to chat", callback_data=f"send:{file_id}"),
            InlineKeyboardButton("⭐ Favorite", callback_data=f"favadd:{file_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="browse:root")],
    ])
    path = await drive.get_path(file_id)
    caption = CAPTION_TEMPLATE.format(
        name=name,
        size=format_size(size),
        path=path,
    )
    await query.message.reply_text(caption, reply_markup=kb, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^send:(.+)$"))
@check_ban
async def send_cb(client: Client, query: CallbackQuery):
    file_id = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    await query.answer("Downloading from Drive…")

    meta = await drive.get_file(file_id)
    if not meta:
        await query.message.reply_text("❌ File not found.")
        return

    name = meta.get("name", "file")
    size = int(meta.get("size") or 0)
    mime = meta.get("mimeType") or ""

    status = await query.message.reply_text(
        f"⬇️ Downloading <b>{name}</b>…", parse_mode=ParseMode.HTML
    )

    dest = TMP_DIR / f"{user_id}_{file_id}_{name}"
    tracker = ProgressTracker(total=size)

    # Simple progress (Drive client progress_callback is sync; we update periodically)
    async def progress_task():
        while dest.exists() is False or tracker.current < size:
            if tracker.should_update():
                try:
                    text = tracker.render(name, PROGRESS_TEMPLATE)
                    await status.edit_text(text, parse_mode=ParseMode.HTML)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass
            await asyncio.sleep(1.5)

    prog = asyncio.create_task(progress_task())

    try:
        def sync_progress(cur, tot):
            tracker.update(cur, tot)

        path = await drive.download_file(file_id, str(dest), progress_callback=sync_progress)
        prog.cancel()
        if not path or not dest.exists():
            await status.edit_text("❌ Download failed.")
            return

        await status.edit_text(f"⬆️ Uploading to Telegram…\n<code>{name}</code>", parse_mode=ParseMode.HTML)

        caption = CAPTION_TEMPLATE.format(
            name=name,
            size=format_size(size),
            path=await drive.get_path(file_id),
        )

        # Choose send method
        if mime.startswith("video/"):
            msg = await client.send_video(
                query.message.chat.id,
                str(dest),
                caption=caption,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            )
        elif mime.startswith("audio/"):
            msg = await client.send_audio(
                query.message.chat.id,
                str(dest),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        elif mime.startswith("image/"):
            msg = await client.send_photo(
                query.message.chat.id,
                str(dest),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            msg = await client.send_document(
                query.message.chat.id,
                str(dest),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        await status.delete()
        await db.log_download(user_id, file_id, name, size)

        # Auto-delete
        secs = await db.get_setting("auto_delete_seconds", AUTO_DELETE_SECONDS)
        if secs and int(secs) > 0:
            async def _autodel():
                await asyncio.sleep(int(secs))
                try:
                    await msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_autodel())

    except Exception as e:
        logger.exception("send failed")
        try:
            prog.cancel()
        except Exception:
            pass
        await status.edit_text(f"❌ Error: <code>{e}</code>", parse_mode=ParseMode.HTML)
    finally:
        try:
            if dest.exists():
                dest.unlink()
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^favadd:(.+)$"))
@check_ban
async def fav_add(client: Client, query: CallbackQuery):
    file_id = query.data.split(":", 1)[1]
    meta = await drive.get_file(file_id)
    if not meta:
        await query.answer("File not found", show_alert=True)
        return
    await db.add_favorite(
        query.from_user.id,
        file_id,
        meta.get("name", "file"),
        meta.get("mimeType"),
        int(meta.get("size") or 0),
    )
    await query.answer("⭐ Added to favorites!", show_alert=True)


@Client.on_message(filters.private & filters.command("favs"))
@check_ban
async def favs_cmd(client: Client, message):
    favs = await db.list_favorites(message.from_user.id)
    if not favs:
        await message.reply_text("No favorites yet. Use ⭐ on any file.")
        return
    rows = []
    for f in favs[:30]:
        rows.append([
            InlineKeyboardButton(
                f"⭐ {f.name[:40]}", callback_data=f"file:{f.file_id}"
            )
        ])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    await message.reply_text(
        f"⭐ <b>Your Favorites</b> ({len(favs)})",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.HTML,
    )
