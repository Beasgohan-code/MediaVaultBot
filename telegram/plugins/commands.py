#@mediavault
from __future__ import annotations

import logging
import time

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID, START_PIC, AUTO_DELETE_SECONDS, YTDLP_ENABLED, SUPPORT_URL
from core.database import db
from telegram.decorators import check_ban, admin_only, owner_only

logger = logging.getLogger(__name__)

START_TEXT = """
<blockquote>⚡ <b>MediaVault 2026 Edition</b> — Universal Media Suite</blockquote>

Hey {mention} 👋

<blockquote><b>🚀 Next-Gen All-Rounder Capabilities</b>
• <b>Universal Downloader:</b> Paste links for YouTube, Spotify, Instagram, TikTok, Reddit, X, Twitch & 1000+ sites.
• <b>Media Tools:</b> <code>/rename</code>, <code>/trim</code>, <code>/convert</code>, <code>/compress</code>, <code>/split</code>, <code>/tag</code>, <code>/subs</code>, <code>/formats</code>.
• <b>Batch Engine:</b> Sequential multi-link & <code>.txt</code> file batch processing (<code>/batch</code>).
• <b>Custom Thumbnails:</b> Save custom artwork for all your downloads (<code>/savethumb</code>).
• <b>Cookies & Credentials:</b> Dynamic browser cookie manager (<code>/setbrowser</code>).</blockquote>

<blockquote>📜 Please accept <code>/tos</code> before downloading media.</blockquote>
"""

HELP_TEXT = """
<blockquote><b>Help & All-Rounder Command Menu</b></blockquote>

<blockquote>
<b>Downloads & Platforms</b>
Paste any link → quality / format picker
<code>/video</code> <code>/audio</code> <code>/dl</code> <code>/batch</code> <code>/subs</code>
<code>/spotify</code> <code>/instagram</code> <code>/anime</code> <code>/formats</code>
<code>/sites</code> <code>/tos</code> <code>/quota</code> <code>/cookies</code> <code>/queue</code>

<b>Media Editing & Tools</b>
Reply to any media/file with:
<code>/rename new_name.ext</code> (or <code>/rn</code>)
<code>/trim 00:00:10 00:00:30</code>
<code>/convert mp3</code> (or mp4, mkv, flac)
<code>/compress</code> (compress video size)
<code>/split 10m</code> (split video in chunks)
<code>/tag title | artist | album</code> (edit MP3 tags)
<code>/savethumb</code> <code>/showthumb</code> <code>/delthumb</code> (custom thumbnail)

<b>Library & Collections</b>
<code>/search query</code> — Web search
<code>/library</code> · <code>/recent</code> · <code>/export</code>
<code>/collections</code> <code>/watchlater</code> <code>/colnew</code> <code>/coladd</code>

<b>Schedule & System</b>
<code>/schedule 2h URL</code> · <code>/schedules</code>
<code>/stars</code> <code>/buy</code> <code>/premium</code> <code>/settings</code>
<code>/stats</code> <code>/addsites</code> <code>/setbrowser</code>
</blockquote>
"""

