#@mediavault
"""
URL downloads — real formats, queue, cancel, preferred quality, quotas, TOS.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from config import (
    CAPTION_TEMPLATE, PROGRESS_TEMPLATE, AUTO_DELETE_SECONDS,
    YTDLP_ENABLED, REQUIRE_TOS_ACCEPT, TOS_TEXT, QUALITY_PRESETS,
    RATE_LIMIT_PER_MIN, YTDLP_PLAYLIST_MAX,
)
from core.database import db
from core.ytdlp import download as ytdlp_download, is_supported_url, extract_info, list_formats
from core.utils import format_size, ProgressTracker
from core.queue import queue
from core.emoji import ce, thinking_frames, ok, warn, progress_header
from core.telegram_ux import safe_react, safe_chat_action
from core.media import auto_tags, metadata_card
from core.media import auto_tags, metadata_card, extract_audio
from config import SHARE_CHANNEL
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)",
    re.IGNORECASE,
)
_url_cache: dict[str, str] = {}


def _cache_url(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    _url_cache[key] = url
    if len(_url_cache) > 500:
        for k in list(_url_cache.keys())[:100]:
            _url_cache.pop(k, None)
    return key


def _get_url(key: str) -> str | None:
    return _url_cache.get(key)


async def has_accepted_tos(user_id: int) -> bool:
    if not REQUIRE_TOS_ACCEPT:
        return True
    return bool(await db.get_setting(f"tos_accepted_{user_id}", False))


async def set_tos_accepted(user_id: int) -> None:
    await db.set_setting(f"tos_accepted_{user_id}", True)


async def send_tos(client: Client, message: Message | CallbackQuery):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I Accept — My Risk", callback_data="tos:accept"),
        InlineKeyboardButton("❌ Decline", callback_data="tos:decline"),
    ]])
    target = message if isinstance(message, Message) else message.message
    await target.reply_text(TOS_TEXT, reply_markup=kb, parse_mode=ParseMode.HTML)


def preset_keyboard(url_key: str, preferred: str | None = None) -> InlineKeyboardMarkup:
    labels = [
        ("🏆 Best", "best"), ("1080p", "1080"), ("720p", "720"),
        ("480p", "480"), ("360p", "360"), ("🎵 Audio", "audio"),
    ]
    rows = []
    row = []
    for text, key in labels:
        mark = " •" if preferred == key else ""
        row.append(InlineKeyboardButton(f"{text}{mark}", callback_data=f"ydl:{url_key}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("📋 All formats", callback_data=f"fmts:{url_key}"),
        InlineKeyboardButton("❌ Cancel", callback_data="close"),
    ])
    return InlineKeyboardMarkup(rows)


@Client.on_callback_query(filters.regex(r"^tos:accept$"))
@check_ban
async def tos_accept(client: Client, query: CallbackQuery):
    await set_tos_accepted(query.from_user.id)
    await query.answer("Accepted.")
    await query.message.edit_text("✅ <b>Terms accepted.</b> Downloads unlocked — your own risk.", parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^tos:decline$"))
@check_ban
async def tos_decline(client: Client, query: CallbackQuery):
    await query.answer("Declined.", show_alert=True)
    await query.message.edit_text("❌ Declined. Download features locked.", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("tos"))
@check_ban
async def tos_cmd(client: Client, message: Message):
    if await has_accepted_tos(message.from_user.id):
        await message.reply_text("✅ Already accepted. Downloads at your own risk.", parse_mode=ParseMode.HTML)
    else:
        await send_tos(client, message)


@Client.on_message(filters.private & filters.regex(URL_REGEX) & ~filters.command(["start", "help", "tos", "quota", "cookies"]))
@check_ban
async def url_handler(client: Client, message: Message):
    if not YTDLP_ENABLED:
        return
    if not await has_accepted_tos(message.from_user.id):
        await send_tos(client, message)
        return

    urls = URL_REGEX.findall(message.text or "")
    if not urls:
        return
    url = urls[0].strip()
    if not is_supported_url(url):
        return

    uid = message.from_user.id
    await db.ensure_user(uid, message.from_user.username, message.from_user.first_name)

    ok, count = await db.check_rate_limit(uid, RATE_LIMIT_PER_MIN)
    if not ok:
        await message.reply_text(f"⏳ Slow down — max {RATE_LIMIT_PER_MIN} links/min.", parse_mode=ParseMode.HTML)
        return

    allowed, qmsg = await db.check_quota(uid)
    if not allowed:
        await message.reply_text(f"🚫 <b>Quota exceeded</b>\n{qmsg}", parse_mode=ParseMode.HTML)
        return

    status = await message.reply_text(f"🔗 Fetching info…\n<code>{url[:70]}</code>", parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    url_key = _cache_url(url)
    preferred = await db.get_preferred_quality(uid)

    try:
        info = await extract_info(url)
        title = (info.get("title") or "Unknown")[:80]
        duration = info.get("duration")
        uploader = info.get("uploader") or info.get("channel") or ""
        extractor = info.get("extractor_key") or info.get("extractor") or "?"
        filesize = info.get("filesize") or info.get("filesize_approx")
        is_pl = "entries" in (info or {})
        dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "—"
        size_str = format_size(filesize) if filesize else "—"
        pl_note = f"\n📜 Playlist detected (max {YTDLP_PLAYLIST_MAX} items)" if is_pl and YTDLP_PLAYLIST_MAX else ""

        age = info.get("age_limit")
        text = (
            f"<blockquote>{ce('fire', '🔥')} <b>{title}</b>\n"
            f"👤 {uploader}\n"
            f"⏱ {dur_str} | 📦 {size_str} | 🌐 {extractor}{pl_note}\n"
            f"{('⚠️ Age: ' + str(age) + '+\n') if age else ''}"
            f"📊 <code>{qmsg}</code>\n"
            f"Choose quality <i>(your risk)</i></blockquote>"
        )
        if age and int(age) >= 18:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🛡 I confirm (18+)", callback_data=f"ageok:{url_key}"),
                InlineKeyboardButton("Cancel", callback_data="close"),
            ]])
            # store preferred in cache side channel via url key only; show confirm first
            await status.edit_text(
                text + f"\n\n<blockquote>{warn()} Age-restricted — confirm to continue</blockquote>",
                reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            )
        else:
            await status.edit_text(text, reply_markup=preset_keyboard(url_key, preferred), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        logger.warning("extract_info: %s", e)
        await status.edit_text(
            f"🔗 <code>{url[:80]}</code>\n\nInfo failed — pick quality anyway:\n📊 <code>{qmsg}</code>",
            reply_markup=preset_keyboard(url_key, preferred),
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )


@Client.on_callback_query(filters.regex(r"^fmts:([a-f0-9]+)$"))
@check_ban
async def show_formats(client: Client, query: CallbackQuery):
    url_key = query.data.split(":")[1]
    url = _get_url(url_key)
    if not url:
        await query.answer("Link expired", show_alert=True)
        return
    await query.answer("Loading formats…")
    try:
        formats = await list_formats(url)
    except Exception as e:
        await query.message.edit_text(f"❌ Could not list formats:\n<code>{e}</code>", parse_mode=ParseMode.HTML)
        return
    if not formats:
        await query.message.edit_text("No formats found. Use presets.", reply_markup=preset_keyboard(url_key))
        return
    rows = []
    row = []
    for f in formats:
        btn = InlineKeyboardButton(f["label"], callback_data=f"ydl:{url_key}:fmt:{f['id']}")
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("⬅️ Presets", callback_data=f"presets:{url_key}"),
        InlineKeyboardButton("❌ Cancel", callback_data="close"),
    ])
    await query.message.edit_text(
        "📋 <b>Available formats</b>\nTap one to download:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^presets:([a-f0-9]+)$"))
@check_ban
async def show_presets(client: Client, query: CallbackQuery):
    url_key = query.data.split(":")[1]
    preferred = await db.get_preferred_quality(query.from_user.id)
    await query.message.edit_text(
        "Choose quality:",
        reply_markup=preset_keyboard(url_key, preferred),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^ydl:([a-f0-9]+):(.+)$"))
@check_ban
async def start_download_cb(client: Client, query: CallbackQuery):
    if not await has_accepted_tos(query.from_user.id):
        await query.answer("Accept /tos first", show_alert=True)
        return

    # ydl:<key>:<quality>  or  ydl:<key>:fmt:<id>
    rest = query.data[4:]  # after ydl:
    url_key, _, qual_part = rest.partition(":")
    quality = qual_part  # may be "720" or "fmt:137"
    url = _get_url(url_key)
    if not url:
        await query.answer("Link expired — paste again", show_alert=True)
        return

    uid = query.from_user.id
    allowed, qmsg = await db.check_quota(uid)
    if not allowed:
        await query.answer(qmsg, show_alert=True)
        return

    # duplicate hint
    try:
        info_quick = None
        dups = await db.find_duplicates(uid, url[-40:] if len(url) > 40 else url)
        # soft: only title from cache not available here
    except Exception:
        pass

    # remember preferred if it's a preset
    if quality in QUALITY_PRESETS:
        await db.set_preferred_quality(uid, quality)

    await query.answer("Queued…")

    status_msg = await query.message.edit_text(
        f"⏳ Queued ({quality})\n<code>{url[:55]}</code>",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True,
    )

    # Hold job ref for cancel_check
    job_holder = {"job": None}

    async def job_coro():
        job = job_holder["job"]
        tracker = ProgressTracker()
        last = ""

        def progress_hook(d):
            if d.get("status") == "downloading":
                tracker.update(
                    d.get("downloaded_bytes") or 0,
                    d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                )

        def cancel_check():
            return job is not None and job.cancel_event.is_set()

        async def updater():
            nonlocal last
            while True:
                await asyncio.sleep(1.8)
                if cancel_check():
                    return
                if tracker.total > 0 and tracker.should_update(1.5):
                    text = tracker.render("Downloading", PROGRESS_TEMPLATE)
                    if text != last and job:
                        try:
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Cancel", callback_data=f"qcancel:{job.id}")]])
                            await status_msg.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
                            last = text
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                        except Exception:
                            pass

        upd = asyncio.create_task(updater())
        filepath = None
        try:
            jid = job.id if job else "?"
            await status_msg.edit_text(
                f"⬇️ Downloading ({quality})…\n<code>{url[:55]}</code>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Cancel", callback_data=f"qcancel:{jid}")]]),
                parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            )
            result = await ytdlp_download(
                url, uid, quality=quality,
                progress_callback=progress_hook,
                cancel_check=cancel_check,
            )
            upd.cancel()
            if cancel_check():
                raise Exception("Cancelled")

            filepath = result["filepath"]
            title = result.get("title") or Path(filepath).name
            size = result.get("filesize") or os.path.getsize(filepath)
            source = result.get("extractor") or "web"
            webpage = result.get("webpage_url") or url

            await status_msg.edit_text(f"⬆️ Uploading…\n<code>{title[:55]}</code>", parse_mode=ParseMode.HTML)

            caption = CAPTION_TEMPLATE.format(name=title[:100], size=format_size(size), source=f"{source} • {quality} • {webpage}")
            ext = (result.get("ext") or Path(filepath).suffix.lstrip(".")).lower()

            if quality == "audio" or "audio" in quality or ext in ("mp3", "m4a", "ogg", "flac", "wav", "opus"):
                msg = await client.send_audio(query.message.chat.id, filepath, caption=caption, parse_mode=ParseMode.HTML)
            elif ext in ("mp4", "mkv", "webm", "mov", "avi"):
                msg = await client.send_video(query.message.chat.id, filepath, caption=caption, parse_mode=ParseMode.HTML, supports_streaming=True)
            else:
                msg = await client.send_document(query.message.chat.id, filepath, caption=caption, parse_mode=ParseMode.HTML)

            try:
                await status_msg.delete()
            except Exception:
                pass
            await db.log_download(uid, result.get("id") or url, title, size)
            # library index + tags
            tags = auto_tags(title)
            try:
                await db.add_library_item(
                    user_id=uid, source="ytdlp",
                    external_id=str(result.get("id") or url)[:250],
                    title=title, clean_title=tags.get("clean_title"),
                    year=tags.get("year"), season=tags.get("season"),
                    episode=tags.get("episode"), duration=result.get("duration"),
                    size=size, extractor=result.get("extractor"),
                    webpage_url=webpage,
                )
            except Exception:
                pass

            secs = await db.get_setting("auto_delete_seconds", AUTO_DELETE_SECONDS)
            if secs and int(secs) > 0:
                async def _del():
                    await asyncio.sleep(int(secs))
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                asyncio.create_task(_del())
        except Exception as e:
            try:
                upd.cancel()
            except Exception:
                pass
            if "Cancel" in str(e) or cancel_check():
                try:
                    await status_msg.edit_text("🗑 Download cancelled.", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            else:
                logger.exception("dl fail")
                try:
                    await status_msg.edit_text(f"❌ Failed:\n<code>{str(e)[:280]}</code>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
                await db.log_download(uid, url, quality, 0, status="error")
        finally:
            if filepath and os.path.exists(filepath):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass

    try:
        job = await queue.submit(uid, f"{quality}:{url[:40]}", job_coro)
        job_holder["job"] = job
    except RuntimeError as e:
        await status_msg.edit_text(f"🚫 Queue full: {e}", parse_mode=ParseMode.HTML)
        return

    try:
        await status_msg.edit_text(
            f"⏳ In queue / starting…\n<code>{url[:55]}</code>\nJob: <code>{job.id}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Cancel", callback_data=f"qcancel:{job.id}")]]),
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^qcancel:(.+)$"))
@check_ban
async def cancel_job(client: Client, query: CallbackQuery):
    job_id = query.data.split(":", 1)[1]
    ok = await queue.cancel(job_id, query.from_user.id)
    if ok:
        await query.answer("Cancel requested")
        try:
            await query.message.edit_text("🗑 Cancel requested…", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    else:
        await query.answer("Cannot cancel (not yours or already finished)", show_alert=True)



@Client.on_callback_query(filters.regex(r"^ageok:([a-f0-9]+)$"))
@check_ban
async def age_ok_cb(client: Client, query: CallbackQuery):
    url_key = query.data.split(":")[1]
    preferred = await db.get_preferred_quality(query.from_user.id)
    await query.answer("Confirmed")
    await query.message.edit_text(
        f"<blockquote>{ok()} Confirmed. Choose quality:</blockquote>",
        reply_markup=preset_keyboard(url_key, preferred),
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("sites"))
@check_ban
async def sites_cmd(client: Client, message: Message):
    await message.reply_text(
        "≡ <b>Supported platforms</b>\n\nYouTube • Reddit • X • TikTok • Instagram\n"
        "Vimeo • SoundCloud • Twitch • +1000 via yt-dlp\n\n"
        "Presets + full format list • Queue • Cancel • Quotas\n/cookies /tos /quota",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("quota"))
@check_ban
async def quota_cmd(client: Client, message: Message):
    allowed, qmsg = await db.check_quota(message.from_user.id)
    status = "✅ OK" if allowed else "🚫 Exceeded"
    await message.reply_text(f"≡ <b>Daily quota</b>\n\n{status}\n<code>{qmsg}</code>\nResets UTC midnight.", parse_mode=ParseMode.HTML)
