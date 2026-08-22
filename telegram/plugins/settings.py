#@mediavault
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import QUALITY_PRESETS, AUTO_DELETE_SECONDS
from core.database import db
from core.emoji import ce, ok, star
from core.i18n import t
from telegram.decorators import check_ban


def settings_kb(uid_settings: dict) -> InlineKeyboardMarkup:
    q = uid_settings.get("quality") or "best"
    lang = uid_settings.get("lang") or "en"
    silent = uid_settings.get("silent", False)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Quality: {q}", callback_data="set:quality"),
            InlineKeyboardButton(f"Lang: {lang}", callback_data="set:lang"),
        ],
        [
            InlineKeyboardButton(f"Silent: {'ON' if silent else 'OFF'}", callback_data="set:silent"),
            InlineKeyboardButton(f"Protect: {'ON' if uid_settings.get('protect_content') else 'OFF'}", callback_data="set:protect"),
        ],
        [InlineKeyboardButton("Filename /fname", callback_data="set:fname")],
        [InlineKeyboardButton("Close", callback_data="close")],
    ])


@Client.on_message(filters.private & filters.command("settings"))
@check_ban
async def settings_cmd(client: Client, message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    s = await db.get_user_settings(message.from_user.id)
    lang = s.get("lang", "en")
    text = (
        f"<blockquote>{star()} <b>{t(lang, 'settings_title')}</b>\n\n"
        f"{ce('pin', '📌')} {t(lang, 'quality')}: <code>{s.get('quality') or 'best'}</code>\n"
        f"{ce('web', '🌐')} {t(lang, 'language')}: <code>{s.get('lang', 'en')}</code>\n"
        f"{ce('snow', '❄️')} Silent progress: <code>{s.get('silent', False)}</code>\n"
        f"{ce('bookmark', '🔖')} Filename: <code>{s.get('filename_template') or '{title}'}</code>\n"
        f"</blockquote>"
    )
    await message.reply_text(text, reply_markup=settings_kb(s), parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^set:(\w+)$"))
@check_ban
async def settings_cb(client: Client, query: CallbackQuery):
    action = query.data.split(":")[1]
    uid = query.from_user.id
    s = await db.get_user_settings(uid)
    if action == "lang":
        new = "hi" if s.get("lang") != "hi" else "en"
        await db.update_user_settings(uid, lang=new)
        await query.answer(f"Lang → {new}")
    elif action == "silent":
        await db.update_user_settings(uid, silent=not s.get("silent", False))
        await query.answer("Toggled silent")
    elif action == "protect":
        await db.update_user_settings(uid, protect_content=not s.get("protect_content", False))
        await query.answer("Toggled protect_content")
    elif action == "quality":
        order = list(QUALITY_PRESETS.keys())
        cur = s.get("quality") or "best"
        try:
            i = order.index(cur)
            nxt = order[(i + 1) % len(order)]
        except ValueError:
            nxt = "best"
        await db.update_user_settings(uid, quality=nxt)
        await db.set_preferred_quality(uid, nxt)
        await query.answer(f"Quality → {nxt}")
    elif action == "fname":
        await query.answer("Send: /fname Your {title} [{height}] template", show_alert=True)
        return
    else:
        await query.answer()
        return
    s = await db.get_user_settings(uid)
    lang = s.get("lang", "en")
    text = (
        f"<blockquote>{ok()} <b>{t(lang, 'settings_title')}</b> — {t(lang, 'saved')}\n"
        f"Quality: <code>{s.get('quality') or 'best'}</code> | Lang: <code>{s.get('lang', 'en')}</code>\n"
        f"Silent: <code>{s.get('silent', False)}</code></blockquote>"
    )
    try:
        await query.message.edit_text(text, reply_markup=settings_kb(s), parse_mode=ParseMode.HTML)
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("fname"))
@check_ban
async def fname_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote>Usage: <code>/fname {title} [{height}]</code>\n"
            "Placeholders: {title} {id} {extractor}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    await db.update_user_settings(message.from_user.id, filename_template=parts[1][:120])
    await message.reply_text(f"<blockquote>{ok()} Filename template saved.</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("me"))
@check_ban
async def me_cmd(client: Client, message: Message):
    uid = message.from_user.id
    await db.ensure_user(uid, message.from_user.username, message.from_user.first_name)
    allowed, qmsg = await db.check_quota(uid)
    count, nbytes = await db.get_daily_usage(uid)
    recent = await db.recent_downloads(uid, 5)
    s = await db.get_user_settings(uid)
    lang = s.get("lang", "en")
    lines = [
        f"<blockquote>{ce('crown', '👑')} <b>{t(lang, 'me_title')}</b>",
        f"{ce('money', '💰')} {t(lang, 'quota')}: <code>{qmsg}</code>",
        f"{ce('fire', '🔥')} Today: <code>{count}</code> files / <code>{nbytes // (1024*1024)} MB</code>",
        f"{ce('star', '⭐')} Quality: <code>{s.get('quality') or 'best'}</code>",
        "",
        "<b>Recent</b>",
    ]
    for r in recent:
        lines.append(f"• {r.file_name[:40]}")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
