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
    browser = YTDLP_COOKIES_FROM_BROWSER or "—"

    status_file = f"✅ `{YTDLP_COOKIES_FILE}`" if file_ok else ("❌ missing" if YTDLP_COOKIES_FILE else "— not set")
    status_browser = f"✅ `{browser}`" if YTDLP_COOKIES_FROM_BROWSER else "— not set"

    text = f"""\
<blockquote>🍪 <b>Universal Browser Cookies & Credentials Helper</b>\n
yt-dlp uses cookies so age-restricted, NSFW, or logged-in public content can be downloaded using your browser credentials.

<b>Current Configuration</b>
• 📁 File: {status_file}
• 🌐 Browser: {status_browser}

<b>Priority:</b> File &gt; Browser.</blockquote>

<blockquote><b>Quick Commands</b>
• <code>/setbrowser chrome</code> (or firefox, edge, brave, opera, safari, vivaldi)
• <code>/formats &lt;url&gt;</code> (Inspect raw formats from yt-dlp)</blockquote>

<blockquote><b>How to setup cookies.txt</b>
1. Install browser extension "Get cookies.txt LOCALLY".
2. Export cookies while logged in.
3. Upload or place <code>cookies.txt</code> next to bot config.
4. Set <code>YTDLP_COOKIES_FILE=cookies.txt</code> in .env.</blockquote>
"""
    await message.reply_text(text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("setbrowser"))
@check_ban
@admin_only
async def set_browser_cmd(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/setbrowser chrome</code>\n"
            "Supported: chrome, firefox, edge, brave, opera, safari, vivaldi</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    browser_name = parts[1].strip().lower()
    import config
    config.YTDLP_COOKIES_FROM_BROWSER = browser_name
    await message.reply_text(
        f"<blockquote>✅ Browser cookies source set to <code>{browser_name}</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )
