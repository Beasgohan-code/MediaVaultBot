#@mediavault
"""
MediaVaultBot – 2026
Kurigram + PostgreSQL + Google Drive + yt-dlp
Queue • Formats • Quotas • Health • Cleanup
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from aiohttp import web
from pyrogram import Client
from pyrogram.enums import ParseMode

from config import (
    API_ID, API_HASH, BOT_TOKEN, OWNER_ID, YTDLP_ENABLED,
    HEALTH_PORT, TEMP_CLEANUP_MINUTES, WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_PORT, INSTANCE_ID,
)
from core.database import db
from core.drive import drive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logger = logging.getLogger("mediavault")

TMP_ROOTS = [
    Path("/tmp/mediavault_ytdlp"),
    Path("/tmp/mediavault"),
]


async def health_handler(request):
    try:
        # light DB check
        n = await db.get_user_count()
        disk = shutil.disk_usage("/")
        return web.json_response({
            "status": "ok",
            "users": n,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "ytdlp": YTDLP_ENABLED,
            "ts": int(time.time()),
        })
    except Exception as e:
        return web.json_response({"status": "error", "detail": str(e)}, status=500)


async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health endpoint on :%s/health", HEALTH_PORT)


async def temp_cleanup_loop():
    """Delete old temp files every TEMP_CLEANUP_MINUTES."""
    while True:
        try:
            cutoff = time.time() - (TEMP_CLEANUP_MINUTES * 60)
            removed = 0
            for root in TMP_ROOTS:
                if not root.exists():
                    continue
                for p in root.rglob("*"):
                    try:
                        if p.is_file() and p.stat().st_mtime < cutoff:
                            p.unlink()
                            removed += 1
                    except Exception:
                        pass
            if removed:
                logger.info("Temp cleanup removed %s files", removed)
        except Exception as e:
            logger.warning("cleanup error: %s", e)
        await asyncio.sleep(max(60, TEMP_CLEANUP_MINUTES * 30))



async def schedule_loop(app: Client):
    """Fire pending scheduled downloads."""
    from core.ytdlp import download as ytdlp_download
    from core.media import auto_tags, metadata_card
    while True:
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            jobs = await db.pending_schedules(now)
            for job in jobs:
                try:
                    await db.set_schedule_status(job.id, "running")
                    # notify user
                    try:
                        await app.send_message(
                            job.user_id,
                            f"<blockquote>⏰ Running scheduled job <code>{job.id}</code></blockquote>\n<code>{job.url[:80]}</code>",
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    except Exception:
                        pass
                    result = await ytdlp_download(job.url, job.user_id, quality=job.quality)
                    path = result.get("filepath")
                    title = result.get("title") or "file"
                    size = result.get("filesize")
                    if path:
                        # send
                        try:
                            await app.send_document(job.user_id, path, caption=f"⏰ Scheduled: {title[:80]}")
                        except Exception:
                            try:
                                await app.send_video(job.user_id, path, caption=f"⏰ Scheduled: {title[:80]}")
                            except Exception as e:
                                await app.send_message(job.user_id, f"Scheduled download failed send: {e}")
                        try:
                            import os
                            os.unlink(path)
                        except Exception:
                            pass
                    await db.log_download(job.user_id, result.get("id") or job.url, title, size)
                    tags = auto_tags(title)
                    await db.add_library_item(
                        user_id=job.user_id, source="ytdlp",
                        external_id=str(result.get("id") or job.url)[:250],
                        title=title, clean_title=tags.get("clean_title"),
                        year=tags.get("year"), season=tags.get("season"),
                        episode=tags.get("episode"), duration=result.get("duration"),
                        size=size, extractor=result.get("extractor"),
                        webpage_url=job.url,
                    )
                    await db.set_schedule_status(job.id, "done")
                except Exception as e:
                    logger.exception("schedule job %s", job.id)
                    await db.set_schedule_status(job.id, "failed")
                    try:
                        await app.send_message(job.user_id, f"Scheduled job failed: {e}")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("schedule_loop: %s", e)
        await asyncio.sleep(30)


def create_app() -> Client:
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("Set API_ID, API_HASH and BOT_TOKEN in .env")
        sys.exit(1)
    if not OWNER_ID:
        logger.warning("OWNER_ID not set")

    return Client(
        "mediavault",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="telegram.plugins"),
        parse_mode=ParseMode.HTML,
        in_memory=True,
    )


async def main():
    logger.info("Starting MediaVaultBot…")
    await db.connect()
    try:
        await drive.connect()
        logger.info("Google Drive ready")
    except Exception as e:
        logger.warning("Drive not available: %s", e)

    if YTDLP_ENABLED:
        logger.info("yt-dlp enabled")

    asyncio.create_task(start_health_server())
    asyncio.create_task(temp_cleanup_loop())

    app = create_app()
    await app.start()
    me = await app.get_me()
    logger.info("Bot online as @%s (id=%s)", me.username, me.id)
    asyncio.create_task(schedule_loop(app))
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down…")
