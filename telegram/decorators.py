#@mediavault
from __future__ import annotations

import functools
import logging
from typing import Callable

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery

from config import OWNER_ID, FSUB_CHANNEL
from core.database import db

logger = logging.getLogger(__name__)


def check_ban(func: Callable):
    @functools.wraps(func)
    async def wrapper(client: Client, update, *args, **kwargs):
        user = update.from_user
        if not user:
            return
        if await db.is_banned(user.id):
            text = "🚫 You are banned from using this bot."
            if isinstance(update, Message):
                await update.reply_text(text)
            elif isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            return
        return await func(client, update, *args, **kwargs)
    return wrapper


def admin_only(func: Callable):
    @functools.wraps(func)
    async def wrapper(client: Client, update, *args, **kwargs):
        user = update.from_user
        if not user:
            return
        if user.id != OWNER_ID and not await db.is_admin(user.id):
            text = "⛔ Admin only."
            if isinstance(update, Message):
                await update.reply_text(text)
            elif isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            return
        return await func(client, update, *args, **kwargs)
    return wrapper


def owner_only(func: Callable):
    @functools.wraps(func)
    async def wrapper(client: Client, update, *args, **kwargs):
        user = update.from_user
        if not user or user.id != OWNER_ID:
            text = "👑 Owner only."
            if isinstance(update, Message):
                await update.reply_text(text)
            elif isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            return
        return await func(client, update, *args, **kwargs)
    return wrapper
