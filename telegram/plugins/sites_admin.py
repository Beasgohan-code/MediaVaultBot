#@mediavault
"""
Custom sites: /addsite /delsite /listsites /setpremium /unsetpremium
Stored in DB settings — survives restarts.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import OWNER_ID, PREMIUM_DOMAINS as ENV_PREMIUM
from core.database import db
from core.emoji import ce, ok, warn
from telegram.decorators import check_ban

_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})(?:/.*)?$", re.I)


def _norm_domain(raw: str) -> str | None:
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    m = _DOMAIN_RE.match(raw)
    if m:
        return m.group(1).lstrip(".")
    # bare domain
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", raw):
        return raw
    return None


async def get_extra_sites() -> list[str]:
    data = await db.get_setting("custom_sites", []) or []
    return [str(x).lower() for x in data]


async def get_extra_premium() -> list[str]:
    data = await db.get_setting("custom_premium_sites", []) or []
    return [str(x).lower() for x in data]


async def all_premium_domains() -> list[str]:
    base = list(ENV_PREMIUM or [])
    extra = await get_extra_premium()
    # de-dupe
    seen = set()
    out = []
    for d in base + extra:
        d = d.lower().strip()
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _is_owner(uid: int) -> bool:
    return uid == OWNER_ID


@Client.on_message(filters.private & filters.command(["addsite", "addsites"]))
@check_ban
async def addsite_cmd(client: Client, message: Message):
    if not _is_owner(message.from_user.id):
        await message.reply_text("Owner only.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            f"<blockquote>{ce('pin', '📌')} <b>Add site(s)</b>\n"
            f"<code>/addsites example.com</code> or <code>/addsites example1.com, example2.com</code>\n"
            f"Marks domain as known/supported for /listsites & universal scrapers.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    raw_sites = parts[1].split(",")
    added = []
    sites = await get_extra_sites()
    for raw in raw_sites:
        dom = _norm_domain(raw.strip())
        if dom and dom not in sites:
            sites.append(dom)
            added.append(dom)
    if added:
        await db.set_setting("custom_sites", sites)
        await message.reply_text(
            f"<blockquote>{ok()} Added <code>{', '.join(added)}</code>\n"
            f"Total custom sites: <code>{len(sites)}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text("<blockquote>❌ No new valid domains added.</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("delsite"))
@check_ban
async def delsite_cmd(client: Client, message: Message):
    if not _is_owner(message.from_user.id):
        await message.reply_text("Owner only.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("Usage: <code>/delsite example.com</code>", parse_mode=ParseMode.HTML)
        return
    dom = _norm_domain(parts[1])
    sites = await get_extra_sites()
    if dom not in sites:
        await message.reply_text("Not in custom list.")
        return
    sites = [s for s in sites if s != dom]
    await db.set_setting("custom_sites", sites)
    await message.reply_text(f"<blockquote>{ok()} Removed <code>{dom}</code></blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("setpremium"))
@check_ban
async def setpremium_site(client: Client, message: Message):
    if not _is_owner(message.from_user.id):
        await message.reply_text("Owner only.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "<blockquote><code>/setpremium reddit.com</code>\n"
            "Require Stars premium to download that domain.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    dom = _norm_domain(parts[1])
    if not dom:
        await message.reply_text("❌ Bad domain")
        return
    prem = await get_extra_premium()
    if dom not in prem:
        prem.append(dom)
        await db.set_setting("custom_premium_sites", prem)
    # also ensure in custom sites
    sites = await get_extra_sites()
    if dom not in sites:
        sites.append(dom)
        await db.set_setting("custom_sites", sites)
    await message.reply_text(
        f"<blockquote>{ok()} Premium domain: <code>{dom}</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("unsetpremium"))
@check_ban
async def unsetpremium_site(client: Client, message: Message):
    if not _is_owner(message.from_user.id):
        await message.reply_text("Owner only.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("Usage: <code>/unsetpremium reddit.com</code>", parse_mode=ParseMode.HTML)
        return
    dom = _norm_domain(parts[1])
    prem = await get_extra_premium()
    prem = [s for s in prem if s != dom]
    await db.set_setting("custom_premium_sites", prem)
    await message.reply_text(f"<blockquote>{ok()} Unset premium: <code>{dom}</code></blockquote>", parse_mode=ParseMode.HTML)



@Client.on_message(filters.private & filters.command(["listsites", "sites"]))
@check_ban
async def listsites_cmd(client: Client, message: Message):
    from core.ytdlp import SITE_CATALOG, SEARCH_BACKENDS
    custom = await get_extra_sites()
    prem = await all_premium_domains()

    lines = [
        f"<blockquote>{ce('globe', '🌐')} <b>Supported sites</b>",
        "",
        "<b>Keyword search</b> — use /search:",
    ]
    for key, (_, label) in SEARCH_BACKENDS.items():
        lines.append(f"• {label}")
    lines.append("")
    lines.append("<b>Catalog</b> (paste URL to download):")
    for dom, meta in list(SITE_CATALOG.items())[:16]:
        home = meta.get("home") or f"https://{dom}"
        name = meta.get("name") or dom
        notes = meta.get("notes") or ""
        searchable = "🔍" if meta.get("search") else "🔗"
        lines.append(f'{searchable} <a href="{home}">{name}</a> — <code>{dom}</code>')
        if notes:
            lines.append(f"   <i>{notes}</i>")
    if custom:
        lines.append("")
        lines.append(f"<b>Custom (/addsite)</b> ({len(custom)}):")
        for d in custom[:25]:
            flag = "⭐" if d in prem else "•"
            lines.append(f'{flag} <a href="https://{d}">{d}</a>')
    lines.append("")
    lines.append(f"<b>Premium-gated</b> ({len(prem)}):")
    lines.append(", ".join(f"<code>{s}</code>" for s in prem[:25]) or "—")
    lines.append("")
    lines.append("🔍 = /search works · 🔗 = paste link only")
    lines.append("Owner: /addsite /delsite /setpremium")
    lines.append("</blockquote>")
    await message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@Client.on_message(filters.private & filters.command("setcaption"))
@check_ban
async def setcaption_cmd(client: Client, message: Message):
    """Per-user caption template: {title} {uploader} {size} {duration}"""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        cur = await db.get_user_settings(message.from_user.id)
        tpl = cur.get("caption_template") or "default"
        await message.reply_text(
            f"<blockquote>Current: <code>{tpl}</code>\n"
            f"Usage: <code>/setcaption {{title}} — {{uploader}}</code>\n"
            f"Vars: title, uploader, size, duration, url</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    tpl = parts[1].strip()[:300]
    s = await db.get_user_settings(message.from_user.id)
    s["caption_template"] = tpl
    await db.set_user_settings(message.from_user.id, s)
    await message.reply_text(f"<blockquote>{ok()} Caption saved.</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("id"))
@check_ban
async def id_cmd(client: Client, message: Message):
    u = message.from_user
    await message.reply_text(
        f"<blockquote>👤 <code>{u.id}</code>\n"
        f"@{u.username or '—'}\n"
        f"{u.first_name or ''}</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("echo"))
@check_ban
async def echo_cmd(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return
    await message.reply_text(parts[1], parse_mode=ParseMode.HTML)
