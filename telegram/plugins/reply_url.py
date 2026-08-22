#@mediavault
"""Reply to a message that contains a URL → open quality picker."""
from __future__ import annotations

import re
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.database import db
from core.emoji import ce
from core.ytdlp import is_supported_url
from telegram.decorators import check_ban

URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)",
    re.I,
)


@Client.on_message(filters.private & filters.reply & filters.text & ~filters.command(["start", "help", "tos"]))
@check_ban
async def reply_url_handler(client: Client, message: Message):
    src = message.reply_to_message
    if not src:
        return
    text = (src.text or src.caption or "")
    urls = URL_REGEX.findall(text)
    if not urls:
        return
    url = urls[0].strip()
    if not is_supported_url(url):
        return

    # lazy imports to avoid circular import at load time
    from telegram.plugins.url_download import (
        _cache_url, preset_keyboard, has_accepted_tos, send_tos,
    )

    if not await has_accepted_tos(message.from_user.id):
        await send_tos(client, message)
        return

    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    allowed, qmsg = await db.check_quota(message.from_user.id)
    if not allowed:
        await message.reply_text(
            f"<blockquote>{ce('block', '🚫')} <b>Quota</b>\n{qmsg}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    key = _cache_url(url)
    preferred = await db.get_preferred_quality(message.from_user.id)
    await message.reply_text(
        f"<blockquote>{ce('fire', '🔥')} <b>Reply → download</b>\n"
        f"<code>{url[:100]}</code>\n"
        f"📊 <code>{qmsg}</code>\n"
        f"Pick quality:</blockquote>",
        reply_markup=preset_keyboard(key, preferred),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
