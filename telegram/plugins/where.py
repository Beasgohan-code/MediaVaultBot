#@mediavault
"""Legal: TMDB search + where to watch (official provider links only)."""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import TMDB_API_KEY, TMDB_REGION
from core.tmdb import search, watch_providers
from core.emoji import ce, star
from telegram.decorators import check_ban


@Client.on_message(filters.private & filters.command(["where", "tmdb"]))
@check_ban
async def where_cmd(client: Client, message: Message):
    if not TMDB_API_KEY:
        await message.reply_text(
            f"<blockquote>{ce('alert', '🚨')} Set <code>TMDB_API_KEY</code> in .env\n"
            f"Get a free key: themoviedb.org</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            f"<blockquote>{ce('web', '🌐')} <b>Where to watch</b> (legal)\n"
            f"Usage: <code>/where Inception</code>\n"
            f"Shows official streaming / rent / buy providers via TMDB + JustWatch data.\n"
            f"Does <b>not</b> stream or download the title.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    q = parts[1].strip()
    status = await message.reply_text(
        f"<blockquote>{ce('crystal', '🔮')} Searching TMDB for <b>{q}</b>…</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    results = await search(q)
    if not results:
        await status.edit_text(f"<blockquote>No TMDB results for <code>{q}</code></blockquote>", parse_mode=ParseMode.HTML)
        return
    rows = []
    for r in results:
        rows.append([InlineKeyboardButton(
            f"{r['title'][:40]} ({r['year']})",
            callback_data=f"tmdb:{r['media_type']}:{r['id']}",
        )])
    rows.append([InlineKeyboardButton("Close", callback_data="close")])
    await status.edit_text(
        f"<blockquote>{star()} <b>TMDB results</b> — pick one for legal watch providers</blockquote>",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^tmdb:(movie|tv):(\d+)$"))
@check_ban
async def tmdb_cb(client: Client, query: CallbackQuery):
    _, media_type, sid = query.data.split(":")
    await query.answer()
    info = await watch_providers(media_type, int(sid))
    providers = info.get("providers") or []
    link = info.get("link") or f"https://www.themoviedb.org/{media_type}/{sid}"
    if not providers:
        await query.message.reply_text(
            f"<blockquote>{ce('ghost', '👻')} No providers listed for region <code>{info.get('region', TMDB_REGION)}</code>\n"
            f"<a href=\"{link}\">Open on TMDB</a></blockquote>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return
    lines = [f"<blockquote>{ce('web', '🌐')} <b>Legal watch options</b> ({info.get('region')})\n"]
    for p in providers[:15]:
        lines.append(f"• <b>{p['name']}</b> <i>({p['type']})</i>")
    lines.append(f"\n<a href=\"{link}\">Details / deep links on TMDB</a>")
    lines.append("\n<i>Attribution: TMDB + JustWatch. No unofficial streams.</i></blockquote>")
    await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
