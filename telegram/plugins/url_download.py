#@mediavault
"""
URL download flow — pyrofork-style:
  paste link → extract → quality buttons → download → upload
  /video <url>  /audio <url>  /dl <url>
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import os
import re
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import (
    YTDLP_ENABLED, REQUIRE_TOS_ACCEPT, TOS_TEXT, QUALITY_PRESETS,
    RATE_LIMIT_PER_MIN, PREMIUM_DOMAINS, OWNER_ID, MAX_DURATION_SEC,
    AUTO_DELETE_SECONDS, MAX_FILE_SIZE_MB,
)
from core.database import db
from core.ytdlp import (
    download as ytdlp_download, is_supported_url, extract_info, TMP_DIR,
)
from core.utils import format_size, progress_bar, human_duration
from core.queue import queue
from core.emoji import ce, ok
from core.media import auto_tags
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

# Same spirit as pyrofork — catch any http(s) link in text
URL_REGEX = re.compile(
    r"(https?://[^\s<>\"\'\]\)]+|"
    r"(?:www\.)?(?:youtube\.com|youtu\.be|instagram\.com|tiktok\.com|"
    r"twitter\.com|x\.com|reddit\.com|redd\.it|facebook\.com|fb\.watch|"
    r"vimeo\.com|soundcloud\.com)[^\s<>\"\'\]\)]*)",
    re.IGNORECASE,
)

QUALITIES = [
    ("best", "🏆 Best"),
    ("1080", "🎬 1080p"),
    ("720", "🎬 720p"),
    ("480", "📺 480p"),
    ("360", "📱 360p"),
    ("audio", "🎵 Audio"),
]

_url_cache: dict[str, str] = {}
_jobs: dict[str, dict] = {}


def _cache_url(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    _url_cache[key] = url
    if len(_url_cache) > 400:
        for k in list(_url_cache)[:80]:
            _url_cache.pop(k, None)
    return key


def _get_url(key: str) -> str | None:
    return _url_cache.get(key)


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    while url and url[-1] in ").,}]}>\"'":
        url = url[:-1]
    if url.startswith("www."):
        url = "https://" + url
    url = re.sub(r"[?&](t|s|ref|si|feature)=[^&]+", "", url)
    return url.rstrip("/")



def _escape(t: str) -> str:
    return html.escape(t or "")


async def has_accepted_tos(user_id: int) -> bool:
    if not REQUIRE_TOS_ACCEPT:
        return True
    return bool(await db.get_setting(f"tos_accepted_{user_id}", False))


async def set_tos_accepted(user_id: int) -> None:
    await db.set_setting(f"tos_accepted_{user_id}", True)


async def send_tos(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I Accept — My Risk", callback_data="tos:accept"),
        InlineKeyboardButton("❌ Decline", callback_data="tos:decline"),
    ]])
    await message.reply_text(TOS_TEXT, reply_markup=kb, parse_mode=ParseMode.HTML)


def quality_keyboard(url_key: str, preferred: str | None = None) -> InlineKeyboardMarkup:
    rows, row = [], []
    for value, label in QUALITIES:
        mark = " ✓" if preferred and preferred == value else ""
        row.append(InlineKeyboardButton(f"{label}{mark}", callback_data=f"ydl:{url_key}:{value}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="close")])
    return InlineKeyboardMarkup(rows)


async def _check_premium_domain(user_id: int, url: str) -> bool:
    """Return True if allowed. Env PREMIUM_DOMAINS + DB /setpremium list."""
    low = url.lower()
    if user_id == OWNER_ID:
        return True
    domains = list(PREMIUM_DOMAINS or [])
    try:
        from telegram.plugins.sites_admin import all_premium_domains
        domains = await all_premium_domains()
    except Exception:
        pass
    if not domains:
        return True
    if not any(d in low for d in domains):
        return True
    prem = await db.get_premium(user_id)
    return bool(prem.get("active"))


# ─── TOS ───
@Client.on_callback_query(filters.regex(r"^tos:accept$"))
@check_ban
async def tos_accept(client: Client, query: CallbackQuery):
    await set_tos_accepted(query.from_user.id)
    await query.answer("Accepted")
    try:
        await query.message.edit_text(
            "<blockquote>✅ <b>TOS accepted.</b>\nSend a link to download.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^tos:decline$"))
@check_ban
async def tos_decline(client: Client, query: CallbackQuery):
    await query.answer("Declined", show_alert=True)
    try:
        await query.message.edit_text("❌ Declined. Downloads locked.", parse_mode=ParseMode.HTML)
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("tos"), group=0)
@check_ban
async def tos_cmd(client: Client, message: Message):
    if await has_accepted_tos(message.from_user.id):
        await message.reply_text("<blockquote>✅ Already accepted.</blockquote>", parse_mode=ParseMode.HTML)
    else:
        await send_tos(client, message)


# ─── Core flow (pyrofork-style) ───
async def start_download_flow(
    client: Client,
    message: Message,
    url: str,
    force_audio: bool = False,
):
    if not YTDLP_ENABLED:
        await message.reply_text("yt-dlp is disabled.")
        return

    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        await message.reply_text("User missing")
        return
    await db.ensure_user(user_id, message.from_user.username, message.from_user.first_name)

    if not await has_accepted_tos(user_id):
        await send_tos(client, message)
        return

    url = _normalize_url(url)
    if not re.match(r"^https?://", url, re.I):
        await message.reply_text("<blockquote>❌ Invalid URL</blockquote>", parse_mode=ParseMode.HTML)
        return

    if not await _check_premium_domain(user_id, url):
        await message.reply_text(
            "<blockquote>⭐ <b>Premium required</b> for this domain.\n"
            "/premium or /buy stars</blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Premium", callback_data="plan:7")],
                [InlineKeyboardButton("❌ Cancel", callback_data="close")],
            ]),
        )
        return

    ok_rate, _ = await db.check_rate_limit(user_id, RATE_LIMIT_PER_MIN)
    if not ok_rate:
        await message.reply_text(
            f"<blockquote>⏳ Slow down — max {RATE_LIMIT_PER_MIN}/min</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    allowed, qmsg = await db.check_quota(user_id)
    if not allowed:
        await message.reply_text(
            f"<blockquote>🚫 Quota: {qmsg}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text(
        f"<blockquote>🔎 Extracting info…\n<code>{_escape(url[:80])}</code></blockquote>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

    try:
        info = await extract_info(url)
    except Exception as e:
        try:
            await status.edit_text(
                f"<blockquote>❌ Extract failed\n<code>{_escape(str(e)[:300])}</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    title = info.get("title") or "Media"
    duration = int(info.get("duration") or 0)
    uploader = info.get("uploader") or info.get("channel") or "Unknown"

    if MAX_DURATION_SEC and duration > MAX_DURATION_SEC:
        await status.edit_text(
            f"<blockquote>❌ Too long ({human_duration(duration)}). "
            f"Max {human_duration(MAX_DURATION_SEC)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    url_key = _cache_url(url)
    preferred = await db.get_preferred_quality(user_id)

    if force_audio:
        # skip picker — go straight to audio job
        await status.edit_text(
            f"<blockquote>🎵 <b>{_escape(title[:70])}</b>\nStarting audio…</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        await _run_job(client, status, user_id, url, "audio", title, duration, uploader)
        return

    text = (
        f"<blockquote>🎬 <b>{_escape(title[:70])}</b>\n"
        f"👤 {_escape(uploader)}\n"
        f"⏱ {human_duration(duration)}\n"
        f"📊 <code>{qmsg}</code>\n\n"
        f"Select quality 👇</blockquote>"
    )
    try:
        await status.edit_text(
            text,
            reply_markup=quality_keyboard(url_key, preferred),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await message.reply_text(
            text,
            reply_markup=quality_keyboard(url_key, preferred),
            parse_mode=ParseMode.HTML,
        )


async def _run_job(
    client: Client,
    status_msg: Message,
    user_id: int,
    url: str,
    quality: str,
    title: str,
    duration: int,
    uploader: str,
):
    # remember preferred (not for fmt:)
    if quality in QUALITY_PRESETS or quality in ("best", "audio"):
        try:
            await db.set_preferred_quality(user_id, quality)
        except Exception:
            pass

    last_edit = [0.0]

    def progress_hook(d: dict):
        if d.get("status") != "downloading":
            return
        now = time.monotonic()
        if now - last_edit[0] < 2.5:
            return
        last_edit[0] = now
        downloaded = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        pct = (downloaded / total * 100) if total else 0
        bar = progress_bar(pct)
        text = (
            f"<blockquote>⏳ <b>Downloading</b>\n"
            f"<code>[{bar}] {pct:.1f}%</code>\n"
            f"📦 {format_size(downloaded)}"
            f"{(' / ' + format_size(total)) if total else ''}\n"
            f"{d.get('_speed_str') or ''}</blockquote>"
        )

        async def _edit():
            try:
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_edit(), loop)
        except Exception:
            pass

    cancel_flag = {"c": False}

    async def job_coro():
        filepath = None
        try:
            try:
                await status_msg.edit_text(
                    f"<blockquote>⬇️ Downloading ({_escape(quality)})…</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

            result = await ytdlp_download(
                url,
                user_id,
                quality=quality,
                progress_callback=progress_hook,
                cancel_check=lambda: cancel_flag["c"],
            )
            filepath = result.get("filepath")
            title2 = result.get("title") or title
            size = result.get("filesize") or (os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0)

            if not filepath or not os.path.exists(filepath):
                raise RuntimeError("File missing after download")

            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise RuntimeError(f"File too large ({format_size(size)})")

            try:
                await status_msg.edit_text(
                    "<blockquote>📤 Uploading to Telegram…</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

            caption = (
                f"<blockquote>{'🎵' if quality == 'audio' else '🎬'} <b>{_escape(title2[:80])}</b>\n"
                f"👤 {_escape(uploader)}\n"
                f"📦 {format_size(size)} · ⏱ {human_duration(duration)}</blockquote>"
            )
            chat_id = status_msg.chat.id
            ext = Path(filepath).suffix.lower()

            if quality == "audio" or ext in (".mp3", ".m4a", ".opus", ".ogg", ".flac"):
                await client.send_audio(
                    chat_id, filepath, caption=caption,
                    title=title2[:64], performer=uploader[:64],
                    duration=duration or None, parse_mode=ParseMode.HTML,
                )
            elif ext in (".mp4", ".mkv", ".webm", ".mov"):
                await client.send_video(
                    chat_id, filepath, caption=caption,
                    supports_streaming=True, duration=duration or None,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await client.send_document(
                    chat_id, filepath, caption=caption, parse_mode=ParseMode.HTML,
                )

            try:
                await status_msg.delete()
            except Exception:
                pass

            await db.log_download(user_id, result.get("id") or url, title2, size)
            try:
                tags = auto_tags(title2)
                await db.add_library_item(
                    user_id=user_id, source="ytdlp",
                    external_id=str(result.get("id") or url)[:250],
                    title=title2, clean_title=tags.get("clean_title"),
                    year=tags.get("year"), season=tags.get("season"),
                    episode=tags.get("episode"), duration=duration,
                    size=size, extractor=result.get("extractor"),
                    webpage_url=url,
                )
            except Exception:
                pass
        except Exception as e:
            logger.exception("download job")
            try:
                await status_msg.edit_text(
                    f"<blockquote>❌ Failed\n<code>{_escape(str(e)[:280])}</code></blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            try:
                await db.log_download(user_id, url, quality, 0, status="error")
            except Exception:
                pass
        finally:
            if filepath and os.path.exists(filepath):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass

    try:
        job = await queue.submit(user_id, f"{quality}:{url[:40]}", job_coro)
        try:
            await status_msg.edit_text(
                f"<blockquote>⏳ Queued · job <code>{job.id}</code>\n"
                f"<code>{_escape(url[:60])}</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    except RuntimeError as e:
        try:
            await status_msg.edit_text(f"<blockquote>🚫 Queue: {_escape(str(e))}</blockquote>", parse_mode=ParseMode.HTML)
        except Exception:
            pass


# ─── Auto URL detect (pyrofork handle_link) — high priority group=-1 ───
@Client.on_message(
    filters.private
    & filters.text
    & ~filters.command([
        "start", "help", "about", "tos", "settings", "me", "status", "ping",
        "search", "library", "queue", "schedule", "schedules", "sites", "quota",
        "cookies", "stars", "buy", "premium", "video", "audio", "dl",
        "listfiles", "forceupload", "path", "clean", "cancelall", "recent",
        "export", "retry", "broadcast", "logs", "backup", "stats", "fname",
        "collections", "watchlater", "colnew", "coladd", "admins", "ban", "unban", "autodel",
    ]),
    group=-1,
)
@check_ban
async def handle_link(client: Client, message: Message):
    text = message.text or ""
    match = URL_REGEX.search(text)
    if not match:
        return
    url = _normalize_url(match.group(1))
    await start_download_flow(client, message, url)


@Client.on_message(filters.private & filters.command("video"), group=0)
@check_ban
async def video_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/video https://youtube.com/...</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    m = URL_REGEX.search(parts[1])
    url = _normalize_url(m.group(1) if m else parts[1].strip())
    await start_download_flow(client, message, url, force_audio=False)


@Client.on_message(filters.private & filters.command("audio"), group=0)
@check_ban
async def audio_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/audio https://...</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    m = URL_REGEX.search(parts[1])
    url = _normalize_url(m.group(1) if m else parts[1].strip())
    await start_download_flow(client, message, url, force_audio=True)


@Client.on_message(filters.private & filters.command("dl"), group=0)
@check_ban
async def dl_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/dl https://...</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    m = URL_REGEX.search(parts[1])
    url = _normalize_url(m.group(1) if m else parts[1].strip())
    await start_download_flow(client, message, url)


@Client.on_message(filters.private & filters.command(["sites", "quota"]), group=0)
@check_ban
async def sites_quota(client: Client, message: Message):
    if message.command[0] == "quota":
        allowed, qmsg = await db.check_quota(message.from_user.id)
        await message.reply_text(
            f"<blockquote>📊 Quota\n<code>{qmsg}</code>\n"
            f"{'✅ OK' if allowed else '🚫 Exceeded'}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    await message.reply_text(
        "<blockquote><b>Supported</b>\n"
        "Any public URL yt-dlp supports:\n"
        "YouTube, Reddit, X/Twitter, TikTok, Instagram, Facebook, Vimeo, SoundCloud…\n"
        "Paste the link or use /video /audio /dl</blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ─── Quality button ───
@Client.on_callback_query(filters.regex(r"^ydl:([a-f0-9]+):(.+)$"))
@check_ban
async def ydl_cb(client: Client, query: CallbackQuery):
    if not await has_accepted_tos(query.from_user.id):
        await query.answer("Accept /tos first", show_alert=True)
        return
    rest = query.data[4:]
    url_key, _, quality = rest.partition(":")
    url = _get_url(url_key)
    if not url:
        await query.answer("Link expired — paste again", show_alert=True)
        return

    await query.answer("Starting…")
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    title = "Media"
    duration = 0
    uploader = "Unknown"
    try:
        # reuse caption from message if present
        pass
    except Exception:
        pass

    try:
        await query.message.edit_text(
            f"<blockquote>⬇️ Preparing <code>{_escape(quality)}</code>…</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await _run_job(
        client, query.message, query.from_user.id,
        url, quality, title, duration, uploader,
    )


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




@Client.on_message(
    filters.private
    & filters.text
    & ~filters.command([
        "start", "help", "about", "tos", "settings", "me", "status", "ping",
        "search", "library", "queue", "schedule", "schedules", "sites", "quota",
        "cookies", "stars", "buy", "premium", "video", "audio", "dl",
        "listfiles", "forceupload", "path", "clean", "cancelall", "recent",
        "export", "retry", "broadcast", "logs", "backup", "stats", "fname",
        "collections", "watchlater", "colnew", "coladd", "admins", "ban", "unban", "autodel",
    ]),
    group=5,
)
@check_ban
async def plain_text_tip(client: Client, message: Message):
    text = (message.text or "").strip()
    if not text or URL_REGEX.search(text):
        return
    if len(text) < 2:
        return
    msg = (
        "<blockquote>Send a full link starting with <code>https://</code>\n\n"
        "Example:\n<code>https://youtu.be/xxxx</code>\n\n"
        "Or use:\n<code>/video https://...</code>\n"
        "<code>/audio https://...</code></blockquote>"
    )
    await message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
