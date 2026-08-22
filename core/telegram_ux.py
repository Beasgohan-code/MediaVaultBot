#@mediavault
"""Modern Bot API UX: reactions, chat actions, progressive status, protect_content."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from pyrogram import Client
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message

from core.emoji import thinking_frames, ce, ok

logger = logging.getLogger(__name__)


async def safe_react(client: Client, chat_id: int, message_id: int, emoji: str = "🔥") -> None:
    """Bot API message reaction (best-effort)."""
    try:
        await client.send_reaction(chat_id, message_id, emoji)
    except Exception as e:
        logger.debug("react failed: %s", e)


async def safe_chat_action(client: Client, chat_id: int, action: ChatAction = ChatAction.TYPING) -> None:
    try:
        await client.send_chat_action(chat_id, action)
    except Exception:
        pass


async def thinking_animation(
    status_msg: Message,
    stop_event: asyncio.Event,
    interval: float = 1.2,
) -> None:
    """Cycle status text like AI streaming while work runs."""
    frames = thinking_frames()
    i = 0
    while not stop_event.is_set():
        try:
            await status_msg.edit_text(
                f"<blockquote>{frames[i % len(frames)]}</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        i += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            continue


def protect_kwargs(user_settings: dict) -> dict:
    """Optional protect_content for sends."""
    if user_settings.get("protect_content"):
        return {"protect_content": True}
    return {}


async def finish_card(title: str, extra: str = "") -> str:
    return (
        f"<blockquote>{ok()} <b>Ready</b>\n"
        f"{ce('sparkle', '✨')} {title[:80]}\n"
        f"{extra}</blockquote>"
    )
