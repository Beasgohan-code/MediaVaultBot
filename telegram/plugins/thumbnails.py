#@mediavault
"""
Thumbnail Manager Plugin — Save, view, and delete custom thumbnails.
Usage:
  Reply to a photo with `/savethumb` or `/sthumb`
  `/showthumb` or `/vthumb`
  `/delthumb` or `/dthumb`
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.database import db
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

THUMB_DIR = Path("data/thumbs")
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def get_user_thumb(user_id: int) -> str | None:
    path = THUMB_DIR / f"{user_id}.jpg"
    if path.exists():
        return str(path)
    return None


@Client.on_message(filters.private & filters.command(["savethumb", "sthumb"]))
@check_ban
async def savethumb_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username, user.first_name)

    reply = message.reply_to_message
    target_msg = reply if (reply and reply.photo) else (message if message.photo else None)

    if not target_msg or not target_msg.photo:
        await message.reply_text(
            "<blockquote>🖼 <b>Custom Thumbnail Manager</b>\n\n"
            "Please <b>reply to a photo</b> (or send a photo with caption) with <code>/savethumb</code> to save it as your custom thumbnail for all downloads!</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text("<blockquote>⏳ Saving custom thumbnail…</blockquote>", parse_mode=ParseMode.HTML)
    thumb_path = THUMB_DIR / f"{user.id}.jpg"

    try:
        await client.download_media(message=target_msg, file_name=str(thumb_path))
        await status.edit_text(
            "<blockquote>✅ <b>Custom thumbnail saved successfully!</b>\n"
            "This thumbnail will now be applied to all your video and audio downloads.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.exception("Save thumb error")
        await status.edit_text(f"<blockquote>❌ Failed to save thumbnail: <code>{e}</code></blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command(["showthumb", "vthumb"]))
@check_ban
async def showthumb_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    thumb_path = get_user_thumb(user.id)
    if not thumb_path:
        await message.reply_text("<blockquote>🖼 <b>No custom thumbnail set.</b>\nUse <code>/savethumb</code> on a photo.</blockquote>", parse_mode=ParseMode.HTML)
        return

    await client.send_photo(
        chat_id=message.chat.id,
        photo=thumb_path,
        caption="<blockquote>🖼 <b>Your saved custom thumbnail.</b></blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command(["delthumb", "dthumb"]))
@check_ban
async def delthumb_cmd(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    thumb_path = get_user_thumb(user.id)
    if not thumb_path:
        await message.reply_text("<blockquote>🖼 <b>No custom thumbnail to delete.</b></blockquote>", parse_mode=ParseMode.HTML)
        return

    try:
        os.unlink(thumb_path)
        await message.reply_text("<blockquote>✅ <b>Custom thumbnail deleted!</b></blockquote>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ Error deleting thumbnail: <code>{e}</code></blockquote>", parse_mode=ParseMode.HTML)
