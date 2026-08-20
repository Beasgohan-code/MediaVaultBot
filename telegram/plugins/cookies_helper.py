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
≡ <b>Cookies helper</b>

yt-dlp uses cookies so age-restricted / logged-in public content can be fetched <b>using credentials you already have</b>.

<b>Current config</b>
• File: {status_file}
• Browser: {status_browser}

Priority: file &gt; browser.

─── <b>How to set</b> ───

<b>1. cookies.txt (works everywhere including Docker)</b>
1. Install browser extension “Get cookies.txt LOCALLY” (or similar)
2. Export cookies while logged into YouTube / site
3. Save as <code>cookies.txt</code> next to the bot
4. Set in .env:
<code>YTDLP_COOKIES_FILE=cookies.txt</code>
5. Restart bot

<b>2. cookies-from-browser (bare metal / VPS with browser)</b>
In .env:
<code>YTDLP_COOKIES_FROM_BROWSER=chrome</code>
or
<code>YTDLP_COOKIES_FROM_BROWSER=firefox:default-release</code>
Supported: chrome, chromium, firefox, edge, opera, brave, safari…

⚠️ Cookies let the bot access what <b>your</b> browser session can access.  
Still your own risk — see /tos.
"""
    await message.reply_text(text, parse_mode=ParseMode.HTML)
