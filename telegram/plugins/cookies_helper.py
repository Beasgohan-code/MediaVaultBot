#@mediavault
"""
Cookies helper — shows current cookie config and how to set it.
Admin/owner can check status; users get instructions.
"""
from __future__ import annotations

import os
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import (
    YTDLP_COOKIES_FILE, YTDLP_COOKIES_FROM_BROWSER,
    OWNER_ID,
)
from telegram.decorators import check_ban, admin_only


@Client.on_message(filters.private & filters.command("cookies"))
@check_ban
async def cookies_cmd(client: Client, message: Message):
    file_ok = bool(YTDLP_COOKIES_FILE and os.path.exists(YTDLP_COOKIES_FILE))

    status_file = f"✅ <code>{YTDLP_COOKIES_FILE}</code>" if file_ok else ("❌ missing" if YTDLP_COOKIES_FILE else "— not set")

    text = f"""\
<blockquote>🍪 <b>Cookies Helper (cookies.txt File Only)</b>\n
To download age-restricted, NSFW, or logged-in public content, provide a <code>cookies.txt</code> file.

<b>Current Status</b>
• 📁 Cookies File: {status_file}</blockquote>

<blockquote><b>How to setup cookies.txt</b>
1. Install browser extension "Get cookies.txt LOCALLY".
2. Log into YouTube or desired site in your browser and export cookies.
3. Save the exported file as <code>cookies.txt</code> next to the bot configuration.
4. Set <code>YTDLP_COOKIES_FILE=cookies.txt</code> in your <code>.env</code> file.</blockquote>
"""
    await message.reply_text(text, parse_mode=ParseMode.HTML)


VALID_BROWSERS = {"chrome", "firefox", "edge", "brave", "opera", "safari", "vivaldi", "none", "off"}


@Client.on_message(filters.private & filters.command("setbrowser"))
@check_ban
@admin_only
async def set_browser_cmd(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/setbrowser chrome</code>\n"
            f"Supported: <code>{', '.join(sorted(VALID_BROWSERS))}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    browser_name = parts[1].strip().lower()
    if browser_name not in VALID_BROWSERS:
        await message.reply_text(
            f"<blockquote>❌ Invalid browser <code>{browser_name}</code>!\n"
            f"Supported: <code>{', '.join(sorted(VALID_BROWSERS))}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    from core.database import db
    new_val = "" if browser_name in ("none", "off") else browser_name
    await db.set_setting(f"user_browser_{message.from_user.id}", new_val)
    import config
    config.YTDLP_COOKIES_FROM_BROWSER = new_val
    desc = "disabled" if not new_val else new_val
    await message.reply_text(
        f"<blockquote>✅ Browser cookies source {desc}.</blockquote>",
        parse_mode=ParseMode.HTML,
    )
