#@mediavault
"""Telegram Stars balance + premium plans (from working pyrofork bot logic)."""
from __future__ import annotations

import re
from datetime import timedelta

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice,
)

from config import OWNER_ID, PRICE_PER_DAY, PREMIUM_DOMAINS
from core.database import db
from core.emoji import ce, ok, crown
from telegram.decorators import check_ban


def premium_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💎 1 day — {PRICE_PER_DAY} ⭐", callback_data="plan:1")],
        [InlineKeyboardButton(f"💎 7 days — {7*PRICE_PER_DAY} ⭐", callback_data="plan:7")],
        [InlineKeyboardButton(f"💎 30 days — {30*PRICE_PER_DAY} ⭐", callback_data="plan:30")],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ])


@Client.on_message(filters.private & filters.command("stars"))
@check_ban
async def stars_cmd(client: Client, message: Message):
    uid = message.from_user.id
    bal = await db.get_stars(uid)
    prem = await db.get_premium(uid)
    extra = ""
    if prem["active"] and prem["expires_at"]:
        left = prem["expires_at"] - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        extra = f"\n{crown()} Premium: ✅ ({left.days}d {left.seconds//3600}h left)"
    else:
        extra = f"\n{crown()} Premium: ❌"
    await message.reply_text(
        f"<blockquote>{ce('coin', '🪙')} <b>Stars</b>\n"
        f"Balance: <code>{bal}</code> ⭐{extra}\n\n"
        f"/buy 100 — buy stars\n"
        f"/premium — plans</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("buy"))
@check_ban
async def buy_cmd(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text(
            f"<blockquote>Usage: <code>/buy 100</code>\nMin 1 · Max 2500 ⭐</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    amount = int(parts[1])
    if amount < 1 or amount > 2500:
        await message.reply_text("❌ Min 1, max 2500")
        return
    try:
        await client.send_invoice(
            chat_id=message.chat.id,
            title=f"{amount} Stars",
            description=f"Buy {amount} Telegram Stars for MediaVault",
            payload=f"stars_{amount}_{message.from_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label=f"{amount} stars", amount=amount)],
        )
    except Exception as e:
        await message.reply_text(
            f"<blockquote>{ce('alert', '🚨')} Invoice failed: <code>{e}</code>\n"
            f"Stars payments need a bot that can receive XTR.</blockquote>",
            parse_mode=ParseMode.HTML,
        )


@Client.on_message(filters.private & filters.successful_payment)
async def on_stars_payment(client: Client, message: Message):
    amount = message.successful_payment.total_amount
    new_bal = await db.add_stars(message.from_user.id, amount)
    await message.reply_text(
        f"<blockquote>{ok()} +{amount} ⭐\nBalance: <code>{new_bal}</code> ⭐</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("premium"))
@check_ban
async def premium_cmd(client: Client, message: Message):
    await message.reply_text(
        f"<blockquote>{crown()} <b>Premium</b>\n"
        f"Unlocks premium / NSFW-listed domains ({', '.join(PREMIUM_DOMAINS) or 'none'}).\n"
        f"Pay with Stars from /buy.</blockquote>",
        reply_markup=premium_plans_kb(),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^plan:(\d+)$"))
@check_ban
async def plan_cb(client: Client, query: CallbackQuery):
    days = int(query.data.split(":")[1])
    price = days * PRICE_PER_DAY
    uid = query.from_user.id
    bal = await db.get_stars(uid)
    await query.answer()
    if bal < price:
        await query.message.edit_text(
            f"<blockquote>Need <code>{price}</code> ⭐, have <code>{bal}</code>.\n"
            f"Use /buy {price - bal}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return
    await query.message.edit_text(
        f"<blockquote>{crown()} Confirm <b>{days} day(s)</b>\n"
        f"Cost: <code>{price}</code> ⭐ · Balance: <code>{bal}</code></blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Pay {price} ⭐", callback_data=f"payprem:{days}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close")],
        ]),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^payprem:(\d+)$"))
@check_ban
async def pay_premium_cb(client: Client, query: CallbackQuery):
    days = int(query.data.split(":")[1])
    price = days * PRICE_PER_DAY
    uid = query.from_user.id
    if not await db.spend_stars(uid, price):
        await query.answer("Not enough stars", show_alert=True)
        return
    await db.set_premium(uid, float(days), price)
    prem = await db.get_premium(uid)
    exp = prem["expires_at"].strftime("%Y-%m-%d %H:%M") if prem["expires_at"] else "?"
    await query.answer("Premium on")
    await query.message.edit_text(
        f"<blockquote>{ok()} <b>Premium active</b>\n"
        f"Until: <code>{exp}</code> UTC\n"
        f"Balance: <code>{await db.get_stars(uid)}</code> ⭐</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@Client.on_message(filters.private & filters.command("ownerstats"))
@check_ban
async def owner_stats(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.reply_text(
        f"<blockquote>{crown()} Owner\nUse /stats for bot stats.\nStars live in star_balances table.</blockquote>",
        parse_mode=ParseMode.HTML,
    )
