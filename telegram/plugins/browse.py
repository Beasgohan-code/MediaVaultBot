#@mediavault
"""Drive browser with breadcrumbs + sort."""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.database import db
from core.drive import drive
from core.state import browse_state
from core.utils import format_size
from telegram.decorators import check_ban

logger = logging.getLogger(__name__)
FOLDER_MIME = "application/vnd.google-apps.folder"

# user_id -> list of (folder_id, name) breadcrumbs
_crumbs: dict[int, list[tuple[str, str]]] = {}
# user_id -> sort key
_sort: dict[int, str] = {}


def _file_button(f: Dict) -> InlineKeyboardButton:
    name = f.get("name", "Unknown")[:36]
    fid = f["id"]
    if f.get("mimeType") == FOLDER_MIME:
        return InlineKeyboardButton(f"📁 {name}", callback_data=f"browse:{fid}")
    size = format_size(int(f["size"])) if f.get("size") else ""
    label = f"📄 {name}" + (f" ({size})" if size else "")
    return InlineKeyboardButton(label[:40], callback_data=f"file:{fid}")


def build_keyboard(
    files: List[Dict], folder_id: str, next_token: Optional[str],
    crumbs: list, sort_key: str,
) -> InlineKeyboardMarkup:
    # sort client-side
    if sort_key == "size":
        files = sorted(files, key=lambda x: int(x.get("size") or 0), reverse=True)
    elif sort_key == "date":
        files = sorted(files, key=lambda x: x.get("modifiedTime") or "", reverse=True)
    else:
        files = sorted(files, key=lambda x: (x.get("mimeType") != FOLDER_MIME, (x.get("name") or "").lower()))

    rows = []
    row = []
    for f in files:
        row.append(_file_button(f))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # sort buttons
    rows.append([
        InlineKeyboardButton("Name" + ("•" if sort_key == "name" else ""), callback_data=f"sort:name:{folder_id}"),
        InlineKeyboardButton("Size" + ("•" if sort_key == "size" else ""), callback_data=f"sort:size:{folder_id}"),
        InlineKeyboardButton("Date" + ("•" if sort_key == "date" else ""), callback_data=f"sort:date:{folder_id}"),
    ])

    nav = []
    if len(crumbs) > 1:
        parent = crumbs[-2][0]
        nav.append(InlineKeyboardButton("⬅️ Up", callback_data=f"browse:{parent}"))
    if next_token:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"bpage:{folder_id}"))
    nav.append(InlineKeyboardButton("🏠 Root", callback_data="browse:root"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    return InlineKeyboardMarkup(rows)


def crumb_text(crumbs: list) -> str:
    if not crumbs:
        return "📂 Root"
    parts = [c[1][:20] for c in crumbs[-4:]]
    return " / ".join(parts)


@Client.on_message(filters.private & filters.command("browse"))
@check_ban
async def browse_cmd(client: Client, message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    uid = message.from_user.id
    folder_id = browse_state.get(uid) or "root"
    await _send_folder(client, message, folder_id, uid)


async def _send_folder(client, target, folder_id: str, uid: int, edit: bool = False):
    real_id = None if folder_id in ("root", "") else folder_id
    sort_key = _sort.get(uid, "name")
    try:
        files, next_token = await drive.list_folder(real_id)
    except Exception as e:
        logger.exception("list_folder")
        text = f"❌ Drive error: <code>{e}</code>"
        if edit and isinstance(target, CallbackQuery):
            await target.message.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await target.reply_text(text, parse_mode=ParseMode.HTML)
        return

    browse_state[uid] = folder_id or "root"

    # maintain crumbs
    crumbs = _crumbs.get(uid, [("root", "Root")])
    if folder_id in ("root", ""):
        crumbs = [("root", "Root")]
    else:
        # if navigating deeper, append; if jumping, try keep
        names = {c[0]: c[1] for c in crumbs}
        if folder_id not in names:
            # get name
            meta = await drive.get_file(folder_id)
            name = (meta or {}).get("name", folder_id[:8])
            crumbs = crumbs + [(folder_id, name)]
        else:
            # trim to this folder
            idx = next(i for i, c in enumerate(crumbs) if c[0] == folder_id)
            crumbs = crumbs[: idx + 1]
    _crumbs[uid] = crumbs

    caption = f"<b>{crumb_text(crumbs)}</b>\n<code>{len(files)} items</code> • sort: {sort_key}"
    kb = build_keyboard(files, folder_id or "root", next_token, crumbs, sort_key)

    if edit and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(caption, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await target.message.reply_text(caption, reply_markup=kb, parse_mode=ParseMode.HTML)
        await target.answer()
    else:
        await target.reply_text(caption, reply_markup=kb, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^browse:(.+)$"))
@check_ban
async def browse_cb(client: Client, query: CallbackQuery):
    folder_id = query.data.split(":", 1)[1]
    if folder_id == "root":
        folder_id = ""
    await _send_folder(client, query, folder_id or "root", query.from_user.id, edit=True)


@Client.on_callback_query(filters.regex(r"^sort:(\w+):(.+)$"))
@check_ban
async def sort_cb(client: Client, query: CallbackQuery):
    _, sort_key, folder_id = query.data.split(":", 2)
    _sort[query.from_user.id] = sort_key
    await _send_folder(client, query, folder_id, query.from_user.id, edit=True)


@Client.on_callback_query(filters.regex(r"^close$"))
async def close_cb(client: Client, query: CallbackQuery):
    try:
        await query.message.delete()
    except Exception:
        await query.answer("Closed")
    await query.answer()