@Client.on_message(filters.private & filters.command("start"))
@check_ban
async def start_cmd(client: Client, message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)

    # Deep link: /start dl_<url-encoded>
    payload = ""
    if message.command and len(message.command) > 1:
        payload = message.command[1]
    if payload.startswith("dl_"):
        import base64
        from urllib.parse import unquote
        try:
            raw = payload[3:]
            try:
                url = base64.urlsafe_b64decode(raw + "==").decode()
            except Exception:
                url = unquote(raw)
            if url.startswith("http"):
                await message.reply_text(
                    f"<blockquote>🔗 Deep link — send this URL to download (after /tos)</blockquote>\n<code>{url[:120]}</code>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        except Exception:
            pass
    elif payload.startswith("lib_"):
        await message.reply_text(
            f"<blockquote>📚 Library deep link <code>{payload}</code>\nUse /library to search.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    elif payload.startswith("col_"):
        await message.reply_text(
            f"<blockquote>📂 Collection deep link <code>{payload}</code>\nUse /collections.</blockquote>",
            parse_mode=ParseMode.HTML,
        )

    buttons = [
        [
            InlineKeyboardButton("📋 Queue", callback_data="noop_q"),
            InlineKeyboardButton("⚙️ Settings", callback_data="noop_s"),
        ],
        [
            InlineKeyboardButton("📚 Library", callback_data="noop_l"),
            InlineKeyboardButton("🌐 Supported Sites", callback_data="sites"),
        ],
    ]
    if SUPPORT_URL:
        buttons.append([
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            InlineKeyboardButton("💬 Support", url=SUPPORT_URL),
        ])
    else:
        buttons.append([InlineKeyboardButton("ℹ️ Help", callback_data="help")])
    kb = InlineKeyboardMarkup(buttons)
    text = START_TEXT.format(mention=user.mention)
    if START_PIC:
        try:
            await message.reply_photo(START_PIC, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("help"))
@check_ban
async def help_cmd(client: Client, message: Message):
    await message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^help$"))
@check_ban
async def help_cb(client: Client, query):
    await query.answer()
    await query.answer()
    try:
        await query.message.edit_text(HELP_TEXT, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^sites$"))
@check_ban
async def sites_cb(client: Client, query):
    await query.answer()
    text = (
        "≡ <b>Supported public platforms</b>\n\n"
        "YouTube • Reddit • X/Twitter • TikTok\n"
        "Instagram (public) • Vimeo • SoundCloud\n"
        "Twitch clips • Facebook public + 1000 more via yt-dlp\n\n"
        "Paste any public URL and the bot will handle it."
    )
    await query.answer()
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("ping"))
@check_ban
async def ping_cmd(client: Client, message: Message):
    t0 = time.perf_counter()
    m = await message.reply_text("<blockquote>…</blockquote>", parse_mode=ParseMode.HTML)
    dt = (time.perf_counter() - t0) * 1000
    await m.edit_text(
        f"<blockquote>🏓 <b>Pong</b>\nLatency: <code>{dt:.1f} ms</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("about"))
@check_ban
async def about_cmd(client: Client, message: Message):
    await message.reply_text(
        """<blockquote><b>MediaVault</b> — personal media bot</blockquote>
<blockquote>
• yt-dlp public URLs (YouTube, Reddit, X, …)
• Queue · schedule · collections · TMDB where-to-watch
• Custom emoji · reactions · protect_content
</blockquote>
<blockquote>
Legal personal use only. Accept /tos before downloads.
Deploy: Docker · Railway · Render
</blockquote>""",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("stats"))
@check_ban
@admin_only
async def stats_cmd(client: Client, message: Message):
    users = await db.get_user_count()
    ytdlp = "✅ ON" if YTDLP_ENABLED else "❌ OFF"
    text = f"""\
≡ <b>Stats</b>

👥 Users: <code>{users}</code>
🗄 Database: PostgreSQL
🌐 yt-dlp: {ytdlp}
⏱ Auto-delete: <code>{AUTO_DELETE_SECONDS}s</code>
"""
    await message.reply_text(text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("autodel"))
@check_ban
@admin_only
async def autodel_cmd(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: <code>/autodel 3600</code>", parse_mode=ParseMode.HTML)
        return
    secs = int(parts[1])
    await db.set_setting("auto_delete_seconds", secs)
    await message.reply_text(f"✅ Auto-delete set to <code>{secs}</code>s", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("admins"))
@check_ban
@admin_only
async def admins_cmd(client: Client, message: Message):
    admins = await db.list_admins()
    lines = [f"• <code>{u.id}</code> {u.full_name or u.username or ''}" for u in admins]
    text = "≡ <b>Admins</b>\n\n" + ("\n".join(lines) if lines else "None")
    await message.reply_text(text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command(["ban", "unban"]))
@check_ban
@admin_only
async def ban_unban_cmd(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.reply_text(
            "Usage:\n<code>/ban 123456789 [days] [reason]</code>\n<code>/ban 123456789 7 spam</code>\n<code>/unban 123456789</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    uid = int(parts[1])
    if message.command[0] == "ban":
        days = None
        reason_parts = parts[2:]
        if reason_parts and reason_parts[0].isdigit():
            days = int(reason_parts[0])
            reason_parts = reason_parts[1:]
        reason = " ".join(reason_parts)
        await db.ban_user(uid, reason, days)
        extra = f" for {days}d" if days else " (permanent)"
        await message.reply_text(f"🚫 Banned <code>{uid}</code>{extra}")
    else:
        await db.unban_user(uid)
        await message.reply_text(f"✅ Unbanned <code>{uid}</code>")


@Client.on_callback_query(filters.regex(r"^noop_"))
async def noop_hint(client: Client, query: CallbackQuery):
    hints = {"noop_q": "/queue", "noop_s": "/settings", "noop_l": "/library query"}
    await query.answer(hints.get(query.data, "Use commands"), show_alert=True)


@Client.on_callback_query(filters.regex(r"^close$"))
async def close_cb(client: Client, query: CallbackQuery):
    await query.answer()
    try:
        await query.message.edit_text("<blockquote>Closed.</blockquote>", parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await query.message.delete()
        except Exception:
            pass
