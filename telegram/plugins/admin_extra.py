#@mediavault
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import OWNER_ID
from core.database import db
from core.emoji import ce, ok, bad, warn, crown
from telegram.decorators import check_ban, admin_only, owner_only


@Client.on_message(filters.private & filters.command("broadcast"))
@check_ban
@admin_only
async def broadcast_cmd(client: Client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            f"<blockquote>{warn()} Usage: <code>/broadcast your message</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    text = parts[1]
    uids = await db.list_user_ids()
    status = await message.reply_text(
        f"<blockquote>{ce('plane', '✈️')} Broadcasting to <code>{len(uids)}</code> users…</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    ok_n = fail_n = 0
    for uid in uids:
        try:
            await client.send_message(
                uid,
                f"<blockquote>{ce('letter', '💌')} <b>Announcement</b>\n\n{text}</blockquote>",
                parse_mode=ParseMode.HTML,
            )
            ok_n += 1
        except Exception:
            fail_n += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        f"<blockquote>{ok()} Broadcast done.\n✅ {ok_n} · ❌ {fail_n}</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("logs"))
@check_ban
@admin_only
async def logs_cmd(client: Client, message: Message):
    rows = await db.recent_errors(25)
    if not rows:
        await message.reply_text(f"<blockquote>{ok()} No recent errors.</blockquote>", parse_mode=ParseMode.HTML)
        return
    lines = [f"<blockquote>{warn()} <b>Recent errors</b>\n"]
    for r in rows:
        lines.append(f"• <code>{r.user_id}</code> {r.file_name[:40]} <i>{r.created_at}</i>")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines)[:4000], parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("backup"))
@check_ban
@owner_only
async def backup_cmd(client: Client, message: Message):
    """Export essential user/library data as JSON to owner."""
    uids = await db.list_user_ids()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_count": len(uids),
        "users_sample": uids[:500],
    }
    # library for owner only
    lib = await db.search_library(message.from_user.id, "", limit=1)
    # dump collections
    cols = await db.list_collections(message.from_user.id)
    payload["collections"] = [{"id": c.id, "name": c.name} for c in cols]
    path = Path(tempfile.gettempdir()) / f"mediavault_backup_{int(datetime.now().timestamp())}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    await message.reply_document(
        str(path),
        caption=f"<blockquote>{crown()} Database backup (metadata)</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    try:
        path.unlink()
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("export"))
@check_ban
async def export_cmd(client: Client, message: Message):
    items = await db.search_library(message.from_user.id, "%")
    # search with empty might fail ilike %% — use recent logs instead
    recent = await db.recent_downloads(message.from_user.id, 100)
    rows = [
        {"name": r.file_name, "size": r.size, "status": r.status, "at": str(r.created_at)}
        for r in recent
    ]
    path = Path(tempfile.gettempdir()) / f"export_{message.from_user.id}.json"
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    await message.reply_document(
        str(path),
        caption=f"<blockquote>{ce('bookmark', '🔖')} Your library export</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    try:
        path.unlink()
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("retry"))
@check_ban
async def retry_cmd(client: Client, message: Message):
    fails = await db.failed_for_user(message.from_user.id, 5)
    if not fails:
        await message.reply_text(f"<blockquote>{ok()} No failed jobs to retry.</blockquote>", parse_mode=ParseMode.HTML)
        return
    lines = [f"<blockquote>{ce('strong', '💪')} <b>Recent failures</b> — paste the URL again to retry\n"]
    for f in fails:
        lines.append(f"• <code>{f.file_id[:60]}</code> — {f.file_name[:30]}")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@Client.on_message(filters.private & filters.command("recent"))
@check_ban
async def recent_cmd(client: Client, message: Message):
    rows = await db.recent_downloads(message.from_user.id, 15)
    if not rows:
        await message.reply_text(f"<blockquote>{ce('ghost', '👻')} No recent downloads.</blockquote>", parse_mode=ParseMode.HTML)
        return
    lines = [f"<blockquote>{ce('fire', '🔥')} <b>Recent downloads</b>\n"]
    for r in rows:
        lines.append(f"• {r.file_name[:50]}")
    lines.append("</blockquote>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
